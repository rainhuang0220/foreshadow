"""Actionable diagnostics for HOME, DB, token, scheduler, last run."""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from foreshadow.config import ensure_default_config, load_config, user_config_path
from foreshadow.db import SCHEMA_VERSION, connect, migrate
from foreshadow.github.client import token_source
from foreshadow.paths import (
    default_data_dir,
    is_unstable_path,
    resolve_data_dir,
)
from foreshadow.schedule import (
    load_spec,
    plist_text_unstable,
    scheduler_status,
    stray_agent_plists,
)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""
    level: str = "error"  # error | warn | info


def initialize() -> dict[str, Any]:
    """Create HOME, SQLite, and default config. Idempotent."""
    from foreshadow.paths import resolve_log_dir

    data_dir = resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    resolve_log_dir(data_dir)
    (data_dir / "reports").mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "foreshadow.sqlite3"
    existed = db_path.is_file()
    conn = connect(db_path)
    migrate(conn)
    conn.close()
    cfg = user_config_path()
    wrote_config = not cfg.exists()
    ensure_default_config(cfg)
    source = token_source()
    return {
        "home": str(data_dir),
        "database": str(db_path),
        "database_existed": existed,
        "schema_version": SCHEMA_VERSION,
        "config": str(cfg),
        "wrote_config": wrote_config,
        "token_ok": source is not None,
        "token_source": source or "missing",
    }


def format_init(info: dict[str, Any]) -> str:
    lines = [
        "Foreshadow is ready.",
        f"home: {info['home']}",
        ("database: existing" if info.get("database_existed") else "database: created"),
        (
            f"config: wrote {info['config']}"
            if info.get("wrote_config")
            else f"config: {info['config']}"
        ),
        (
            f"github token: ok ({info['token_source']})"
            if info.get("token_ok")
            else "github token: missing — export GITHUB_TOKEN before the first run"
        ),
        "",
        "Next:",
        "  export GITHUB_TOKEN=ghp_...     # classic PAT, no scopes — or: gh auth login",
        "  foreshadow run",
        "  foreshadow board",
        "  foreshadow schedule install     # optional, once",
    ]
    return "\n".join(lines) + "\n"


def last_successful_run(data_dir: Path | None = None) -> str | None:
    path = (data_dir or resolve_data_dir()) / "foreshadow.sqlite3"
    if not path.is_file():
        return None
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT run_date, status FROM daily_runs
            WHERE status IN ('complete', 'degraded')
            ORDER BY run_date DESC LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    return f"{row[0]} {row[1]}"


def last_run_row(data_dir: Path | None = None) -> dict[str, Any] | None:
    path = (data_dir or resolve_data_dir()) / "foreshadow.sqlite3"
    if not path.is_file():
        return None
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT run_date, status, finished_at, top5_count, error,
                   source_health_json, report_path
            FROM daily_runs
            ORDER BY run_date DESC, id DESC LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    return {
        "run_date": row[0],
        "status": row[1],
        "finished_at": row[2],
        "top5_count": row[3],
        "error": row[4],
        "source_health_json": row[5],
        "report_path": row[6],
    }


