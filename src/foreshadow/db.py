from __future__ import annotations

import importlib.resources
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    os.chmod(path, 0o600)
    conn.execute("PRAGMA journal_mode=WAL").fetchone()
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    if _version_applied(conn, SCHEMA_VERSION):
        return
    sql = (
        importlib.resources.files("foreshadow")
        .joinpath("sql/001_init.sql")
        .read_text(encoding="utf-8")
    )
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )
    conn.commit()


def _version_applied(conn: sqlite3.Connection, version: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if row is None:
        return False
    found = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
    ).fetchone()
    return found is not None
