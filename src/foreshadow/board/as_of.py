"""Latest completed Official date for a long-lived Board process."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime

from foreshadow.clock import Clock

DISPLAYABLE = frozenset({"complete", "degraded"})
PENDING_ZH = "今日扫描尚未完成，当前展示最近一次 Official。"
FAILED_ZH = "今日扫描失败，当前展示最近一次成功结果。"


@dataclass(frozen=True)
class BoardAsOf:
    current_date: str
    display_as_of_date: str | None
    today_run_status: str
    note_zh: str | None


def resolve_board_as_of(conn: sqlite3.Connection, clock: Clock) -> BoardAsOf:
    """Pick the latest displayable Official at or before clock.today() (UTC)."""
    today = clock.today().isoformat()
    today_status = _status_on(conn, today)
    latest = _latest_displayable(conn, today)
    if today_status in DISPLAYABLE:
        return BoardAsOf(
            current_date=today,
            display_as_of_date=today,
            today_run_status=today_status,
            note_zh=None,
        )
    if today_status == "failed":
        return BoardAsOf(
            current_date=today,
            display_as_of_date=latest,
            today_run_status="failed",
            note_zh=FAILED_ZH if latest else None,
        )
    if today_status == "running":
        return BoardAsOf(
            current_date=today,
            display_as_of_date=latest,
            today_run_status="running",
            note_zh=PENDING_ZH if latest else None,
        )
    if latest:
        return BoardAsOf(
            current_date=today,
            display_as_of_date=latest,
            today_run_status="pending",
            note_zh=PENDING_ZH,
        )
    return BoardAsOf(
        current_date=today,
        display_as_of_date=None,
        today_run_status="none",
        note_zh=None,
    )


def scoring_clock_for(day: str) -> Clock:
    """Bind v7 windows to the Official date, not wall-clock after UTC midnight."""
    parsed = date.fromisoformat(day)
    return Clock(now=datetime(parsed.year, parsed.month, parsed.day, 0, 5, tzinfo=UTC))


def _status_on(conn: sqlite3.Connection, day: str) -> str | None:
    try:
        row = conn.execute(
            """
            SELECT status FROM daily_runs
            WHERE run_date=?
            ORDER BY id DESC LIMIT 1
            """,
            (day,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _latest_displayable(conn: sqlite3.Connection, today: str) -> str | None:
    try:
        row = conn.execute(
            """
            SELECT run_date FROM daily_runs
            WHERE status IN ('complete','degraded')
              AND run_date <= ?
            ORDER BY run_date DESC LIMIT 1
            """,
            (today,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])