def observation_counts(data_dir: Path | None = None) -> dict[str, int] | None:
    path = (data_dir or resolve_data_dir()) / "foreshadow.sqlite3"
    if not path.is_file():
        return None
    conn = connect(path)
    try:
        try:
            system = conn.execute(
                "SELECT COUNT(*) FROM observations WHERE state='active'"
            ).fetchone()[0]
        except sqlite3.Error:
            system = 0
        try:
            watch = conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT repo_id, action FROM reviews
                  WHERE id IN (SELECT MAX(id) FROM reviews GROUP BY repo_id)
                ) WHERE action IN ('watch', 'interested', 'investigate', 'enter')
                """
            ).fetchone()[0]
        except sqlite3.Error:
            watch = 0
    finally:
        conn.close()
    system_n = int(system or 0)
    watch_n = int(watch or 0)
    return {
        "watch": watch_n,
        "system": system_n,
        "panel": watch_n + system_n,
    }


def collect_doctor() -> dict[str, Any]:
    checks = collect_checks()
    source = token_source()
    home = resolve_data_dir()
    db = home / "foreshadow.sqlite3"
    return {
        "ok": doctor_exit_code(checks) == 0,
        "home": str(home),
        "database": str(db) if db.is_file() else None,
        "token_ok": source is not None,
        "token_source": source or "missing",
        "checks": checks,
        "last_run": last_successful_run(home),
        "gh": shutil.which("gh"),
    }


def format_doctor(info: dict[str, Any]) -> str:
    token_bit = (
        f"ok ({info.get('token_source')})" if info.get("token_ok") else "missing"
    )
    lines = [
        f"home: {info.get('home')}",
        f"github token: {token_bit}",
    ]
    if not info.get("token_ok"):
        lines.append("GitHub credentials unavailable")
        lines.append("next: export GITHUB_TOKEN=… or gh auth login")
    last = info.get("last_run")
    lines.append(f"last successful run: {last or 'none'}")
    checks = info.get("checks") or []
    if checks:
        lines.append("")
        lines.append(format_checks(checks).rstrip())
    if not info.get("ok"):
        lines.append("next: foreshadow doctor")
    return "\n".join(lines) + "\n"


def collect_status() -> dict[str, Any]:
    home = resolve_data_dir()
    return {
        "home": str(home),
        "last_run": last_run_row(home),
        "last_successful": last_successful_run(home),
        "observation": observation_counts(home),
        "schedule": scheduler_status(),
    }


def format_status(info: dict[str, Any]) -> str:
    lines = [f"home: {info.get('home')}"]
    last = info.get("last_run")
    if not last:
        lines.append("last run: none")
    else:
        extra = f"last run: {last.get('run_date')} {last.get('status')}"
        if last.get("top5_count") is not None:
            extra += f" top5={last.get('top5_count')}"
        lines.append(extra)
        if last.get("error"):
            lines.append(f"last error: {last['error']}")
    lines.append(f"last successful run: {info.get('last_successful') or 'none'}")
    sched = info.get("schedule") or {}
    if sched.get("installed") and sched.get("next_run"):
        lines.append(f"next run: {sched['next_run']} ({sched.get('backend')})")
    else:
        lines.append("next run: not scheduled")
    obs = info.get("observation")
    if obs is None:
        lines.append("observation: none")
    else:
        lines.append(
            "observation: "
            f"panel={obs['panel']} watch={obs['watch']} system={obs['system']}"
        )
    return "\n".join(lines) + "\n"


def collect_checks() -> list[Check]:
    checks: list[Check] = []
    checks.append(_python_check())
    checks.append(_home_check())
    checks.append(_database_check())
    checks.append(_config_check())
    checks.append(_token_check())
    checks.append(_git_check())
    checks.append(_port_check())
    checks.extend(_scheduler_checks())
    checks.append(_last_run_check())
    return checks


def format_checks(checks: list[Check]) -> str:
    lines: list[str] = []
    for check in checks:
        if check.ok:
            mark = "ok  "
        elif check.level == "warn":
            mark = "WARN"
        else:
            mark = "FAIL"
        lines.append(f"{mark}  {check.name}: {check.detail}")
        if not check.ok and check.hint:
            lines.append(f"      next: {check.hint}")
    failed = [c for c in checks if not c.ok and c.level == "error"]
    if failed:
        lines.append("next: fix the FAIL items, then foreshadow doctor")
    return "\n".join(lines) + "\n"


def doctor_exit_code(checks: list[Check]) -> int:
    if any(not c.ok and c.level == "error" for c in checks):
        return 1
    return 0


def format_product_status() -> str:
    home = resolve_data_dir()
    lines = [f"HOME: {home}"]
    if is_unstable_path(home):
        lines.append(
            "WARN: HOME is a Desktop/worktree path; "
            "product use does not need FORESHADOW_HOME"
        )
        lines.append(f"default HOME: {default_data_dir()}")
    last = last_run_row(home)
    if last is None:
        lines.append("last run: none")
    else:
        extra = last.get("status") or ""
        top = last.get("top5_count")
        bit = f"last run: {last.get('run_date')} {extra}"
        if top is not None:
            bit += f" top5={top}"
        lines.append(bit)
        if last.get("error"):
            lines.append(f"last error: {last['error']}")
    success = last_successful_run(home)
    lines.append(f"last successful run: {success or 'none'}")
    sched = scheduler_status()
    if sched.get("installed") and sched.get("next_run"):
        lines.append(f"next run: {sched['next_run']} ({sched.get('backend')})")
    else:
        lines.append("next run: not scheduled")
        lines.append("next: foreshadow schedule install")
    obs = observation_counts(home)
    if obs is None:
        lines.append("observation: none")
        if last is None:
            lines.append("next: foreshadow init && foreshadow run")
    else:
        lines.append(
            "observation: "
            f"panel={obs['panel']} watch={obs['watch']} system={obs['system']}"
        )
    from foreshadow.board.server import resolve_public_url

    board_url = resolve_public_url()
    if board_url:
        lines.append(f"Board: {board_url}")
    return "\n".join(lines) + "\n"


def _python_check() -> Check:
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    exe = Path(sys.executable)
    detail = f"{ver} at {exe}"
    if is_unstable_path(exe):
        return Check(
            "python",
            False,
            f"{detail} (Desktop/worktree)",
            "install with `uv tool install .` then use that interpreter",
            level="warn",
        )
    return Check("python", True, detail, level="info")


def _home_check() -> Check:
    home = resolve_data_dir()
    default = default_data_dir()
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".doctor-write"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check(
            "HOME",
            False,
            f"{home} not writable ({exc})",
            "fix permissions on the data directory "
            "(unset FORESHADOW_HOME to use the default)",
        )
    if is_unstable_path(home):
        return Check(
            "HOME",
            False,
            f"{home} is a Desktop/worktree path",
            f"unset FORESHADOW_HOME (default is {default})",
            level="warn",
        )
    detail = str(home)
    if home.resolve() == default.resolve():
        detail += " (platformdirs)"
    return Check("HOME", True, detail, level="info")


def _database_check() -> Check:
    path = resolve_data_dir() / "foreshadow.sqlite3"
    if not path.is_file():
        return Check(
            "database",
            False,
            f"missing {path}",
            "foreshadow init",
        )
    conn = connect(path)
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        version = int(row[0] or 0) if row else 0
    except sqlite3.Error as exc:
        return Check(
            "database",
            False,
            f"unreadable ({exc})",
            "foreshadow init",
        )
    finally:
        conn.close()
    if version < SCHEMA_VERSION:
        return Check(
            "database",
            False,
            f"schema {version} (want {SCHEMA_VERSION})",
            "foreshadow init",
        )
    return Check("database", True, f"{path} schema {version}", level="info")


def _config_check() -> Check:
    path = user_config_path()
    if not path.is_file():
        return Check(
            "config",
            True,
            "defaults (no user file)",
            level="info",
        )
    try:
        load_config()
    except SystemExit:
        return Check(
            "config",
            False,
            f"unreadable {path}",
            "fix ~/.config/foreshadow/config.toml (weights must sum to 100)",
        )
    return Check("config", True, str(path), level="info")


def _token_check() -> Check:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key, "").strip():
            return Check("token", True, f"ok ({key})", level="info")
    if shutil.which("gh"):
        source = token_source()
        if source:
            return Check("token", True, f"ok ({source})", level="info")
    return Check(
        "token",
        False,
        "missing",
        "export GITHUB_TOKEN=… (classic PAT, no scopes) or gh auth login",
    )


def _git_check() -> Check:
    path = shutil.which("git")
    if path:
        return Check("git", True, path, level="info")
    return Check(
        "git",
        False,
        "not installed",
        "macOS: xcode-select --install  ·  https://git-scm.com/downloads",
        level="warn",
    )


def _port_check(port: int = 8765) -> Check:
    if _port_free("127.0.0.1", port):
        return Check("board_port", True, f"{port} free", level="info")
    return Check(
        "board_port",
        False,
        f"{port} in use",
        f"foreshadow board --port {port + 1}",
        level="warn",
    )


def _port_free(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        return False
    return True


def _scheduler_checks() -> list[Check]:
    checks: list[Check] = []
    info = scheduler_status()
    spec = load_spec()
    if not info.get("installed"):
        checks.append(
            Check(
                "scheduler",
                False,
                "not installed",
                "foreshadow schedule install",
                level="warn",
            )
        )
    else:
        detail = (
            f"{info.get('backend')} at {info.get('hour'):02d}:{info.get('minute'):02d}"
            if info.get("hour") is not None
            else str(info.get("backend"))
        )
        if info.get("loaded") is False:
            checks.append(
                Check(
                    "scheduler",
                    False,
                    f"{detail} (not loaded)",
                    "foreshadow schedule install",
                )
            )
        else:
            checks.append(Check("scheduler", True, detail, level="info"))
        if spec is not None and (
            is_unstable_path(spec.python) or is_unstable_path(spec.home)
        ):
            checks.append(
                Check(
                    "scheduler.paths",
                    False,
                    "points at a Desktop/worktree",
                    "foreshadow schedule uninstall && foreshadow schedule install",
                )
            )
        elif info.get("unstable"):
            checks.append(
                Check(
                    "scheduler.paths",
                    False,
                    "LaunchAgent/unit contains a Desktop/worktree path",
                    "foreshadow schedule uninstall && foreshadow schedule install",
                )
            )
        else:
            py = info.get("python") or ""
            checks.append(Check("scheduler.python", True, str(py), level="info"))
    for stray in stray_agent_plists():
        unstable = plist_text_unstable(stray)
        checks.append(
            Check(
                "scheduler.stray",
                False,
                f"{stray}" + (" (worktree)" if unstable else ""),
                "foreshadow schedule uninstall (removes product agent; "
                "delete leftover dogfood plists by hand if needed)",
                level="error" if unstable else "warn",
            )
        )
    return checks


def _last_run_check() -> Check:
    row = last_run_row()
    if row is None:
        return Check(
            "last_run",
            False,
            "none",
            "foreshadow run",
            level="warn",
        )
    status = str(row.get("status") or "")
    detail = f"{row.get('run_date')} {status}"
    from foreshadow.clock import Clock

    today = Clock().today().isoformat()
    if status in {"complete", "degraded"} and str(row.get("run_date")) == today:
        return Check(
            "last_run",
            True,
            f"{detail} (already ran today; --force to debug)",
            level="info",
        )
    if status == "failed":
        err = str(row.get("error") or "failed")
        return Check(
            "last_run",
            False,
            f"{detail}: {err}",
            "foreshadow run --force",
        )
    if status == "running":
        return Check(
            "last_run",
            False,
            f"{detail} (unfinished)",
            "foreshadow run",
            level="warn",
        )
    return Check("last_run", True, detail, level="info")
