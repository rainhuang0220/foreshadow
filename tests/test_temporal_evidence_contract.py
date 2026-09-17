"""PR4 temporal evidence contracts. No new intelligence layer."""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path

from fakes import seed_repo
from foreshadow.clock import Clock
from foreshadow.db import connect, migrate
from foreshadow.observation_view import (
    card_layers,
    enrich_board_payload,
    interpret_growth,
    load_series,
    observation_span,
    repo_detail,
    star_delta,
    timeline_for,
)
from foreshadow.pipeline.features import SnapshotPoint, compute_windows

ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = ROOT / "src" / "foreshadow" / "observation_view.py"
WEBAPP_PATH = ROOT / "src" / "foreshadow" / "board" / "webapp.py"
_WRITE_TABLES = (
    "repos",
    "snapshots",
    "observations",
    "observation_events",
    "scores",
    "daily_runs",
)
_FALSE_WINDOW_LABELS = ("7日增长", "7 日趋势", "7 day growth", "7-day growth")


def _snap(conn, rid, day, stars, *, captured_at=None, issues=None, prs=None):
    conn.execute(
        """
        INSERT INTO snapshots(
          repo_id, snapshot_date, captured_at, stars, open_issues, open_prs,
          last_pushed_at, completeness
        ) VALUES (?,?,?,?,?,?,?,1)
        """,
        (
            rid,
            day,
            captured_at or (day + "T00:05:00+00:00"),
            stars,
            issues,
            prs,
            None,
        ),
    )


def _fingerprint(conn) -> dict[str, tuple]:
    return {
        name: tuple(conn.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall())
        for name in _WRITE_TABLES
    }


