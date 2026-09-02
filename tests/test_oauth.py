"""GitHub identity login. Password is not the public operator path."""

from __future__ import annotations

import threading
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from foreshadow.auth import (
    SESSION_DAYS,
    create_session,
    lookup_session,
    operator_logins,
    session_cookie,
    upsert_github_user,
)
from foreshadow.board.server import make_server
from foreshadow.clock import Clock
from foreshadow.db import SCHEMA_VERSION, connect, migrate
from test_board_server import _seed_board


def test_schema_7_adds_github_identity_and_v03_tables(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    assert SCHEMA_VERSION == 7
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert "github_id" in cols
    assert "github_login" in cols
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for name in (
        "oauth_states",
        "observation_events",
        "entry_analyses",
        "contribution_jobs",
        "contribution_artifacts",
    ):
        assert name in tables, name


def test_operator_allowlist_from_env_not_source(monkeypatch):
    monkeypatch.delenv("FORESHADOW_OPERATORS", raising=False)
    assert operator_logins() == frozenset()
    monkeypatch.setenv("FORESHADOW_OPERATORS", "rainhuang0220, OtherUser")
    assert operator_logins() == frozenset({"rainhuang0220", "otheruser"})
    import inspect

    from foreshadow import auth

    source = inspect.getsource(auth)
    assert "rainhuang0220" not in source


def test_session_cookie_is_httponly_30_days_secure_optional():
    assert SESSION_DAYS == 30
    plain = session_cookie("tok")
    assert "HttpOnly" in plain
    assert "SameSite=Lax" in plain
    assert "Path=/" in plain
    assert "Max-Age=2592000" in plain
    assert "Secure" not in plain
    https = session_cookie("tok", secure=True)
    assert "Secure" in https


def test_github_user_upsert_and_session_rotation(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    user = upsert_github_user(conn, github_id=195641118, login="rainhuang0220")
    assert user["github_login"] == "rainhuang0220"
    assert user["username"] == "rainhuang0220"
    again = upsert_github_user(conn, github_id=195641118, login="rainhuang0220")
    assert again["id"] == user["id"]
    old = create_session(conn, int(user["id"]), auth_method="github")
    new = create_session(conn, int(user["id"]), auth_method="github")
    assert lookup_session(conn, old) is None
    found = lookup_session(conn, new)
    assert found is not None
    assert found["github_login"] == "rainhuang0220"


def _public_server(tmp_home, clock: Clock, monkeypatch):
    monkeypatch.setenv("FORESHADOW_GITHUB_OAUTH_CLIENT_ID", "client-test")
    monkeypatch.setenv("FORESHADOW_GITHUB_OAUTH_CLIENT_SECRET", "secret-test")
    monkeypatch.setenv("FORESHADOW_OPERATORS", "rainhuang0220")
    monkeypatch.setenv("FORESHADOW_BOARD_URL", "http://127.0.0.1/")
    _seed_board(tmp_home, clock)
    httpd = make_server(
        host="127.0.0.1",
        port=0,
        date="2026-08-24",
        preview=True,
        clock=clock,
        public=True,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    return httpd, f"http://{host}:{port}"


@respx.mock
def test_github_oauth_allowlisted_operator_gets_durable_session(
    tmp_home, frozen_clock, monkeypatch
):
    respx.route(host="127.0.0.1").pass_through()
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "gho_test", "token_type": "bearer", "scope": ""},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(
            200, json={"id": 195641118, "login": "rainhuang0220"}
        )
    )
    httpd, base = _public_server(tmp_home, frozen_clock, monkeypatch)
    try:
        start = httpx.get(f"{base}/api/auth/github", follow_redirects=False)
        assert start.status_code == 302
        loc = start.headers["location"]
        parsed = urlparse(loc)
        assert parsed.netloc == "github.com"
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == ["client-test"]
        assert "scope" not in qs or qs.get("scope") == [""]
        state = qs["state"][0]
        cb = httpx.get(
            f"{base}/api/auth/github/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert cb.status_code == 302
        cookie = cb.headers.get("set-cookie") or ""
        assert "foreshadow_session=" in cookie
        assert "HttpOnly" in cookie
        assert "Max-Age=2592000" in cookie
        me = httpx.get(f"{base}/api/me", headers={"Cookie": cookie.split(";", 1)[0]})
        body = me.json()
        assert body["user"]["github_login"] == "rainhuang0220"
        assert body["user"]["operator"] is True
        assert body["user"]["username"] == "rainhuang0220"
        conn = connect(tmp_home / "foreshadow.sqlite3")
        ntok = conn.execute(
            "SELECT COUNT(*) FROM oauth_states WHERE state=?", (state,)
        ).fetchone()[0]
        assert ntok == 0
        stored = conn.execute(
            "SELECT token_hash FROM sessions WHERE user_id=("
            "SELECT id FROM users WHERE github_login=?)",
            ("rainhuang0220",),
        ).fetchone()
        assert stored is not None
        assert "gho_test" not in str(stored[0])
    finally:
        httpd.shutdown()
        httpd.server_close()


@respx.mock
def test_github_oauth_rejects_non_operator(tmp_home, frozen_clock, monkeypatch):
    respx.route(host="127.0.0.1").pass_through()
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "gho_x", "token_type": "bearer", "scope": ""}
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"id": 1, "login": "random-person"})
    )
    httpd, base = _public_server(tmp_home, frozen_clock, monkeypatch)
    try:
        start = httpx.get(f"{base}/api/auth/github", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        cb = httpx.get(
            f"{base}/api/auth/github/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert cb.status_code in {302, 403}
        if cb.status_code == 302:
            assert "error=" in cb.headers.get("location", "")
        me = httpx.get(f"{base}/api/me")
        assert me.json()["user"] is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_github_oauth_start_without_client_id_is_503(
    tmp_home, frozen_clock, monkeypatch
):
    monkeypatch.delenv("FORESHADOW_GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("FORESHADOW_GITHUB_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("FORESHADOW_OPERATORS", "rainhuang0220")
    _seed_board(tmp_home, frozen_clock)
    httpd = make_server(
        host="127.0.0.1",
        port=0,
        date="2026-08-24",
        preview=True,
        clock=frozen_clock,
        public=True,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        res = httpx.get(f"{base}/api/auth/github", follow_redirects=False)
        assert res.status_code == 503
        assert "GitHub" in res.json()["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
