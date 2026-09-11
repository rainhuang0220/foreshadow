"""Board-facing two-gate actions. Default remote writes remain 0."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from foreshadow.contribution.approval import (
    ALLOWED_REMOTE_ACTIONS,
    BLOCKED_REMOTE_ACTIONS,
    current_snapshot,
    fields_from_review,
    invalidate_snapshot,
    matches_package,
)
from foreshadow.contribution.review import contribution_for_mission
from foreshadow.contribution.submit import (
    FakeGitHub,
    RemoteWriteRefused,
    refuse,
    submit_approved,
)
from foreshadow.mission import record_user_event, set_status


def _real_port(review: dict[str, Any]) -> Any:
    from foreshadow.github.approved_write import ApprovedGitHubPort

    package = review.get("package") if isinstance(review.get("package"), dict) else {}
    local_path = str(review.get("local_path") or "")
    repo_path = os.path.join(local_path, "repo") if local_path else None
    return ApprovedGitHubPort(
        bundle_path=package.get("git_bundle"),
        repo_path=repo_path,
        validated_base_sha=str(review.get("validated_base_sha") or ""),
        source_repo=str(review.get("repository") or ""),
    )


def assess_submission_readiness(
    *,
    review: dict[str, Any],
    fields: dict[str, Any],
    snapshot: dict[str, Any] | None,
    port: Any,
) -> dict[str, Any]:
    """Return the four facts required before the Board may claim READY."""
    snapshot_current = bool(snapshot and matches_package(snapshot, fields))
    package_complete = bool(
        str(fields.get("patch_commit_sha") or "").strip()
        and str(fields.get("validated_base_sha") or "").strip()
        and str(fields.get("repository") or "").strip()
        and str(fields.get("pr_title") or "").strip()
    )
    is_fake = bool(getattr(port, "is_fake", False))
    transport_ready = is_fake or bool(
        getattr(port, "transport_ready", lambda _sha: False)(
            str(fields.get("patch_commit_sha") or "")
        )
    )
    credential_ready = is_fake or bool(
        getattr(port, "credential_ready", lambda _repo: False)(
            str(fields.get("repository") or "")
        )
    )
    upstream_fresh = False
    preflight: dict[str, Any] | None = None
    if snapshot_current and snapshot is not None:
        try:
            from foreshadow.contribution.preflight import run_preflight

            preflight = run_preflight(port, snapshot, current_fields=fields)
            upstream_fresh = (
                bool(preflight.get("ok")) and preflight.get("status") == "EXACT"
            )
        except (
            RemoteWriteRefused,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            KeyError,
        ) as exc:
            preflight = {
                "ok": False,
                "status": "PREFLIGHT_UNAVAILABLE",
                "error": str(exc),
            }
    checks = {
        "write_transport_ready": transport_ready,
        "credential_ready": credential_ready,
        "snapshot_current": snapshot_current,
        "upstream_fresh": upstream_fresh,
        "package_complete": package_complete,
    }
    ready = (
        str(review.get("status") or "") == "WAITING_USER_APPROVAL"
        and str(fields.get("maintainer_output_safety") or "").upper() == "PASS"
        and all(checks.values())
    )
    if ready:
        display = "READY_FOR_HUMAN_SUBMIT"
    elif not snapshot_current:
        display = "APPROVAL_STALE"
    elif preflight and preflight.get("status") not in {
        "EXACT",
        "PREFLIGHT_UNAVAILABLE",
    }:
        display = (
            "NEEDS_REFRESH"
            if preflight.get("status")
            in {"DOCS_ONLY", "NON_OVERLAPPING", "NEEDS_REFRESH"}
            else str(preflight.get("status"))
        )
    elif not transport_ready:
        display = "WRITE_TRANSPORT_UNAVAILABLE"
    elif not credential_ready:
        display = "CREDENTIAL_REQUIRED"
    elif preflight and preflight.get("status") == "PREFLIGHT_UNAVAILABLE":
        display = "PREFLIGHT_UNAVAILABLE"
    elif not package_complete:
        display = "PACKAGE_INCOMPLETE"
    elif not upstream_fresh:
        display = "NEEDS_REFRESH"
    else:
        display = "NOT_READY_FOR_SUBMIT"
    return {
        "ready_for_human_submit": ready,
        "display_status": display,
        "approval_enabled": ready,
        "checks": checks,
        "preflight": preflight,
    }


def attach_submission_readiness(
    review: dict[str, Any], *, port: Any | None = None
) -> dict[str, Any]:
    fields = fields_from_review(review, mission_id=int(review["mission_id"]))
    snap = review.get("approval")
    if not isinstance(snap, dict) or not snap.get("approval_snapshot_id"):
        snap = None
    else:
        snap = {**fields, **snap}
    readiness = assess_submission_readiness(
        review=review,
        fields=fields,
        snapshot=snap,
        port=port or _real_port(review),
    )
    review.update(readiness)
    return review


def review_fields(
    conn: sqlite3.Connection, user_id: int, mission_id: int
) -> dict[str, Any]:
    review = contribution_for_mission(conn, user_id, mission_id)
    if review is None:
        raise LookupError("contribution not found")
    return fields_from_review(review, mission_id=mission_id)


def submit_preview(
    conn: sqlite3.Connection, user_id: int, mission_id: int
) -> dict[str, Any]:
    review = contribution_for_mission(conn, user_id, mission_id)
    if review is None:
        raise LookupError("contribution not found")
    fields = fields_from_review(review, mission_id=mission_id)
    snap = current_snapshot(conn, user_id=user_id, mission_id=mission_id)
    return {
        "ok": True,
        "confirm_required": True,
        "you_review_this_version": True,
        "approval_snapshot_id": None
        if snap is None
        else snap.get("approval_snapshot_id"),
        "approval_digest": None if snap is None else snap.get("approval_digest"),
        "patch_sha": fields.get("diff_sha256"),
        "will": list(ALLOWED_REMOTE_ACTIONS),
        "will_not": list(BLOCKED_REMOTE_ACTIONS),
        "will_zh": ["fork（如需要）", "push 一个贡献 branch", "创建一个 PR"],
        "will_not_zh": ["评论", "review", "merge", "force push"],
        "matched": bool(snap and matches_package(snap, fields)),
        "remote_writes": 0,
    }


def execute_gate2(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int,
    snapshot_id: int | None,
    confirm: bool,
    port: Any | None = None,
) -> dict[str, Any]:
    if not confirm:
        return submit_preview(conn, user_id, mission_id)
    review = contribution_for_mission(conn, user_id, mission_id)
    if review is None:
        return {**refuse("create_pr"), "error": "contribution not found"}
    from foreshadow.mission import load_mission_plan

    plan = load_mission_plan(conn, mission_id, user_id) or {}
    status = str(plan.get("status") or review.get("status") or "")
    if status == "SUBMITTED" and (plan.get("bound_pr") or review.get("bound_pr")):
        return {
            "ok": True,
            "status": "SUBMITTED",
            "pr": plan.get("bound_pr") or review.get("bound_pr"),
            "remote_writes": 0,
            "resumed": True,
        }
    if status != "WAITING_USER_APPROVAL":
        return {
            "ok": False,
            "blocked": True,
            "status": "NOT_WAITING_APPROVAL",
            "remote_writes": 0,
            "error": f"Gate 2 only from WAITING_USER_APPROVAL, not {status}",
        }
    fields = fields_from_review(review, mission_id=mission_id)
    snap = current_snapshot(conn, user_id=user_id, mission_id=mission_id)
    if snap is None:
        return {**refuse("create_pr"), "error": "no current approval snapshot"}
    if snapshot_id is not None and int(snap["approval_snapshot_id"]) != int(
        snapshot_id
    ):
        return {
            "ok": False,
            "status": "APPROVAL_STALE",
            "remote_writes": 0,
            "error": "snapshot id does not match the version on the Board",
        }
    if not matches_package(snap, fields):
        return {
            "ok": False,
            "status": "APPROVAL_STALE",
            "remote_writes": 0,
            "error": "package changed; Gate 2 required again",
        }
    if str(fields.get("maintainer_output_safety") or "").upper() != "PASS":
        return {
            "ok": False,
            "blocked": True,
            "status": "MAINTAINER_OUTPUT_UNSAFE",
            "remote_writes": 0,
            "error": "Maintainer-facing draft failed the output safety gate.",
        }
    if str(review.get("status") or "") == "SUBMITTED" and (
        review.get("bound_pr") or (review.get("package") or {}).get("bound_pr")
    ):
        return {
            "ok": True,
            "status": "SUBMITTED",
            "pr": review.get("bound_pr")
            or (review.get("package") or {}).get("bound_pr"),
            "remote_writes": 0,
            "resumed": True,
        }
    use_fake = os.environ.get("FORESHADOW_SUBMIT_FAKE") == "1" or (
        port is not None and getattr(port, "is_fake", False)
    )
    if not use_fake:
        from foreshadow.github.approved_write import write_token

        if write_token() is None:
            return {
                "ok": False,
                "blocked": True,
                "status": "WRITE_TOKEN_MISSING",
                "remote_writes": 0,
                "error": "提交引擎已就绪。设置 FORESHADOW_WRITE_TOKEN 后再点一次「提交到 GitHub」。",
                "will": list(ALLOWED_REMOTE_ACTIONS),
                "will_not": list(BLOCKED_REMOTE_ACTIONS),
            }
    worker = port if port is not None else (FakeGitHub() if use_fake else None)
    if worker is None:
        worker = _real_port(review)
    try:
        return submit_approved(
            conn,
            user_id=user_id,
            snapshot_id=int(snap["approval_snapshot_id"]),
            current_fields=fields,
            port=worker,
            allow_real_remote=True,
        )
    except (RemoteWriteRefused, LookupError, TypeError, ValueError, OSError) as exc:
        return {
            "ok": False,
            "blocked": True,
            "status": "SUBMIT_FAILED",
            "remote_writes": 0,
            "error": str(exc),
        }


def continue_local(
    conn: sqlite3.Connection, user_id: int, mission_id: int
) -> dict[str, Any]:
    snap = current_snapshot(conn, user_id=user_id, mission_id=mission_id)
    if snap is not None:
        invalidate_snapshot(conn, int(snap["approval_snapshot_id"]), user_id=user_id)
    set_status(conn, mission_id, user_id, "IMPLEMENTING")
    return {"ok": True, "status": "IMPLEMENTING", "remote_writes": 0}


def abandon_mission(
    conn: sqlite3.Connection, user_id: int, mission_id: int
) -> dict[str, Any]:
    return record_user_event(
        conn, user_id=user_id, mission_id=mission_id, event="abandoned"
    )


def reconcile_user_safe(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    from foreshadow.contribution.reconcile import bound_pr, reconcile_user
    from foreshadow.mission import list_missions

    if not any(bound_pr(m) for m in list_missions(conn, user_id)):
        return []
    try:
        from foreshadow.github.approved_write import ClientPullReader
        from foreshadow.github.client import GitHubClient, resolve_token

        token = resolve_token()
        if not token:
            return []
        reader = ClientPullReader(GitHubClient(token=token))
        return reconcile_user(conn, user_id=user_id, reader=reader)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError):
        return []
