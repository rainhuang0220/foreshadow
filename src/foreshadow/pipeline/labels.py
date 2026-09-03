"""Resolve future outcome labels. Missing t+h stays NULL. Never 0-fill."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

HORIZONS = (7, 30, 90)
WINDOW_SLACK_DAYS = 1


def resolve_labels(
    conn: sqlite3.Connection,
    today: date,
    slack_days: int = WINDOW_SLACK_DAYS,
) -> int:
    """Write/update outcome_labels for as_of = today - h. Returns rows touched."""
    n = 0
    labeled_at = datetime.now(UTC).isoformat()
    for h in HORIZONS:
        as_of = today - timedelta(days=int(h))
        target = as_of + timedelta(days=int(h))
        rows = conn.execute(
            """
            SELECT repo_id, stars, contributor_count, last_pushed_at
            FROM snapshots
            WHERE snapshot_date=?
            """,
            (as_of.isoformat(),),
        ).fetchall()
        for repo_id, stars_t, contrib_t, _pushed_t in rows:
            found = lookup_horizon_snapshot(conn, int(repo_id), target, slack_days)
            stars_h = found["stars"] if found else None
            contrib_h = found["contributors"] if found else None
            pushed_h = found["last_pushed_at"] if found else None
            source = found["source"] if found else None
            delta_stars = None
            if stars_t is not None and stars_h is not None:
                delta_stars = int(stars_h) - int(stars_t)
            delta_c = None
            if contrib_t is not None and contrib_h is not None:
                delta_c = int(contrib_h) - int(contrib_t)
            maintained = _still_maintained(pushed_h, target)
            conn.execute(
                """
                INSERT INTO outcome_labels(
                  repo_id, as_of_date, horizon_days,
                  stars_t, stars_t_h, delta_stars,
                  contributors_t, contributors_t_h, delta_contributors,
                  still_maintained, source, labeled_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(repo_id, as_of_date, horizon_days) DO UPDATE SET
                  stars_t=excluded.stars_t,
                  stars_t_h=excluded.stars_t_h,
                  delta_stars=excluded.delta_stars,
                  contributors_t=excluded.contributors_t,
                  contributors_t_h=excluded.contributors_t_h,
                  delta_contributors=excluded.delta_contributors,
                  still_maintained=excluded.still_maintained,
                  source=excluded.source,
                  labeled_at=excluded.labeled_at
                """,
                (
                    int(repo_id),
                    as_of.isoformat(),
                    int(h),
                    stars_t,
                    stars_h,
                    delta_stars,
                    contrib_t,
                    contrib_h,
                    delta_c,
                    maintained,
                    source,
                    labeled_at,
                ),
            )
            n += 1
    conn.commit()
    return n


def lookup_horizon_snapshot(
    conn: sqlite3.Connection,
    repo_id: int,
    target_date: date,
    slack_days: int = WINDOW_SLACK_DAYS,
) -> dict[str, Any] | None:
    """Forward nearest snapshot at t+h, slack in days. Never looks backward of t."""
    lo = target_date
    hi = target_date + timedelta(days=max(int(slack_days), 0))
    row = conn.execute(
        """
        SELECT snapshot_date, stars, contributor_count, last_pushed_at
        FROM snapshots
        WHERE repo_id=? AND snapshot_date >= ? AND snapshot_date <= ?
        ORDER BY snapshot_date ASC
        LIMIT 1
        """,
        (int(repo_id), lo.isoformat(), hi.isoformat()),
    ).fetchone()
    if row is None:
        return None
    day = str(row[0])
    source = "exact" if day == target_date.isoformat() else "nearest-1d"
    return {
        "date": day,
        "stars": row[1],
        "contributors": row[2],
        "last_pushed_at": row[3],
        "source": source,
    }


def _still_maintained(pushed_at: Any, horizon: date) -> int | None:
    if not pushed_at:
        return None
    text = str(pushed_at).replace("Z", "+00:00")
    try:
        pushed = datetime.fromisoformat(text)
    except ValueError:
        if len(text) >= 10:
            try:
                pushed_d = date.fromisoformat(text[:10])
            except ValueError:
                return None
            delta = (horizon - pushed_d).days
            if delta < 0:
                return 1
            return 1 if delta <= 30 else 0
        return None
    delta = (horizon - pushed.date()).days
    if delta < 0:
        return 1
    return 1 if delta <= 30 else 0
