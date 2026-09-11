"""Immutable Gate-2 approval snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

ALLOWED_REMOTE_ACTIONS = ("fork", "push_branch", "create_pr")
BLOCKED_REMOTE_ACTIONS = (
    "comment",
    "issue_comment",
    "review",
    "reaction",
    "merge",
    "force_push",
    "extra_commit",
)


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


FIELD_KEYS = (
    "mission_id",
    "repository",
    "issue_number",
    "issue_url",
    "base_repo",
    "base_branch",
    "validated_base_sha",
    "patch_commit_sha",
    "diff_sha256",
    "branch_name",
    "pr_title",
    "pr_body",
    "test_evidence_digest",
    "qa_verdict",
    "maintainer_output_safety",
    "freshness",
    "planned_remote_actions",
    "blocked_remote_actions",
)


def canonical_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in FIELD_KEYS:
        if key not in fields:
            continue
        value = fields[key]
        if key == "planned_remote_actions":
            value = list(value)
        if key == "blocked_remote_actions":
            value = list(value)
        out[key] = value
    return out


def compute_digest(fields: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(canonical_fields(fields)).encode("utf-8")).hexdigest()


def snapshot_fields(
    *,
    mission_id: int,
    repository: str,
    issue_number: int,
    issue_url: str,
    base_repo: str,
    base_branch: str,
    validated_base_sha: str,
    patch_commit_sha: str,
    diff_sha256: str,
    branch_name: str,
    pr_title: str,
    pr_body: str,
    test_evidence_digest: str,
    qa_verdict: str,
    maintainer_output_safety: str,
    freshness: str,
    planned_remote_actions: tuple[str, ...] = ALLOWED_REMOTE_ACTIONS,
) -> dict[str, Any]:
    return {
        "mission_id": int(mission_id),
        "repository": repository,
        "issue_number": int(issue_number),
        "issue_url": issue_url,
        "base_repo": base_repo,
        "base_branch": base_branch,
        "validated_base_sha": validated_base_sha,
        "patch_commit_sha": patch_commit_sha,
        "diff_sha256": diff_sha256,
        "branch_name": branch_name,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "test_evidence_digest": test_evidence_digest,
        "qa_verdict": qa_verdict,
        "maintainer_output_safety": maintainer_output_safety,
        "freshness": freshness,
        "planned_remote_actions": list(planned_remote_actions),
        "blocked_remote_actions": list(BLOCKED_REMOTE_ACTIONS),
    }


def create_snapshot(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    fields: dict[str, Any],
) -> dict[str, Any]:
    digest = compute_digest(fields)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        UPDATE approval_snapshots
        SET status='invalid', invalidated_at=?
        WHERE user_id=? AND mission_id=? AND status='current'
        """,
        (now, user_id, int(fields["mission_id"])),
    )
    cur = conn.execute(
        """
        INSERT INTO approval_snapshots(
          user_id, mission_id, digest, snapshot_json, status, created_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            user_id,
            int(fields["mission_id"]),
            digest,
            _canon({**fields, "approval_digest": digest}),
            "current",
            now,
        ),
    )
    conn.commit()
    return load_snapshot(conn, int(cur.lastrowid), user_id=user_id)


def load_snapshot(
    conn: sqlite3.Connection, snapshot_id: int, *, user_id: int
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, mission_id, digest, snapshot_json, status, created_at, invalidated_at
        FROM approval_snapshots WHERE id=? AND user_id=?
        """,
        (snapshot_id, user_id),
    ).fetchone()
    if row is None:
        raise LookupError("approval snapshot not found")
    body = json.loads(row[3])
    body.update(
        {
            "approval_snapshot_id": row[0],
            "mission_id": row[1],
            "approval_digest": row[2],
            "status": row[4],
            "created_at": row[5],
            "invalidated_at": row[6],
        }
    )
    return body


def current_snapshot(
    conn: sqlite3.Connection, *, user_id: int, mission_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id FROM approval_snapshots
        WHERE user_id=? AND mission_id=? AND status='current'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, mission_id),
    ).fetchone()
    if row is None:
        return None
    return load_snapshot(conn, int(row[0]), user_id=user_id)


def matches_package(snapshot: dict[str, Any], fields: dict[str, Any]) -> bool:
    if str(snapshot.get("status") or "") != "current":
        return False
    return compute_digest(fields) == compute_digest(snapshot) or compute_digest(
        fields
    ) == str(snapshot.get("approval_digest") or "")