def test_sparse_span_is_calendar_days_not_seven_day_growth(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-15", 50)
    conn.commit()

    series = load_series(conn, rid)
    delta = star_delta(series, days=7)
    span = observation_span(series)
    assert delta["pending"] is False
    assert delta["calendar_days"] == 14
    assert delta["observed_points"] == 2
    assert span["calendar_days"] == 14
    assert span["observed_points"] == 2
    assert delta["days"] == 14
    assert delta["observed_days"] == 2
    assert delta["delta"] == 40
    assert delta["first_date"] == "2026-09-01"
    assert delta["last_date"] == "2026-09-15"
    assert delta["window_complete"] is False
    text = interpret_growth(series)
    for label in _FALSE_WINDOW_LABELS:
        assert label not in text
    assert "14" in text


def test_consecutive_three_days_is_not_a_seven_day_window(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 100)
    _snap(conn, rid, "2026-09-02", 110)
    _snap(conn, rid, "2026-09-03", 125)
    conn.commit()

    delta = star_delta(load_series(conn, rid), days=7)
    assert delta["calendar_days"] == 2
    assert delta["observed_points"] == 3
    assert delta["calendar_days"] != 7
    assert delta["window_complete"] is False


def test_single_observation_cannot_claim_a_span(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-02", 1200, captured_at="2026-09-02T06:15:00+00:00")
    conn.commit()

    series = load_series(conn, rid)
    delta = star_delta(series, days=7)
    assert delta["pending"] is True
    assert delta["delta"] is None
    assert delta["calendar_days"] is None
    assert delta["observed_points"] == 1
    assert delta["first_date"] == "2026-09-02"
    assert series[0]["observed_at"] == "2026-09-02T06:15:00+00:00"
    text = interpret_growth(series)
    assert "还不能比较两次观察" in text
    for label in _FALSE_WINDOW_LABELS:
        assert label not in text


def test_missing_observation_is_pending_not_zero_growth():
    delta = star_delta([])
    assert delta["pending"] is True
    assert delta["delta"] is None
    assert delta["from"] is None
    assert delta["calendar_days"] is None
    assert delta["observed_points"] == 0
    assert delta["window_complete"] is False
    assert interpret_growth([]) == "还没有本地快照，不能谈增长。"


def test_null_star_points_are_not_observed_points(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-08", None)
    _snap(conn, rid, "2026-09-15", 20)
    conn.commit()

    delta = star_delta(load_series(conn, rid))
    assert delta["calendar_days"] == 14
    assert delta["observed_points"] == 2
    assert delta["delta"] == 10
    assert delta["pending"] is False


def test_observation_delta_is_not_official_v7():
    snaps = [
        SnapshotPoint(date(2026, 8, 24), 100, None, None),
        SnapshotPoint(date(2026, 8, 25), 110, None, None),
        SnapshotPoint(date(2026, 8, 26), 120, None, None),
        SnapshotPoint(date(2026, 8, 27), 130, None, None),
        SnapshotPoint(date(2026, 8, 28), 140, None, None),
        SnapshotPoint(date(2026, 8, 29), 150, None, None),
        SnapshotPoint(date(2026, 8, 30), 160, None, None),
        SnapshotPoint(date(2026, 8, 31), 170, None, None),
    ]
    series = [
        {"date": p.date.isoformat(), "stars": p.stars} for p in snaps
    ]
    delta = star_delta(series)
    windows = compute_windows(
        snaps,
        Clock(now=datetime(2026, 8, 31, 0, 5, tzinfo=UTC)),
        created_at=date(2026, 7, 1),
        slack_days=1,
    )
    assert delta["calendar_days"] == 7
    assert delta["observed_points"] == 8
    assert delta["delta"] == 70
    assert windows.v7 is not None
    assert abs(float(windows.v7) - 10.0) < 1e-9
    assert delta["delta"] != windows.v7
    assert delta["window_complete"] is False


def test_sparse_observation_does_not_satisfy_official_v7():
    snaps = [
        SnapshotPoint(date(2026, 9, 1), 10, None, None),
        SnapshotPoint(date(2026, 9, 15), 50, None, None),
    ]
    series = [
        {"date": p.date.isoformat(), "stars": p.stars} for p in snaps
    ]
    delta = star_delta(series)
    windows = compute_windows(
        snaps,
        Clock(now=datetime(2026, 9, 15, 0, 5, tzinfo=UTC)),
        created_at=date(2026, 7, 1),
        slack_days=1,
    )
    assert delta["calendar_days"] == 14
    assert delta["observed_points"] == 2
    assert delta["delta"] == 40
    assert windows.v7 is None
    assert delta["window_complete"] is False


def test_observation_view_does_not_import_official_windows():
    source = VIEW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "foreshadow.pipeline.features" not in imported
    assert "compute_windows" not in source


def test_observation_reads_do_not_mutate_database(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-09-01", "2026-09-03", "2026-09-15", "opportunity"),
    )
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-03", 18)
    conn.commit()
    before = _fingerprint(conn)
    before_changes = conn.total_changes

    series = load_series(conn, rid)
    star_delta(series)
    timeline_for(conn, rid, today="2026-09-03")
    layers = card_layers(conn, rid, official=False, observing=True)
    payload = {
        "candidates": [{"full_name": "acme/x", "status": "preview_top", "stars": 18}],
        "counts": {},
    }
    enrich_board_payload(payload, conn)
    detail = repo_detail(conn, "acme/x")

    assert detail is not None
    assert layers["fact"]["calendar_days"] == 2
    assert layers["fact"]["observed_points"] == 2
    assert payload["candidates"][0]["star_delta"]["calendar_days"] == 2
    assert payload["candidates"][0]["star_delta"]["observed_points"] == 2
    assert conn.total_changes == before_changes
    assert _fingerprint(conn) == before


def test_observation_view_has_no_github_or_write_surface():
    source = VIEW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("github" in name for name in imported)
    assert "foreshadow.github.approved_write" not in imported
    lowered = source.lower()
    assert "insert into" not in lowered
    assert "delete from" not in lowered
    assert "update observations" not in lowered
    assert "update snapshots" not in lowered
    assert "update missions" not in lowered


def test_board_fact_chip_does_not_hardcode_seven_day_growth():
    source = WEBAPP_PATH.read_text(encoding="utf-8")
    assert "function factCells" in source
    assert ">7日增长<" not in source
    assert "7日增长" not in source
    assert "观察增长" in source
    assert "calendar_days" in source
    assert "observed_points" in source
    assert "个观察点" in source


def test_card_layers_preserve_observed_at(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10, captured_at="2026-09-01T06:15:00+00:00")
    _snap(conn, rid, "2026-09-03", 18, captured_at="2026-09-03T07:00:00+00:00")
    conn.commit()
    layers = card_layers(conn, rid, official=False, observing=True)
    assert layers["fact"]["observed_at"] == "2026-09-03T07:00:00+00:00"
    assert layers["series"][0]["observed_at"] == "2026-09-01T06:15:00+00:00"
    assert layers["series"][0]["observed_at"] != "2026-09-01"
