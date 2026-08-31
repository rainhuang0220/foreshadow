"""Minimal local users, password hashes, and session cookies.

Public scan data stays in repos/snapshots/scores. Reviews are per-user.
The CLI operator is a reserved local user that cannot log in via the Board.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

PBKDF2_ITERATIONS = 400_000
SESSION_DAYS = 14
COOKIE_NAME = "foreshadow_session"
LOCAL_USERNAME = "local"
LOCAL_EMAIL = "local@foreshadow.localhost"
RESERVED_USERNAMES = frozenset(
    {"local", "admin", "system", "foreshadow", "root", "operator"}
)

_USERNAME_RE = re.compile(
    r"^[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\-\u4e00-\u9fff]{1,31}$"
)
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


class AuthError(Exception):
    """Register / login validation. Safe to show to the user."""


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not isinstance(password, str):
        raise TypeError("password must be str")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


def ensure_local_user(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM users WHERE is_local=1 LIMIT 1").fetchone()
    if row:
        return int(row[0])
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO users(username, email, password_hash, created_at, is_local)
        VALUES (?,?,?,?,1)
        """,
        (
            LOCAL_USERNAME,
            LOCAL_EMAIL,
            hash_password(secrets.token_urlsafe(48)),
            now,
        ),
    )
    conn.commit()
    found = conn.execute("SELECT id FROM users WHERE is_local=1 LIMIT 1").fetchone()
    assert found is not None
    return int(found[0])


def resolve_cli_user(conn: sqlite3.Connection) -> int:
    """Prefer the latest unexpired Board session so CLI and Board share missions."""
    now = datetime.now(UTC).isoformat()
    row = conn.execute(
        """
        SELECT user_id FROM sessions
        WHERE expires_at > ?
        ORDER BY COALESCE(last_seen_at, created_at) DESC
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row:
        return int(row[0])
    return ensure_local_user(conn)


def is_operator_user(conn: sqlite3.Connection, user_id: int) -> bool:
    row = conn.execute("SELECT is_local FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and int(row[0]) == 1)


def public_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, username, email, created_at, is_local
        FROM users WHERE id=?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "username": row[1],
        "email": row[2],
        "created_at": row[3],
        "is_local": bool(row[4]),
    }


def register_user(
    conn: sqlite3.Connection, username: str, email: str, password: str
) -> dict[str, Any]:
    name = (username or "").strip()
    mail = (email or "").strip().lower()
    if not _USERNAME_RE.match(name):
        raise AuthError("用户名需 2–32 个字符，仅字母、数字、下划线、连字符或汉字。")
    if name.lower() in RESERVED_USERNAMES:
        raise AuthError("该用户名不可用。")
    if not _EMAIL_RE.match(mail):
        raise AuthError("邮箱格式不正确。")
    if len(password or "") < 8:
        raise AuthError("密码至少 8 位。")
    if len(password) > 256:
        raise AuthError("密码过长。")
    now = datetime.now(UTC).isoformat()
    try:
        cur = conn.execute(
            """
            INSERT INTO users(username, email, password_hash, created_at, is_local)
            VALUES (?,?,?,?,0)
            """,
            (name, mail, hash_password(password), now),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise AuthError("用户名或邮箱已被使用。") from exc
    uid = int(cur.lastrowid)
    user = public_user(conn, uid)
    assert user is not None
    return user


def authenticate(
    conn: sqlite3.Connection, identity: str, password: str
) -> dict[str, Any]:
    ident = (identity or "").strip()
    if not ident or not password:
        raise AuthError("请输入用户名/邮箱和密码。")
    row = conn.execute(
        """
        SELECT id, password_hash, is_local FROM users
        WHERE username = ? OR email = ?
        """,
        (ident, ident.lower()),
    ).fetchone()
    if row is None or not verify_password(password, row[1]):
        raise AuthError("用户名或密码不正确。")
    if int(row[2]) == 1:
        raise AuthError("本地操作账号不能用于网页登录。")
    user = public_user(conn, int(row[0]))
    assert user is not None
    return user


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_DAYS)
    conn.execute(
        """
        INSERT INTO sessions(user_id, token_hash, created_at, expires_at, last_seen_at)
        VALUES (?,?,?,?,?)
        """,
        (
            user_id,
            token_hash,
            now.isoformat(),
            expires.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    return token


def session_cookie(token: str, *, max_age: int = SESSION_DAYS * 86400) -> str:
    return f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}"


def clear_session_cookie() -> str:
    return f"{COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def lookup_session(
    conn: sqlite3.Connection, token: str | None
) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = _token_hash(token)
    row = conn.execute(
        """
        SELECT s.user_id, s.expires_at, s.id, u.is_local
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash=?
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        return None
    if int(row[3]) == 1:
        return None
    expires = _parse_dt(row[1])
    if expires is None or expires <= datetime.now(UTC):
        conn.execute("DELETE FROM sessions WHERE id=?", (row[2],))
        conn.commit()
        return None
    conn.execute(
        "UPDATE sessions SET last_seen_at=? WHERE id=?",
        (datetime.now(UTC).isoformat(), row[2]),
    )
    conn.commit()
    return public_user(conn, int(row[0]))


def revoke_session(conn: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
    conn.commit()


def parse_cookie(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            token = value.strip()
            return token or None
    return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