def _heuristic_semantic(payload: dict[str, Any]) -> dict[str, Any]:
    from foreshadow.contribution.maintainer.lint import default_semantic_reasons

    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    text = f"{draft.get('title') or ''}\n{draft.get('body') or ''}"
    reasons = default_semantic_reasons(text)
    return {"ok": not reasons, "reasons": reasons}


def maintainer_safety_from_review(review: dict[str, Any]) -> str:
    """Evaluate leak / privacy / AI-attribution. Grounding style does not flip PASS."""
    from foreshadow.contribution.maintainer import (
        evaluate_maintainer_output,
        project_maintainer_context,
    )

    draft = review.get("pr_draft") if isinstance(review.get("pr_draft"), dict) else {}
    existing = draft.get("safety") if isinstance(draft.get("safety"), dict) else {}
    if existing.get("ok") is False:
        checks = existing.get("checks") if isinstance(existing.get("checks"), dict) else {}
        if any(
            checks.get(name) == "FAIL"
            for name in ("internal_leakage", "privacy", "ai_self_reference")
        ) or any(
            "ai" in str(r).lower() or "leak" in str(r).lower() or "cursor" in str(r).lower()
            for r in (existing.get("reasons") or existing.get("summary") or [])
        ):
            return "FAIL"
    pkg = review.get("package") if isinstance(review.get("package"), dict) else {}
    ctx = project_maintainer_context(
        repository=str(review.get("repository") or ""),
        diff=str(review.get("diff") or ""),
        files=list(review.get("files_changed") or pkg.get("files_changed") or []),
        issue_title=str(review.get("title") or pkg.get("issue_title") or ""),
        issue_body=str(pkg.get("issue_body") or ""),
        issue_number=review.get("issue_number"),
        tests_ok=bool(review.get("tests_ok") or review.get("qa_ok")),
    )
    gate = evaluate_maintainer_output(
        str(review.get("pr_title") or ""),
        str(review.get("pr_body") or ""),
        ctx,
        semantic_reviewer=_heuristic_semantic,
    )
    for name in ("internal_leakage", "privacy", "ai_self_reference"):
        if gate.checks.get(name) == "FAIL":
            return "FAIL"
    return "PASS"


def fields_from_review(review: dict[str, Any], *, mission_id: int) -> dict[str, Any]:
    from foreshadow.contribution.import_store import sha256_text

    pkg = review.get("package") if isinstance(review.get("package"), dict) else {}
    impl = review.get("implementation") if isinstance(review.get("implementation"), dict) else {}
    diff = str(review.get("diff") or "")
    out = snapshot_fields(
        mission_id=int(mission_id),
        repository=str(review.get("repository") or ""),
        issue_number=int(review.get("issue_number") or 0),
        issue_url=str(review.get("issue_url") or ""),
        base_repo=str(review.get("repository") or ""),
        base_branch=str(review.get("base_branch") or "main"),
        validated_base_sha=str(
            review.get("validated_base_sha") or impl.get("upstream_head") or ""
        ),
        patch_commit_sha=str(
            review.get("patch_commit_sha") or impl.get("patch_commit_sha") or ""
        ),
        diff_sha256=sha256_text(diff) if diff else str(
            review.get("diff_sha256") or pkg.get("diff_sha256") or ""
        ),
        branch_name=str(
            review.get("branch_name")
            or impl.get("branch")
            or (
                f"foreshadow/entry-{int(review.get('issue_number') or 0)}"
                if review.get("issue_number")
                else "foreshadow/entry"
            )
        ),
        pr_title=str(review.get("pr_title") or ""),
        pr_body=str(review.get("pr_body") or ""),
        test_evidence_digest=sha256_text(
            json.dumps(pkg.get("evidence") or review.get("tests") or {}, sort_keys=True)
        ),
        qa_verdict=str(review.get("qa") or "PASS"),
        maintainer_output_safety=maintainer_safety_from_review(review),
        freshness=str(review.get("freshness") or "UNKNOWN"),
    )
    out["files_changed"] = list(
        review.get("files_changed") or pkg.get("files_changed") or []
    )
    return out


def invalidate_snapshot(
    conn: sqlite3.Connection, snapshot_id: int, *, user_id: int
) -> None:
    conn.execute(
        """
        UPDATE approval_snapshots
        SET status='invalid', invalidated_at=?
        WHERE id=? AND user_id=?
        """,
        (datetime.now(UTC).isoformat(), snapshot_id, user_id),
    )
    conn.commit()
