"""S5 observed outcomes. Separate from Access formula weights."""

from __future__ import annotations

import sqlite3
from typing import Any

from foreshadow.pipeline.access import classify_access
from foreshadow.pipeline.features import clip

MIN_OBSERVATIONS = 3

OUTCOME_WEIGHTS: dict[str, float] = {
    "maintainer_replied": 1.0,
    "issue_accepted": 1.0,
    "pr_reviewed": 1.0,
    "pr_merged": 1.5,
    "maintainer_silent": 0.0,
    "pr_rejected": 0.15,
}

OUTCOME_EVENTS = frozenset(OUTCOME_WEIGHTS)


def observed_access(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str | None = None,
) -> dict[str, Any]:
    """User-local overlay. UNKNOWN when the sample is small. Never 0-fill."""
    if full_name:
        rows = conn.execute(
            """
            SELECT event, COUNT(*) FROM contribution_events
            WHERE user_id=? AND full_name=? GROUP BY 1
            """,
            (user_id, full_name),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT event, COUNT(*) FROM contribution_events
            WHERE user_id=? GROUP BY 1
            """,
            (user_id,),
        ).fetchall()
    counts = {str(k): int(v) for k, v in rows}
    n = sum(counts.get(ev, 0) for ev in OUTCOME_EVENTS)
    if n < MIN_OBSERVATIONS:
        return {
            "score": None,
            "class": None,
            "n": n,
            "counts": counts,
            "source": "user_events",
            "why": "UNKNOWN (few observations); not 0",
            "note": "Observed Access is not the formula Access Score.",
        }
    weighted = 0.0
    used = 0.0
    for ev, w in OUTCOME_WEIGHTS.items():
        c = counts.get(ev, 0)
        if c <= 0:
            continue
        weighted += w * c
        used += c
    score = clip(100.0 * weighted / max(used, 1.0), 0, 100)
    return {
        "score": round(score, 4),
        "class": classify_access(score),
        "n": n,
        "counts": counts,
        "source": "user_events",
        "why": f"observed n={n} from your missions (formula weights unchanged)",
        "note": "Observed Access is not the formula Access Score.",
    }
