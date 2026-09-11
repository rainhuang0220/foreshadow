"""GET-only outcome reconciliation bound to mission_id + exact PR."""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from foreshadow.mission import load_mission_plan, record_user_event


class PullReader(Protocol):
    def get_pull(self, repo: str, number: int) -> dict[str, Any]: ...


def bound_pr(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    for key in ("bound_pr", "submitted_pr", "pr"):
        raw = plan.get(key)
        if isinstance(raw, dict) and raw.get("number"):
            return raw
    return None


def reconcile_mission(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int,
    reader: PullReader,
) -> dict[str, Any]:
    plan = load_mission_plan(conn, mission_id, user_id)
    if plan is None:
        return {"ok": False, "reason": "mission_not_found"}
    pr = bound_pr(plan)
    if pr is None:
        return {"ok": True, "status": plan.get("status"), "changed": False}
    repo = str(plan.get("full_name") or "")
    info = reader.get_pull(repo, int(pr["number"]))
    merged = bool(info.get("merged") or info.get("merged_at"))
    state = str(info.get("state") or "").lower()
    if merged and str(plan.get("status") or "") != "MERGED":
        out = record_user_event(
            conn, user_id=user_id, mission_id=mission_id, event="pr_merged"
        )
        return {
            "ok": True,
            "changed": True,
            "status": out.get("status"),
            "pr": int(pr["number"]),
        }
    if state == "closed" and not merged and str(plan.get("status") or "") not in {
        "BLOCKED",
        "ABANDONED",
        "MERGED",
    }:
        out = record_user_event(
            conn, user_id=user_id, mission_id=mission_id, event="pr_rejected"
        )
        return {
            "ok": True,
            "changed": True,
            "status": out.get("status"),
            "pr": int(pr["number"]),
        }
    return {"ok": True, "changed": False, "status": plan.get("status"), "pr": int(pr["number"])}


def reconcile_user(
    conn: sqlite3.Connection, *, user_id: int, reader: PullReader
) -> list[dict[str, Any]]:
    from foreshadow.mission import list_missions

    out: list[dict[str, Any]] = []
    for plan in list_missions(conn, user_id):
        if not bound_pr(plan):
            continue
        if str(plan.get("status") or "") in {"MERGED", "ABANDONED"}:
            continue
        out.append(
            reconcile_mission(
                conn, user_id=user_id, mission_id=int(plan["id"]), reader=reader
            )
        )
    return out
