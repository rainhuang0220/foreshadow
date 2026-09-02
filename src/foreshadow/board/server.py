"""Review Board HTTP server. Localhost by default. Never logs secrets."""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from foreshadow.auth import (
    AuthError,
    authenticate,
    clear_session_cookie,
    create_session,
    lookup_session,
    parse_cookie,
    register_user,
    revoke_session,
    session_cookie,
)
from foreshadow.board.pipeline import build_board_from_db
from foreshadow.board.present import present_board
from foreshadow.clock import Clock
from foreshadow.config import Settings, load_config
from foreshadow.db import connect, migrate
from foreshadow.paths import resolve_data_dir
from foreshadow.reviews import (
    ACTIONS,
    ReviewError,
    ReviewFetchError,
    apply_review,
    latest_action_map,
)

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_BODY = 64 * 1024
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_STATIC_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_SAFE_STATIC = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE
)


def _resolve_static(url_path: str) -> tuple[Path, str] | None:
    """Map /static/<name> to a file inside _ASSETS_DIR. Rejects traversal."""
    rel = unquote(url_path)
    prefix = "/static/"
    if not rel.startswith(prefix):
        return None
    name = rel[len(prefix) :]
    if not _SAFE_STATIC.fullmatch(name):
        return None
    try:
        root = _ASSETS_DIR.resolve()
        target = (root / name).resolve()
        target.relative_to(root)
    except (OSError, ValueError):
        return None
    if not target.is_file():
        return None
    ctype = _STATIC_TYPES.get(target.suffix.lower())
    if ctype is None:
        return None
    return target, ctype


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_board_public(settings: Settings | None = None) -> bool:
    flag = _env_flag("FORESHADOW_BOARD_PUBLIC")
    if flag is not None:
        return flag
    if settings is not None:
        return bool(settings.board.public)
    return False


def resolve_allow_register(settings: Settings | None = None) -> bool:
    flag = _env_flag("FORESHADOW_BOARD_ALLOW_REGISTER")
    if flag is not None:
        return flag
    if settings is not None:
        return bool(settings.board.allow_register)
    return True


def resolve_public_url(settings: Settings | None = None) -> str:
    env = (os.environ.get("FORESHADOW_BOARD_URL") or "").strip()
    if env:
        return env.rstrip("/") + "/"
    if settings is not None:
        url = (settings.board.public_url or "").strip()
        if url:
            return url.rstrip("/") + "/"
    return ""


class BoardState:
    def __init__(
        self,
        *,
        date: str,
        preview: bool,
        clock: Clock,
        settings: Settings,
        public: bool = False,
        allow_register: bool = True,
        public_url: str = "",
    ) -> None:
        self.date = date
        self.preview = preview
        self.clock = clock
        self.settings = settings
        self.public = public
        self.allow_register = allow_register
        self.public_url = public_url
        self._lock = threading.Lock()

    def db(self):
        path = resolve_data_dir() / "foreshadow.sqlite3"
        conn = connect(path)
        migrate(conn)
        return conn

    def board_payload(self, user_id: int | None) -> dict[str, Any]:
        with self._lock:
            conn = self.db()
            try:
                doc, before, after = build_board_from_db(
                    date=self.date,
                    preview=self.preview,
                    clock=self.clock,
                    settings=self.settings,
                )
                if before != after:
                    raise RuntimeError("board run mutated snapshots")
                stances = latest_action_map(conn, user_id=user_id) if user_id else {}
                missions: dict[str, dict] = {}
                if user_id:
                    from foreshadow.mission import list_missions

                    for row in list_missions(conn, int(user_id)):
                        name = str(row.get("full_name") or "")
                        if not name or str(row.get("status") or "") == "ABANDONED":
                            continue
                        missions.setdefault(name, row)
            finally:
                conn.close()
            return present_board(doc, stances=stances, missions=missions)


def _json_bytes(payload: Any, status: int = 200) -> tuple[int, bytes, str]:
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return status, raw, "application/json; charset=utf-8"


def _mission_id(data: dict[str, Any]) -> int:
    raw = data.get("id")
    try:
        mid = int(raw) if raw is not None and raw is not False else 0
    except (TypeError, ValueError):
        raise ValueError("需要任务 id") from None
    if mid <= 0:
        raise ValueError("需要任务 id")
    return mid


class BoardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: BoardState

    def log_message(self, fmt: str, *args: Any) -> None:
        msg = fmt % args
        lowered = msg.lower()
        if "password" in lowered or "cookie" in lowered or "token" in lowered:
            return
        sys.stderr.write(f"{self.address_string()} - {msg}\n")

    def _origin_ok(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return not self.state.public
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.path not in {"", "/"} or parsed.username or parsed.password:
            return False
        req = urlparse("http://" + (self.headers.get("Host") or ""))
        origin_host = (parsed.hostname or "").lower()
        req_host = (req.hostname or "").lower()
        if not origin_host or origin_host != req_host:
            return False
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        req_port = req.port or 80
        return origin_port == req_port

    def _access(self) -> dict[str, Any]:
        return {
            "public": self.state.public,
            "allow_register": self.state.allow_register,
            "board_url": self.state.public_url or None,
        }

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError("无效请求") from None
        if length < 0 or length > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise TypeError("json object required")
        return data

    def _user(self) -> dict[str, Any] | None:
        token = parse_cookie(self.headers.get("Cookie"))
        conn = self.state.db()
        try:
            return lookup_session(conn, token)
        finally:
            conn.close()

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        for name, value in extra or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_cookie(self, status: int, payload: Any, cookie: str) -> None:
        status, body, ctype = _json_bytes(payload, status)
        self._send(status, body, ctype, [("Set-Cookie", cookie)])

    def _serve_static(self, path: str) -> None:
        resolved = _resolve_static(path)
        if resolved is None:
            self._send(*_json_bytes({"error": "not found"}, 404))
            return
        target, ctype = resolved
        try:
            body = target.read_bytes()
        except OSError:
            self._send(*_json_bytes({"error": "not found"}, 404))
            return
        self._send(200, body, ctype)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/static/"):
            self._serve_static(path)
            return
        if path in {"/", "/index.html"}:
            from foreshadow.board.webapp import render_app_html

            body = render_app_html().encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/api/me":
            user = self._user()
            access = self._access()
            if user is None:
                self._send(*_json_bytes({"user": None, **access}, 200))
                return
            self._send(
                *_json_bytes(
                    {
                        "user": {k: user[k] for k in ("id", "username", "email")},
                        **access,
                    }
                )
            )
            return
        if path == "/api/portfolio":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            from foreshadow.mission import portfolio
            from foreshadow.pipeline.learning import observed_access

            conn = self.state.db()
            try:
                payload = portfolio(conn, int(user["id"]))
                payload["observed_access"] = observed_access(
                    conn, user_id=int(user["id"])
                )
            finally:
                conn.close()
            self._send(*_json_bytes(payload))
            return
        if path == "/api/missions":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            from foreshadow.mission import list_missions

            conn = self.state.db()
            try:
                items = list_missions(conn, int(user["id"]))
            finally:
                conn.close()
            self._send(*_json_bytes({"missions": items}))
            return
        if path == "/api/board":
            user = self._user()
            if user is None and not self.state.public:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            uid = int(user["id"]) if user is not None else None
            payload = self.state.board_payload(uid)
            payload.update(self._access())
            self._send(*_json_bytes(payload))
            return
        self._send(*_json_bytes({"error": "not found"}, 404))

    def do_POST(self) -> None:
        if not self._origin_ok():
            self._send(*_json_bytes({"error": "origin"}, 403))
            return
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            data = self._read_json()
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send(*_json_bytes({"error": "无效请求"}, 400))
            return
        if path == "/api/register":
            if self.state.public and not self.state.allow_register:
                self._send(*_json_bytes({"error": "公网未开放注册"}, 403))
                return
            conn = self.state.db()
            try:
                user = register_user(
                    conn,
                    str(data.get("username") or ""),
                    str(data.get("email") or ""),
                    str(data.get("password") or ""),
                )
                token = create_session(conn, int(user["id"]))
            except AuthError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            finally:
                conn.close()
            self._send_cookie(
                200,
                {"user": {k: user[k] for k in ("id", "username", "email")}},
                session_cookie(token),
            )
            return
        if path == "/api/login":
            conn = self.state.db()
            try:
                user = authenticate(
                    conn,
                    str(data.get("username") or data.get("identity") or ""),
                    str(data.get("password") or ""),
                )
                token = create_session(conn, int(user["id"]))
            except AuthError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 401))
                return
            finally:
                conn.close()
            self._send_cookie(
                200,
                {"user": {k: user[k] for k in ("id", "username", "email")}},
                session_cookie(token),
            )
            return
        if path == "/api/logout":
            token = parse_cookie(self.headers.get("Cookie"))
            conn = self.state.db()
            try:
                revoke_session(conn, token)
            finally:
                conn.close()
            self._send_cookie(200, {"ok": True}, clear_session_cookie())
            return
        if path == "/api/review":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            repo = str(data.get("repo") or data.get("full_name") or "")
            action = str(data.get("action") or "")
            note = data.get("note")
            note_s = str(note) if note else None
            if action not in ACTIONS:
                self._send(
                    *_json_bytes({"error": f"未知操作（{', '.join(ACTIONS)}）"}, 400)
                )
                return
            conn = self.state.db()
            try:
                apply_review(
                    conn,
                    None,
                    repo,
                    action,
                    note_s,
                    self.state.clock,
                    settings=self.state.settings,
                    user_id=int(user["id"]),
                )
            except ReviewError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            except ReviewFetchError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            finally:
                conn.close()
            self._send(*_json_bytes({"ok": True, "repo": repo, "action": action}))
            return
        if path == "/api/mission":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            from foreshadow.mission import create_for_user, parse_repo_name
            from foreshadow.paths import resolve_data_dir

            name = str(data.get("full_name") or data.get("repo") or "")
            try:
                name = parse_repo_name(name)
            except ValueError:
                self._send(*_json_bytes({"error": "需要合法的 owner/repo"}, 400))
                return
            conn = self.state.db()
            try:
                mission = create_for_user(
                    conn,
                    user_id=int(user["id"]),
                    full_name=name,
                    data_dir=resolve_data_dir(),
                )
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            finally:
                conn.close()
            self._send(*_json_bytes({"mission": mission.as_dict()}))
            return
        if path == "/api/mission/setup":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            from foreshadow.mission import setup_local_environment
            from foreshadow.paths import resolve_data_dir

            try:
                mid = _mission_id(data)
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            conn = self.state.db()
            try:
                out = setup_local_environment(
                    conn, mid, int(user["id"]), resolve_data_dir()
                )
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            finally:
                conn.close()
            self._send(*_json_bytes({"mission": out["mission"], "clone": out["clone"]}))
            return
        if path == "/api/mission/event":
            user = self._user()
            if user is None:
                self._send(*_json_bytes({"error": "需要登录"}, 401))
                return
            from foreshadow.mission import record_user_event

            event = str(data.get("event") or "")
            try:
                mid = _mission_id(data)
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            conn = self.state.db()
            try:
                plan = record_user_event(
                    conn, user_id=int(user["id"]), mission_id=mid, event=event
                )
            except ValueError as exc:
                self._send(*_json_bytes({"error": str(exc)}, 400))
                return
            finally:
                conn.close()
            self._send(*_json_bytes({"mission": plan, "event": event}))
            return
        if path == "/api/mission/remote":
            from foreshadow.mission import record_remote_refused, refuse_remote_action

            action = str(data.get("action") or "")
            out = refuse_remote_action(action)
            user = self._user()
            if user is not None:
                conn = self.state.db()
                try:
                    mid = None
                    try:
                        if data.get("id") not in (None, "", 0, "0"):
                            mid = _mission_id(data)
                    except ValueError:
                        mid = None
                    record_remote_refused(
                        conn,
                        user_id=int(user["id"]),
                        action=action,
                        mission_id=mid,
                    )
                finally:
                    conn.close()
            self._send(*_json_bytes(out))
            return
        self._send(*_json_bytes({"error": "not found"}, 404))

    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain")


