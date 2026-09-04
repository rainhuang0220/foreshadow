"""Board displays the latest completed Official run, not the process start date."""

from __future__ import annotations

from datetime import UTC, datetime

from fakes import seed_repo
from foreshadow.clock import Clock
from foreshadow.db import connect, migrate
from foreshadow.pipeline.snapshot import upsert_snapshot


def _insert_run(conn, *, day: str, status: str, started: str, repo_id: int) -> int:
    conn.execute(
        "INSERT INTO daily_runs(run_date, started_at, status, budget_cap) "
        "VALUES (?,?,?,800)",
        (day, started, status),
    )
    run_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        "INSERT INTO candidates(run_id, repo_id, discovery_source, hydrate_status) "
        "VALUES (?,?,'search','ok')",
        (run_id, repo_id),
    )
    if status in {"complete", "degraded"}:
        conn.execute(
            "UPDATE daily_runs SET finished_at=?, status=? WHERE id=?",
            (started, status, run_id),
        )
    conn.commit()
    return run_id


def _seed(home, day: str = "2026-08-24") -> int:
    conn = connect(home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    upsert_snapshot(
        conn,
        rid,
        day,
        {
            "stars": 10,
            "forks": 1,
            "open_issues": 1,
            "open_prs": 0,
            "captured_at": f"{day}T00:05:00+00:00",
            "topics_json": "[]",
            "features_json": "{}",
            "completeness": 1.0,
            "contributor_count": 2,
        },
    )
    conn.commit()
    return rid


def test_latest_completed_is_today_when_degraded(tmp_home):
    from foreshadow.board.as_of import resolve_board_as_of

    rid = _seed(tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    _insert_run(
        conn,
        day="2026-08-24",
        status="degraded",
        started="2026-08-24T00:30:00+00:00",
        repo_id=rid,
    )
    clock = Clock(now=datetime(2026, 8, 24, 1, 0, tzinfo=UTC))
    as_of = resolve_board_as_of(conn, clock)
    assert as_of.display_as_of_date == "2026-08-24"
    assert as_of.current_date == "2026-08-24"
    assert as_of.today_run_status == "degraded"
    assert as_of.note_zh is None


def test_midnight_before_daily_keeps_yesterday(tmp_home):
    from foreshadow.board.as_of import resolve_board_as_of

    rid = _seed(tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    _insert_run(
        conn,
        day="2026-08-24",
        status="complete",
        started="2026-08-24T00:30:00+00:00",
        repo_id=rid,
    )
    clock = Clock(now=datetime(2026, 8, 25, 0, 10, tzinfo=UTC))
    as_of = resolve_board_as_of(conn, clock)
    assert as_of.current_date == "2026-08-25"
    assert as_of.display_as_of_date == "2026-08-24"
    assert as_of.today_run_status == "pending"
    assert "尚未完成" in (as_of.note_zh or "")


def test_running_today_still_shows_yesterday(tmp_home):
    from foreshadow.board.as_of import resolve_board_as_of

    rid = _seed(tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    _insert_run(
        conn,
        day="2026-08-24",
        status="complete",
        started="2026-08-24T00:30:00+00:00",
        repo_id=rid,
    )
    _insert_run(
        conn,
        day="2026-08-25",
        status="running",
        started="2026-08-25T00:30:00+00:00",
        repo_id=rid,
    )
    clock = Clock(now=datetime(2026, 8, 25, 0, 33, tzinfo=UTC))
    as_of = resolve_board_as_of(conn, clock)
    assert as_of.display_as_of_date == "2026-08-24"
    assert as_of.today_run_status == "running"


def test_failed_today_keeps_last_success(tmp_home):
    from foreshadow.board.as_of import resolve_board_as_of

    rid = _seed(tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    _insert_run(
        conn,
        day="2026-08-24",
        status="complete",
        started="2026-08-24T00:30:00+00:00",
        repo_id=rid,
    )
    _insert_run(
        conn,
        day="2026-08-25",
        status="failed",
        started="2026-08-25T00:30:00+00:00",
        repo_id=rid,
    )
    clock = Clock(now=datetime(2026, 8, 25, 1, 0, tzinfo=UTC))
    as_of = resolve_board_as_of(conn, clock)
    assert as_of.display_as_of_date == "2026-08-24"
    assert as_of.today_run_status == "failed"
    assert "失败" in (as_of.note_zh or "")


def test_empty_db_is_pending_not_crash(tmp_home):
    from foreshadow.board.as_of import resolve_board_as_of

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    clock = Clock(now=datetime(2026, 8, 24, 1, 0, tzinfo=UTC))
    as_of = resolve_board_as_of(conn, clock)
    assert as_of.display_as_of_date is None
    assert as_of.current_date == "2026-08-24"
    assert as_of.today_run_status == "none"
