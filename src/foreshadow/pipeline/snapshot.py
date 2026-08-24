from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any


def _total(obj: Any) -> int | None:
    if isinstance(obj, dict) and obj.get("totalCount") is not None:
        try:
            return int(obj["totalCount"])
        except (TypeError, ValueError):
            return None
    return None


def _topics(repo: dict[str, Any]) -> list[str]:
    raw = repo.get("repositoryTopics") or {}
    nodes = raw.get("nodes") if isinstance(raw, dict) else None
    out: list[str] = []
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if not isinstance(node, dict):
            continue
        topic = node.get("topic")
        name = topic.get("name") if isinstance(topic, dict) else None
        if name:
            out.append(str(name))
    return out


def _commit_date(repo: dict[str, Any]) -> str | None:
    ref = repo.get("defaultBranchRef")
    if not isinstance(ref, dict):
        return None
    target = ref.get("target")
    if not isinstance(target, dict):
        return None
    val = target.get("committedDate")
    return str(val) if val else None


def payload_from_graphql(
    repo: dict[str, Any],
    *,
    captured_at: str,
    created_at: str | None = None,
    features_json: str = "{}",
    contributor_count: int | None = None,
    contributor_identified: int | None = None,
    contributor_anon: int | None = None,
    contributor_censored: int | None = None,
    unique_committers_30d: int | None = None,
) -> dict[str, Any]:
    """Map GraphQL Repository fields. Never REST open_issues_count / watchers_count."""
    created = created_at or repo.get("createdAt")
    payload = {
        "stars": repo.get("stargazerCount"),
        "forks": repo.get("forkCount"),
        "open_issues": _total(repo.get("issuesOpen")),
        "closed_issues": _total(repo.get("issuesClosed")),
        "open_prs": _total(repo.get("prsOpen")),
        "watchers": None,
        "last_pushed_at": repo.get("pushedAt"),
        "last_commit_at": _commit_date(repo),
        "contributor_count": contributor_count,
        "contributor_identified": contributor_identified,
        "contributor_anon": contributor_anon,
        "contributor_censored": contributor_censored,
        "unique_committers_30d": unique_committers_30d,
        "discussions_count": _total(repo.get("discussions")),
        "topics_json": json.dumps(_topics(repo), ensure_ascii=False),
        "features_json": features_json or "{}",
        "created_at": created,
        "captured_at": captured_at,
    }
    payload["completeness"] = completeness(payload)
    return payload


def completeness(payload: dict[str, Any]) -> float:
    keys = [
        "stars",
        "forks",
        "open_issues",
        "open_prs",
        "last_pushed_at",
        "created_at",
    ]
    phase_b = payload.get("contributor_count") is not None or (
        (payload.get("features_json") or "{}") not in ("{}", "", "null")
    )
    if phase_b:
        keys.append("contributor_count")
    present = sum(1 for key in keys if payload.get(key) is not None)
    expected = len(keys)
    if phase_b:
        expected += 1
        feat = payload.get("features_json") or "{}"
        if feat not in ("{}", "", "null"):
            present += 1
    return present / expected if expected else 0.0


def upsert_snapshot(
    conn: sqlite3.Connection,
    repo_id: int,
    snapshot_date: date | str,
    payload: dict[str, Any],
) -> None:
    day = (
        snapshot_date.isoformat()
        if isinstance(snapshot_date, date)
        else str(snapshot_date)
    )
    feat = payload.get("features_json") or "{}"
    if not isinstance(feat, str):
        feat = json.dumps(feat, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO snapshots(
          repo_id, snapshot_date, captured_at, stars, forks, open_issues,
          closed_issues, open_prs, watchers, last_pushed_at, last_commit_at,
          contributor_count, contributor_identified, contributor_anon,
          contributor_censored, unique_committers_30d, discussions_count,
          topics_json, features_json, completeness
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(repo_id, snapshot_date) DO UPDATE SET
          captured_at=excluded.captured_at,
          stars=excluded.stars,
          forks=excluded.forks,
          open_issues=excluded.open_issues,
          closed_issues=excluded.closed_issues,
          open_prs=excluded.open_prs,
          watchers=NULL,
          last_pushed_at=excluded.last_pushed_at,
          last_commit_at=excluded.last_commit_at,
          contributor_count=excluded.contributor_count,
          contributor_identified=excluded.contributor_identified,
          contributor_anon=excluded.contributor_anon,
          contributor_censored=excluded.contributor_censored,
          unique_committers_30d=excluded.unique_committers_30d,
          discussions_count=excluded.discussions_count,
          topics_json=excluded.topics_json,
          features_json=excluded.features_json,
          completeness=excluded.completeness
        """,
        (
            repo_id,
            day,
            payload.get("captured_at"),
            payload.get("stars"),
            payload.get("forks"),
            payload.get("open_issues"),
            payload.get("closed_issues"),
            payload.get("open_prs"),
            None,
            payload.get("last_pushed_at"),
            payload.get("last_commit_at"),
            payload.get("contributor_count"),
            payload.get("contributor_identified"),
            payload.get("contributor_anon"),
            payload.get("contributor_censored"),
            payload.get("unique_committers_30d"),
            payload.get("discussions_count"),
            payload.get("topics_json") or "[]",
            feat,
            payload.get("completeness", completeness(payload)),
        ),
    )
