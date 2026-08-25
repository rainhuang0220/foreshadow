from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from foreshadow.github.client import GitHubClient, GitHubError

BOT_LOGINS = frozenset(
    {
        "dependabot[bot]",
        "renovate[bot]",
        "github-actions[bot]",
        "copilot",
    }
)
BOT_LOGIN_RE = re.compile(r"(?i).*-bot$|\[bot\]$")


def is_bot(login: str | None, type_: str | None = None) -> bool:
    if type_ == "Bot":
        return True
    if not login:
        return False
    if login in BOT_LOGINS or login.lower() == "copilot":
        return True
    return bool(BOT_LOGIN_RE.search(login))


def fetch_contributors(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """K18: stop at a short page, identified ≥ 500, or C ≥ 80."""
    page = 1
    out: list[dict[str, Any]] = []
    identified = 0
    anon = 0
    while True:
        resp = client.get(
            f"/repos/{owner}/{repo}/contributors",
            params={"per_page": per_page, "anon": "1", "page": page},
        )
        if resp.status_code == 204:
            break
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            if row.get("type") == "Anonymous" or not row.get("login"):
                anon += 1
            else:
                identified += 1
        if len(rows) < per_page or identified >= 500 or (identified + anon) >= 80:
            break
        page += 1
    return out


def fetch_commits(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: datetime,
    *,
    per_page: int = 100,
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    page = 1
    out: list[dict[str, Any]] = []
    since_s = since.isoformat()
    while page <= max_pages:
        resp = client.get(
            f"/repos/{owner}/{repo}/commits",
            params={"since": since_s, "per_page": per_page, "page": page},
        )
        if resp.status_code == 204:
            break
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < per_page:
            break
        page += 1
    return out


def fetch_root_contents(
    client: GitHubClient, owner: str, repo: str
) -> list[dict[str, Any]]:
    resp = client.get(f"/repos/{owner}/{repo}/contents")
    if resp.status_code == 204:
        return []
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def fetch_workflows(client: GitHubClient, owner: str, repo: str) -> dict[str, Any]:
    resp = client.get(f"/repos/{owner}/{repo}/actions/workflows")
    body = resp.json()
    return body if isinstance(body, dict) else {}


def fetch_community_profile(
    client: GitHubClient, owner: str, repo: str
) -> dict[str, Any]:
    resp = client.get(f"/repos/{owner}/{repo}/community/profile")
    body = resp.json()
    return body if isinstance(body, dict) else {}


def fetch_releases(
    client: GitHubClient, owner: str, repo: str, *, per_page: int = 10
) -> list[dict[str, Any]]:
    resp = client.get(
        f"/repos/{owner}/{repo}/releases", params={"per_page": per_page, "page": 1}
    )
    if resp.status_code == 204:
        return []
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def content_exists(client: GitHubClient, owner: str, repo: str, path: str) -> bool:
    url = (
        f"{client.settings.api_url.rstrip('/')}"
        f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}"
    )
    try:
        resp = client.request("HEAD", url)
    except GitHubError as exc:
        if exc.status in (404, 410, 451):
            return False
        raise
    return resp.status_code == 200
