"""GitHub OAuth web flow for identity only. Access tokens are not stored."""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from foreshadow.auth import AuthError

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
STATE_MINUTES = 10


def oauth_client_id() -> str:
    return (os.environ.get("FORESHADOW_GITHUB_OAUTH_CLIENT_ID") or "").strip()


def oauth_client_secret() -> str:
    return (os.environ.get("FORESHADOW_GITHUB_OAUTH_CLIENT_SECRET") or "").strip()


def oauth_configured() -> bool:
    return bool(oauth_client_id() and oauth_client_secret())


def callback_url(public_url: str, host: str) -> str:
    base = (public_url or "").strip().rstrip("/")
    if base:
        return f"{base}/api/auth/github/callback"
    host = (host or "127.0.0.1").strip()
    scheme = "http"
    return f"{scheme}://{host}/api/auth/github/callback"


def start_login(
    conn: sqlite3.Connection, *, redirect_uri: str, next_path: str = "/"
) -> str:
    if not oauth_configured():
        raise AuthError(
            "未配置 GitHub OAuth（需要 FORESHADOW_GITHUB_OAUTH_CLIENT_ID）。"
        )
    state = secrets.token_urlsafe(24)
    now = datetime.now(UTC)
    conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now.isoformat(),))
    conn.execute(
        """
        INSERT INTO oauth_states(state, created_at, expires_at, next_path)
        VALUES (?,?,?,?)
        """,
        (
            state,
            now.isoformat(),
            (now + timedelta(minutes=STATE_MINUTES)).isoformat(),
            next_path or "/",
        ),
    )
    conn.commit()
    query = urlencode(
        {
            "client_id": oauth_client_id(),
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def consume_state(conn: sqlite3.Connection, state: str) -> str | None:
    raw = (state or "").strip()
    if not raw:
        return None
    now = datetime.now(UTC).isoformat()
    row = conn.execute(
        "SELECT next_path FROM oauth_states WHERE state=? AND expires_at > ?",
        (raw, now),
    ).fetchone()
    conn.execute("DELETE FROM oauth_states WHERE state=?", (raw,))
    conn.commit()
    if row is None:
        return None
    nxt = str(row[0] or "/")
    if not nxt.startswith("/"):
        return "/"
    return nxt


def fetch_github_identity(code: str, redirect_uri: str) -> dict[str, Any]:
    if not oauth_configured():
        raise AuthError("未配置 GitHub OAuth。")
    if not (code or "").strip():
        raise AuthError("GitHub 未返回授权码。")
    with httpx.Client(timeout=20.0) as client:
        token_res = client.post(
            TOKEN_URL,
            data={
                "client_id": oauth_client_id(),
                "client_secret": oauth_client_secret(),
                "code": code.strip(),
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        try:
            token_res.raise_for_status()
            payload = token_res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError("无法向 GitHub 换取登录令牌。") from exc
        access = str((payload or {}).get("access_token") or "")
        if not access:
            raise AuthError("GitHub 拒绝了登录。")
        user_res = client.get(
            USER_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access}",
                "User-Agent": "foreshadow-radar",
            },
        )
        try:
            user_res.raise_for_status()
            user = user_res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError("无法读取 GitHub 用户。") from exc
    login = str((user or {}).get("login") or "")
    try:
        github_id = int((user or {}).get("id"))
    except (TypeError, ValueError):
        github_id = 0
    if not login or github_id <= 0:
        raise AuthError("GitHub 未返回有效用户。")
    return {"id": github_id, "login": login}
