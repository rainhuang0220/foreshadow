"""Entry Mission: local plan + optional clone. Never posts to GitHub."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import compute_access
from foreshadow.pipeline.activity import compute_activity
from foreshadow.pipeline.s1 import compute_s1
from foreshadow.pipeline.strategy import StrategyResult, recommend_entry

Status = Literal[
    "DISCOVERED",
    "INTERESTED",
    "INVESTIGATING",
    "MISSION_READY",
    "LOCAL_SETUP",
    "REPRODUCING",
    "DISCUSSING",
    "IMPLEMENTING",
    "DRAFT_READY",
    "WAITING_USER_APPROVAL",
    "SUBMITTED",
    "REVIEWING",
    "MERGED",
    "FOLLOW_UP",
    "ABANDONED",
    "BLOCKED",
    "WAITING_MAINTAINER",
]

REMOTE_ACTIONS = frozenset(
    {"post_issue", "post_discussion", "push_branch", "create_pr", "comment", "review", "merge"}
)


@dataclass
class Mission:
    full_name: str
    status: Status
    strategy: StrategyResult
    stage: str | None
    earlyness: float | None
    evidence: float | None
    window: float | None
    access: float | None
    why_now: list[str]
    needs_user_approval: bool
    local_path: str | None = None
    id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "status": self.status,
            "strategy": self.strategy.as_dict(),
            "stage": self.stage,
            "earlyness": self.earlyness,
            "evidence": self.evidence,
            "opportunity_window": self.window,
            "access": self.access,
            "why_now": list(self.why_now),
            "steps_zh": list(self.strategy.steps_zh),
            "difficulty": self.strategy.difficulty,
            "effort": self.strategy.effort,
            "needs_user_approval": self.needs_user_approval,
            "local_path": self.local_path,
            "remote_blocked": (
                "等待你的确认才能执行任何远程 GitHub 操作。"
            ),
        }


def build_mission(
    full_name: str,
    *,
    feat: FeaturesBlob | None = None,
    age_days: float | None = None,
    contributors: int | None = None,
    stars: float | None = None,
    pushed_age_days: int | None = None,
    unique_issue_authors: int | None = None,
) -> Mission:
    feat = feat or FeaturesBlob()
    act = compute_activity(feat)
    acc = compute_access(feat)
    s1 = compute_s1(
        age_days=age_days,
        contributors=contributors,
        stars=stars,
        pushed_age_days=pushed_age_days,
        unique_issue_authors=unique_issue_authors,
        feat=feat,
        activity=act,
    )
    strat = recommend_entry(feat, s1=s1, access=acc)
    why = [
        f"阶段 {s1.stage}",
        *s1.earlyness_plus[:2],
        *s1.evidence_plus[:2],
        *strat.why,
    ]
    return Mission(
        full_name=full_name,
        status="MISSION_READY",
        strategy=strat,
        stage=s1.stage,
        earlyness=s1.earlyness,
        evidence=s1.evidence,
        window=s1.window,
        access=acc.score,
        why_now=[w for w in why if w],
        needs_user_approval=True,
    )


def persist_mission(
    conn: sqlite3.Connection,
    mission: Mission,
    *,
    user_id: int,
    repo_id: int | None,
) -> int:
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, repo_id, full_name, status, entry_path, difficulty, effort,
          plan_json, local_path, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            repo_id,
            mission.full_name,
            mission.status,
            mission.strategy.path,
            mission.strategy.difficulty,
            mission.strategy.effort,
            json.dumps(mission.as_dict(), ensure_ascii=False),
            mission.local_path,
            now,
            now,
        ),
    )
    conn.commit()
    mission.id = int(cur.lastrowid)
    return mission.id


def list_missions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, full_name, status, entry_path, difficulty, effort, plan_json,
               local_path, created_at, updated_at
        FROM entry_missions WHERE user_id=? ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            plan = json.loads(row[6] or "{}")
        except json.JSONDecodeError:
            plan = {}
        plan.update(
            {
                "id": row[0],
                "full_name": row[1],
                "status": row[2],
                "local_path": row[7],
                "created_at": row[8],
                "updated_at": row[9],
            }
        )
        out.append(plan)
    return out


def set_status(
    conn: sqlite3.Connection, mission_id: int, user_id: int, status: Status
) -> None:
    conn.execute(
        """
        UPDATE entry_missions SET status=?, updated_at=?
        WHERE id=? AND user_id=?
        """,
        (status, datetime.now(UTC).isoformat(), mission_id, user_id),
    )
    conn.commit()


def create_for_user(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str,
    data_dir: Path,
) -> Mission:
    from foreshadow.pipeline import load_score_input

    row = conn.execute(
        "SELECT id FROM repos WHERE full_name=?", (full_name,)
    ).fetchone()
    repo_id = int(row[0]) if row else None
    data = load_score_input(conn, repo_id) if repo_id is not None else None
    feat = FeaturesBlob()
    age = None
    pushed = None
    stars = None
    contrib = None
    u_issue = None
    if data:
        raw = data.get("features") or {}
        if isinstance(raw, dict):
            feat = FeaturesBlob.model_validate(raw)
        stars = data.get("S")
        contrib = data.get("C")
        u_issue = data.get("U_issue") or feat.u_issue
        age = data.get("age_days")
        pushed = data.get("pushed_age_days")
        if age is None:
            from foreshadow.pipeline.hydrate import parse_dt

            created = parse_dt(data.get("created_at"))
            if created is not None:
                age = max((datetime.now(UTC).date() - created.date()).days, 1)
        if pushed is None:
            from foreshadow.pipeline.hydrate import parse_dt

            p = parse_dt(data.get("pushed_at"))
            if p is not None:
                pushed = max((datetime.now(UTC).date() - p.date()).days, 0)
    mission = build_mission(
        full_name,
        feat=feat,
        age_days=age,
        contributors=contrib,
        stars=stars,
        pushed_age_days=pushed,
        unique_issue_authors=u_issue,
    )
    dest = prepare_local_dir(data_dir, full_name)
    mission.local_path = str(dest)
    persist_mission(conn, mission, user_id=user_id, repo_id=repo_id)
    return mission


def refuse_remote_action(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "blocked": True,
        "action": action,
        "error": "远程 GitHub 操作需要你明确批准，Foreshadow 不会自动发送。",
        "status": "WAITING_USER_APPROVAL",
    }


def prepare_local_dir(root: Path, full_name: str) -> Path:
    safe = full_name.replace("/", "__")
    dest = Path(root) / "work" / safe
    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "FORESHADOW.md"
    if not readme.exists():
        readme.write_text(
            f"# Entry Mission\n\n{full_name}\n\n"
            "本目录只做本地准备。不会自动 push / 开 Issue / 开 PR。\n",
            encoding="utf-8",
        )
    return dest
