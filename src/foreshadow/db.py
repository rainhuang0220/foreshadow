from __future__ import annotations

import importlib.resources
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 5

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, "001_init.sql"),
    (2, "002_users.sql"),
    (3, "003_score_version.sql"),
    (4, "004_missions.sql"),
    (5, "005_learning.sql"),
)


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
    for version, filename in MIGRATIONS:
        if _version_applied(conn, version):
            continue
        sql = (
            importlib.resources.files("foreshadow")
            .joinpath(f"sql/{filename}")
            .read_text(encoding="utf-8")
        )
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        if version == 2:
            _backfill_review_users(conn)


def _backfill_review_users(conn: sqlite3.Connection) -> None:
    from foreshadow.auth import ensure_local_user

    uid = ensure_local_user(conn)
    conn.execute("UPDATE reviews SET user_id=? WHERE user_id IS NULL", (uid,))
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
