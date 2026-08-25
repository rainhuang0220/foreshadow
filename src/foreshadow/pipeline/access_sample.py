"""GET-only medium Access sample. Does not recompute official v1 scores."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from foreshadow.github.client import GitHubError
from foreshadow.github.rest import fetch_closed_pulls
from foreshadow.pipeline.hydrate import _pr_acceptance_from_pulls

PR_KEYS = (
    "pr_merged_sample_n",
    "pr_external_merged_n",
    "pr_accept_rate",
    "pr_reviewed_n",
    "pr_review_rate",
)


def sample_medium_access(
    conn: sqlite3.Connection,
    client: Any,
    *,
    limit: int = 30,
) -> dict[str, Any]:
    """Fill pr_* on phase=M snapshots that have no PR sample. GET only."""
    rows = conn.execute(
        """
        SELECT s.repo_id, s.snapshot_date, s.features_json, r.full_name
        FROM snapshots s
        JOIN repos r ON r.id = s.repo_id
        JOIN (
          SELECT repo_id, MAX(snapshot_date) AS d FROM snapshots GROUP BY repo_id
        ) latest ON latest.repo_id = s.repo_id AND latest.d = s.snapshot_date
        ORDER BY s.repo_id
        """
    ).fetchall()
    updated = 0
    skipped = 0
    failed = 0
    known = 0
    for repo_id, day, raw, full_name in rows:
        try:
            feat = json.loads(raw or "{}")
        except json.JSONDecodeError:
            feat = {}
        if not isinstance(feat, dict):
            feat = {}
        if feat.get("phase") != "M":
            continue
        if feat.get("pr_merged_sample_n") is not None:
            skipped += 1
            continue
        if "/" not in str(full_name or ""):
            failed += 1
            continue
        owner, name = str(full_name).split("/", 1)
        try:
            pulls = fetch_closed_pulls(client, owner, name)
        except GitHubError:
            failed += 1
            continue
        n, ext, rate, rev, rrate = _pr_acceptance_from_pulls(pulls)
        feat["pr_merged_sample_n"] = n
        feat["pr_external_merged_n"] = ext
        feat["pr_accept_rate"] = rate
        feat["pr_reviewed_n"] = rev
        feat["pr_review_rate"] = rrate
        conn.execute(
            "UPDATE snapshots SET features_json=? WHERE repo_id=? AND snapshot_date=?",
            (json.dumps(feat, ensure_ascii=False), repo_id, day),
        )
        updated += 1
        if rate is not None or n == 0:
            known += 1
        if updated >= limit:
            break
    conn.commit()
    return {
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "note": "Official v1 scores are unchanged. Access is read from features on the Board.",
    }
