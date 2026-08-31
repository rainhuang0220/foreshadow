"""Persistent system observation panel (P1).

Discovery answers “what appeared today?”. Observation answers “what have we
been watching?”. Official scoring is unchanged.

Invariants (tested):
A. An active system row is re-hydrated even if Search misses it.
B. Identity is repos.id / node_id; rename does not fork the panel.
C. Operator watchlist seats first and is never TTL-evicted here.
D. Panel membership is not Official selected_rank.
E. System rows are not user interested / reviews.
F. Active panel size is capped (max_candidates - fresh_discovery_floor).
G. Fresh discovery keeps a reserved floor of seats.
H. Preview / Board reads must not write this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from foreshadow.config import DiscoverySettings
from foreshadow.pipeline.score import ScoredRepo


@dataclass(frozen=True)
class ObservationEntry:
    repo_id: int
    node_id: str
    full_name: str
    added_on: str
    last_observed_on: str
    expires_on: str
    reason: str
    state: str = "active"


def expire_due(conn: Any, today: date) -> int:
    """Mark system rows past expires_on. Does not touch reviews."""
    cur = conn.execute(
        """
        UPDATE observations
        SET state='expired'
        WHERE state='active' AND expires_on < ?
        """,
        (today.isoformat(),),
    )
    return int(cur.rowcount or 0)


def load_active(conn: Any, today: date) -> list[ObservationEntry]:
    """Active, unexpired system observations. Deterministic order."""
    rows = conn.execute(
        """
        SELECT o.repo_id, r.node_id, r.full_name,
               o.added_on, o.last_observed_on, o.expires_on, o.reason, o.state
        FROM observations o
        JOIN repos r ON r.id = o.repo_id
        WHERE o.state='active' AND o.expires_on >= ?
        ORDER BY o.added_on ASC, r.node_id ASC
        """,
        (today.isoformat(),),
    ).fetchall()
    return [
        ObservationEntry(
            repo_id=int(row[0]),
            node_id=str(row[1]),
            full_name=str(row[2]),
            added_on=str(row[3]),
            last_observed_on=str(row[4]),
            expires_on=str(row[5]),
            reason=str(row[6]),
            state=str(row[7]),
        )
        for row in rows
    ]


def mark_observed(conn: Any, repo_ids: list[int], today: date) -> None:
    if not repo_ids:
        return
    day = today.isoformat()
    conn.executemany(
        """
        UPDATE observations
        SET last_observed_on=?
        WHERE repo_id=? AND state='active'
        """,
        [(day, int(rid)) for rid in repo_ids],
    )


def panel_cap(disc: DiscoverySettings) -> int:
    max_n = int(disc.max_candidates)
    floor = int(disc.fresh_discovery_floor)
    return max(0, max_n - min(floor, max_n))


def _expires_on(added: date, ttl_days: int) -> str:
    return (added + timedelta(days=int(ttl_days))).isoformat()


def _opportunity(scored: ScoredRepo) -> float | None:
    val = scored.breakdown.opportunity.value
    return None if val is None else float(val)


def admit_from_scores(
    conn: Any,
    *,
    today: date,
    scored_rows: list[tuple[int, ScoredRepo, dict[str, Any]]],
    selected_ids: set[int],
    watchlist_ids: set[int],
    disc: DiscoverySettings,
) -> int:
    """Promote system observations. Never inserts into reviews.

    Official Top 5 (selected_ids) are always pinned when space remains.
    Other promotions need opportunity >= observation_admit_min and are
    capped at observation_admit_max per day.
    """
    ttl = int(disc.observation_ttl_days)
    cap = panel_cap(disc)
    admit_max = int(disc.observation_admit_max)
    min_opp = float(disc.observation_admit_min)
    today_s = today.isoformat()

    existing = {
        int(row[0]): str(row[1])
        for row in conn.execute("SELECT repo_id, state FROM observations").fetchall()
    }
    active_n = sum(1 for state in existing.values() if state == "active")
    promoted = 0

    def upsert(repo_id: int, reason: str) -> bool:
        nonlocal active_n, promoted
        if existing.get(repo_id) == "active":
            return False
        if active_n >= cap:
            return False
        expires = _expires_on(today, ttl)
        conn.execute(
            """
            INSERT INTO observations(
              repo_id, added_on, last_observed_on, expires_on, reason, state
            ) VALUES (?,?,?,?,?, 'active')
            ON CONFLICT(repo_id) DO UPDATE SET
              added_on=excluded.added_on,
              last_observed_on=excluded.last_observed_on,
              expires_on=excluded.expires_on,
              reason=excluded.reason,
              state='active'
            """,
            (repo_id, today_s, today_s, expires, reason),
        )
        existing[repo_id] = "active"
        active_n += 1
        promoted += 1
        return True

    for repo_id in sorted(selected_ids):
        upsert(repo_id, "previous_official")

    ranked: list[tuple[float, str, int, str]] = []
    for repo_id, scored, data in scored_rows:
        if repo_id in watchlist_ids or existing.get(repo_id) == "active":
            continue
        if scored.breakdown.vetoed:
            continue
        opp = _opportunity(scored)
        if opp is None or opp < min_opp:
            continue
        node_id = str(data.get("node_id") or scored.full_name)
        ranked.append((-opp, node_id, repo_id, f"opportunity {opp:.0f}"))
    ranked.sort()
    opportunity_promoted = 0
    for _neg, _nid, repo_id, reason in ranked:
        if opportunity_promoted >= admit_max:
            break
        if upsert(repo_id, reason):
            opportunity_promoted += 1
    return promoted


def count_states(conn: Any) -> tuple[int, int]:
    active = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE state='active'"
    ).fetchone()[0]
    expired = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE state='expired'"
    ).fetchone()[0]
    return int(active or 0), int(expired or 0)


def v7_eligible_count(
    conn: Any,
    repo_ids: list[int],
    today: date,
    slack_days: int,
) -> int:
    """Repos with a snapshot in [today-7-slack, today-7]. Not a score."""
    if not repo_ids:
        return 0
    want = today - timedelta(days=7)
    lo = (want - timedelta(days=int(slack_days))).isoformat()
    hi = want.isoformat()
    placeholders = ",".join("?" * len(repo_ids))
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT repo_id) FROM snapshots
        WHERE repo_id IN ({placeholders})
          AND snapshot_date >= ? AND snapshot_date <= ?
        """,
        [*repo_ids, lo, hi],
    ).fetchone()
    return int(row[0] or 0) if row else 0


def yesterday_overlap(conn: Any, run_id: int, today: date) -> tuple[int, int, float]:
    """(retained, previous_count, overlap_rate) vs prior run_date candidates."""
    prev = conn.execute(
        """
        SELECT id, run_date FROM daily_runs
        WHERE run_date < ? AND id != ?
        ORDER BY run_date DESC LIMIT 1
        """,
        (today.isoformat(), run_id),
    ).fetchone()
    if prev is None:
        return 0, 0, 0.0
    prev_ids = {
        int(r[0])
        for r in conn.execute(
            "SELECT repo_id FROM candidates WHERE run_id=?", (int(prev[0]),)
        )
    }
    cur_ids = {
        int(r[0])
        for r in conn.execute(
            "SELECT repo_id FROM candidates WHERE run_id=?", (run_id,)
        )
    }
    retained = len(prev_ids & cur_ids)
    prev_n = len(prev_ids)
    rate = (retained / prev_n) if prev_n else 0.0
    return retained, prev_n, rate
