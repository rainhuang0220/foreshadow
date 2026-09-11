"""Two human gates. Local phases between them never wait for extra approval."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from foreshadow.contribution.executor import ContributionExecutor, ContributionJob
from foreshadow.mission import create_for_user, load_mission_plan, set_status

LOCAL_PHASES = (
    "INVESTIGATING",
    "REPRODUCING",
    "IMPLEMENTING",
    "VALIDATING",
    "PACKAGING",
)


def authorize_entry(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str,
    data_dir: Path,
    issue_number: int | None = None,
    live: bool = False,
    contribute: bool = True,
    executor: ContributionExecutor | None = None,
) -> dict[str, Any]:
    """GATE 1 — user authorizes local work on one issue. No remote writes."""
    mission = create_for_user(
        conn,
        user_id=user_id,
        full_name=full_name,
        data_dir=data_dir,
        issue_number=issue_number,
        source="HUMAN_CONFIRM",
        live=live,
    )
    mid = int(mission.id or 0)
    plan0 = load_mission_plan(conn, mid, user_id) or mission.as_dict()
    if str(plan0.get("status") or "") not in {
        "WAITING_USER_APPROVAL",
        "SUBMITTED",
        "REVIEWING",
        "WAITING_MAINTAINER",
        "MERGED",
        "ABANDONED",
        "BLOCKED",
    }:
        run_autonomous_local(conn, user_id=user_id, mission_id=mid)
    job: ContributionJob | None = None
    if contribute:
        from foreshadow.contribution.local import start_local_contribution

        job = start_local_contribution(
            conn,
            user_id=user_id,
            full_name=full_name,
            data_dir=data_dir,
            executor=executor,
            mission_id=mid,
        )
        set_status(conn, mid, user_id, "WAITING_USER_APPROVAL")
    plan = load_mission_plan(conn, mid, user_id) or mission.as_dict()
    return {
        "gate": 1,
        "mission": plan,
        "job": job,
        "status": plan.get("status"),
        "remote_writes": 0,
    }


def run_autonomous_local(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int,
    runner: Any | None = None,
) -> list[str]:
    """Advance observable local phases. Does not prompt and does not write remote."""
    seen: list[str] = []
    for dest in LOCAL_PHASES:
        set_status(conn, mission_id, user_id, dest)  # type: ignore[arg-type]
        seen.append(dest)
        if runner is not None:
            runner(dest)
    set_status(conn, mission_id, user_id, "WAITING_USER_APPROVAL")
    seen.append("WAITING_USER_APPROVAL")
    return seen
