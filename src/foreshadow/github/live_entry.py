"""Live GET of issues/PRs/CONTRIBUTING for Entry. Never mutates GitHub."""

from __future__ import annotations

import base64
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from foreshadow.entry import analyze_entry, persist_entry

FetchFn = Callable[[str], dict[str, Any]]


def features_from_live(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a live GitHub GET payload into analyze_entry features."""
    issues = [
        item
        for item in (payload.get("issues") or [])
        if isinstance(item, dict) and "pull_request" not in item
    ]
    prs = [item for item in (payload.get("prs") or []) if isinstance(item, dict)]
    help_titles: list[str] = []
    open_titles: list[str] = []
    help_n = 0
    unassigned_help = 0
    bug_n = 0
    for iss in issues:
        number = iss.get("number")
        title = str(iss.get("title") or "").strip()
        labels = {
            str(x).lower() if not isinstance(x, dict) else str(x.get("name") or "").lower()
            for x in (iss.get("labels") or [])
        }
        line = f"#{number} {title}".strip() if number is not None else title
        if line:
            open_titles.append(line)
        if labels & {
            "help wanted",
            "help-wanted",
            "good first issue",
            "good-first-issue",
        }:
            help_n += 1
            help_titles.append(line)
            assignees = iss.get("assignees") or []
            if not assignees:
                unassigned_help += 1
        if labels & {"bug", "crash", "defect", "regression"}:
            bug_n += 1
    contributing = str(payload.get("contributing") or "")
    readme = str(payload.get("readme") or payload.get("readme_excerpt") or "")
    return {
        "language": payload.get("language"),
        "full_name": payload.get("full_name"),
        "html_url": payload.get("html_url"),
        "description": payload.get("description"),
        "contributing": contributing,
        "readme": readme,
        "readme_excerpt": readme[:4000],
        "issues": issues,
        "prs": prs,
        "issue_sample_n": len(issues),
        "help_n": help_n,
        "unassigned_help": unassigned_help,
        "bug_n": bug_n,
        "help_issue_titles": help_titles,
        "open_issue_titles": open_titles,
        "pr_merged_sample_n": payload.get("pr_merged_sample_n", 4),
        "pr_accept_rate": payload.get("pr_accept_rate", 0.5),
        "pr_review_rate": payload.get("pr_review_rate", 0.5),
        "maint_touch": payload.get("maint_touch", 0.4),
        "tree_names": payload.get("tree_names")
        or ["README.md", "CONTRIBUTING.md", "src", "tests"],
    }


def fetch_live_payload(full_name: str) -> dict[str, Any]:
    """GET-only live snapshot. Never posts."""
    from foreshadow.config import load_config
    from foreshadow.github.client import GitHubClient, resolve_token
    from foreshadow.mission import parse_repo_name

    full_name = parse_repo_name(full_name)
    owner, name = full_name.split("/", 1)
    client = GitHubClient(resolve_token(), settings=load_config().github)
    repo = client.get(f"/repos/{owner}/{name}").json()
    if not isinstance(repo, dict):
        repo = {}
    issues_raw = client.get(
        f"/repos/{owner}/{name}/issues",
        params={"state": "open", "per_page": 50},
    ).json()
    issues = [
        item
        for item in (issues_raw if isinstance(issues_raw, list) else [])
        if isinstance(item, dict) and "pull_request" not in item
    ]
    prs_raw = client.get(
        f"/repos/{owner}/{name}/pulls",
        params={"state": "open", "per_page": 50},
    ).json()
    prs = [item for item in (prs_raw if isinstance(prs_raw, list) else []) if isinstance(item, dict)]
    return {
        "full_name": str(repo.get("full_name") or full_name),
        "html_url": str(repo.get("html_url") or f"https://github.com/{full_name}"),
        "language": repo.get("language"),
        "description": repo.get("description"),
        "default_branch": repo.get("default_branch") or "main",
        "contributing": _file_text(client, owner, name, "CONTRIBUTING.md"),
        "readme": _file_text(client, owner, name, "README.md")[:4000],
        "issues": issues,
        "prs": [
            {
                "number": p.get("number"),
                "title": p.get("title") or "",
                "body": p.get("body") or "",
                "url": p.get("html_url"),
            }
            for p in prs
        ],
    }


def refresh_entry_for_repo(
    conn: sqlite3.Connection,
    full_name: str,
    *,
    now: datetime,
    fetch: FetchFn | None = None,
    preferred_issue: int | None = None,
    source: str = "HUMAN_CONFIRM",
    language: str | None = None,
) -> dict[str, Any]:
    """Live-analyze a human-confirmed repo. Does not write Official ranks."""
    from foreshadow.mission import parse_repo_name

    full_name = parse_repo_name(full_name)
    payload = (fetch or fetch_live_payload)(full_name)
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("full_name", full_name)
    features = features_from_live(payload)
    lang = language or features.get("language")
    repo_id = _ensure_repo_row(conn, features, now=now)
    strategy = analyze_entry(
        features,
        now=now,
        language=str(lang) if lang else None,
        preferred_issue=preferred_issue,
    )
    if preferred_issue is not None and strategy.recommended.issue_number != preferred_issue:
        raise ValueError("confirmed issue is unavailable or ineligible; refusing fallback")
    persist_entry(conn, repo_id, strategy)
    return {
        "source": source,
        "strategy": strategy,
        "features": features,
        "payload": payload,
        "repo_id": repo_id,
    }


def extras_from_issue(issue: dict[str, Any] | None) -> dict[str, Any]:
    """Turn a live issue GET into StructuredTask extras. Does not invent files."""
    if not isinstance(issue, dict):
        return {}
    body = str(issue.get("body") or "")
    title = str(issue.get("title") or "")
    number = issue.get("number")
    url = issue.get("html_url") or issue.get("url")
    criteria = _bullets(body)
    files = _backticked_paths(body)
    tests = _test_commands(body)
    expected = ""
    for line in body.splitlines():
        text = line.strip()
        if text and not text.startswith("#") and not text.startswith("|"):
            expected = text[:400]
            break
    return {
        "issue_body": body,
        "expected_behavior": expected or title,
        "acceptance_criteria": criteria
        or [
            "Match the maintainer's 'What a fix looks like' section",
            "Do not fail when the related tool is not installed",
        ],
        "relevant_files": files,
        "test_commands": tests,
        "issue_url": url,
        "why": f"Human-confirmed issue #{number}: {title}" if number else title,
        "evidence": [url or body[:200]],
    }


def _ensure_repo_row(
    conn: sqlite3.Connection, features: dict[str, Any], *, now: datetime
) -> int:
    full = str(features.get("full_name") or "")
    row = conn.execute("SELECT id FROM repos WHERE full_name=?", (full,)).fetchone()
    if row:
        return int(row[0])
    owner, name = full.split("/", 1)
    stamp = now.isoformat() if now.tzinfo else now.replace(tzinfo=UTC).isoformat()
    conn.execute(
        """
        INSERT INTO repos(
          node_id, full_name, owner, name, html_url, description, language,
          status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            f"human:{full}",
            full,
            owner,
            name,
            features.get("html_url") or f"https://github.com/{full}",
            features.get("description"),
            features.get("language"),
            "active",
            stamp,
            stamp,
        ),
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM repos WHERE full_name=?", (full,)).fetchone()[0])


def _file_text(client: Any, owner: str, repo: str, path: str) -> str:
    from foreshadow.github.client import GitHubError

    try:
        resp = client.get(f"/repos/{owner}/{repo}/contents/{path}")
    except GitHubError as exc:
        if getattr(exc, "status", None) in {404, 410, 451}:
            return ""
        raise
    body = resp.json()
    if not isinstance(body, dict):
        return ""
    raw = body.get("content")
    if not raw:
        return ""
    try:
        return base64.b64decode("".join(str(raw).split())).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _bullets(body: str) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        text = line.strip()
        if text.startswith(("- ", "* ", "• ")):
            item = text[2:].strip()
            if item:
                out.append(item[:240])
        if len(out) >= 8:
            break
    return out


def _backticked_paths(body: str) -> list[str]:
    import re

    found: list[str] = []
    for match in re.finditer(r"`([^`]+)`", body):
        path = match.group(1).strip()
        if "/" in path and not path.startswith("http") and len(path) < 160:
            found.append(path)
    return list(dict.fromkeys(found))[:12]


def _test_commands(body: str) -> list[str]:
    import re

    out: list[str] = []
    for match in re.finditer(r"`((?:go test|pytest|npm test)[^`]*)`", body):
        out.append(match.group(1).strip())
    return list(dict.fromkeys(out))[:6]