def validate_host(host: str, *, public: bool = False) -> str:
    h = (host or "").strip() or "127.0.0.1"
    if h in LOOPBACK:
        return h
    if public and h in {"0.0.0.0", "::"}:
        return h
    raise ValueError(f"board 只允许绑定本机回环地址，拒绝 {h}（公网请用 --public）")


def _is_addr_in_use(exc: OSError) -> bool:
    codes = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)}
    if getattr(exc, "errno", None) in codes:
        return True
    if getattr(exc, "winerror", None) in codes:
        return True
    msg = str(exc).lower()
    return "address already in use" in msg or "already in use" in msg


def port_in_use_message(host: str, port: int) -> str:
    nxt = port + 1 if port else 8766
    return (
        f"端口 {port} 已被占用，看板无法在 http://{host}:{port}/ 启动。\n"
        f"换一个端口：  foreshadow board --port {nxt}\n"
        f"查看占用该端口的进程：  lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
        "结束后再运行 foreshadow board。"
    )


def make_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    date: str,
    preview: bool,
    clock: Clock | None = None,
    settings: Settings | None = None,
    public: bool | None = None,
) -> ThreadingHTTPServer:
    clock = clock or Clock()
    settings = settings or load_config()
    is_public = resolve_board_public(settings) if public is None else public
    host = validate_host(host, public=is_public)
    state = BoardState(
        date=date,
        preview=preview,
        clock=clock,
        settings=settings,
        public=is_public,
        allow_register=resolve_allow_register(settings),
        public_url=resolve_public_url(settings),
    )

    class BoundHandler(BoardHandler):
        pass

    BoundHandler.state = state
    httpd = ThreadingHTTPServer((host, port), BoundHandler)
    return httpd


def serve_board(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    date: str,
    preview: bool,
    clock: Clock | None = None,
    settings: Settings | None = None,
    open_browser: bool = True,
    public: bool | None = None,
) -> None:
    settings = settings or load_config()
    is_public = resolve_board_public(settings) if public is None else public
    host = validate_host(host, public=is_public)
    try:
        httpd = make_server(
            host=host,
            port=port,
            date=date,
            preview=preview,
            clock=clock,
            settings=settings,
            public=is_public,
        )
    except OSError as exc:
        if _is_addr_in_use(exc):
            print(port_in_use_message(host, port), file=sys.stderr, flush=True)
            raise SystemExit(1) from exc
        print(f"无法启动看板：{exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    actual_port = httpd.server_address[1]
    bind_url = f"http://{host}:{actual_port}/"
    public_url = resolve_public_url(settings)
    print(f"Foreshadow Board  {bind_url}", flush=True)
    if public_url:
        print(f"public  {public_url}", flush=True)
    if is_public:
        print(
            "公网只读；开始进入 / clone 需要登录。远程 GitHub 写入仍需人工批准。",
            flush=True,
        )
    else:
        print("仅监听本机。Ctrl+C 结束。", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(public_url or bind_url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
