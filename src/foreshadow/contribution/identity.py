"""Mission identity: mission_id + issue, never latest-row-for-repo."""

from __future__ import annotations

from typing import Any

REVIEWABLE = frozenset(
    {
        "WAITING_USER_APPROVAL",
        "DRAFT_READY",
        "SUBMITTED",
        "REVIEWING",
        "WAITING_MAINTAINER",
        "IMPLEMENTING",
        "VALIDATING",
        "PACKAGING",
        "INVESTIGATING",
        "REPRODUCING",
        "LOCAL_SETUP",
        "MISSION_READY",
        "DISCUSSING",
    }
)
TERMINAL = frozenset({"MERGED", "ABANDONED", "BLOCKED"})
QUEUE_STATUSES = frozenset({"WAITING_USER_APPROVAL", "DRAFT_READY"})
_PRIORITY = (
    "WAITING_USER_APPROVAL",
    "DRAFT_READY",
    "SUBMITTED",
    "REVIEWING",
    "WAITING_MAINTAINER",
    "IMPLEMENTING",
    "VALIDATING",
    "PACKAGING",
)


def display_status(status: str) -> str:
    if str(status or "") == "WAITING_USER_APPROVAL":
        return "READY_FOR_HUMAN_SUBMIT"
    return str(status or "")


def issue_from_plan(plan: dict[str, Any]) -> int | None:
    raw_n = plan.get("issue_number")
    if isinstance(raw_n, int) and raw_n > 0:
        return raw_n
    if isinstance(raw_n, str) and raw_n.lstrip("#").isdigit():
        return int(raw_n.lstrip("#"))
    url = plan.get("issue_url")
    if isinstance(url, str) and "/issues/" in url:
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        if tail.isdigit():
            return int(tail)
    for key in ("preferred_issue", "cited_issue", "active_entry_target"):
        raw = plan.get(key)
        if isinstance(raw, int) and raw > 0:
            return raw
        if isinstance(raw, dict):
            n = raw.get("number") or raw.get("issue_number")
            if isinstance(n, int) and n > 0:
                return n
            if isinstance(n, str) and n.lstrip("#").isdigit():
                return int(n.lstrip("#"))
        if isinstance(raw, str) and raw.lstrip("#").isdigit():
            return int(raw.lstrip("#"))
    rec = plan.get("entry_strategy") if isinstance(plan.get("entry_strategy"), dict) else {}
    rec = rec.get("recommended") if isinstance(rec, dict) else {}
    if isinstance(rec, dict):
        n = rec.get("issue_number") or rec.get("number")
        if isinstance(n, int) and n > 0:
            return n
    return None


def is_reviewable(status: str) -> bool:
    return str(status or "") in REVIEWABLE


def is_queueable(status: str) -> bool:
    return str(status or "") in QUEUE_STATUSES


def missions_for_repo(
    missions: list[dict[str, Any]], full_name: str
) -> list[dict[str, Any]]:
    return [m for m in missions if m.get("full_name") == full_name]


def pick_active_for_repo(missions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer an open reviewable mission. MERGED never beats WAITING."""
    open_rows = [
        m
        for m in missions
        if str(m.get("status") or "") not in TERMINAL
        and str(m.get("status") or "") != "ABANDONED"
    ]
    if open_rows:
        def key(m: dict[str, Any]) -> tuple[int, int]:
            st = str(m.get("status") or "")
            try:
                pri = _PRIORITY.index(st)
            except ValueError:
                pri = len(_PRIORITY)
            return (pri, -int(m.get("id") or 0))

        return min(open_rows, key=key)
    rest = [m for m in missions if str(m.get("status") or "") != "ABANDONED"]
    if not rest:
        return None
    return max(rest, key=lambda m: int(m.get("id") or 0))


def require_mission_id(
    missions: list[dict[str, Any]],
    *,
    full_name: str,
    mission_id: int | None = None,
    issue_number: int | None = None,
) -> dict[str, Any]:
    rows = missions_for_repo(missions, full_name)
    if mission_id is not None:
        for m in rows:
            if int(m.get("id") or 0) == int(mission_id):
                return m
        raise LookupError(f"no mission {mission_id} for {full_name}")
    if issue_number is not None:
        hits = [m for m in rows if issue_from_plan(m) == int(issue_number)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise LookupError(
                f"multiple missions for {full_name}#{issue_number}; pass mission_id"
            )
        raise LookupError(f"no mission for {full_name}#{issue_number}")
    if len(rows) == 1:
        return rows[0]
    raise LookupError(
        f"{full_name} has {len(rows)} missions; pass --mission-id"
    )
