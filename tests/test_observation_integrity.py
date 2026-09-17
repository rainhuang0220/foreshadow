"""PR3 observation-integrity contracts. No new intelligence layer."""

from __future__ import annotations

import ast
from pathlib import Path

from fakes import seed_repo
from foreshadow.db import connect, migrate
from foreshadow.observation_view import (
    card_layers,
    enrich_board_payload,
    interpret_growth,
    load_series,
    repo_detail,
    star_delta,
    timeline_for,
)

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


def test_load_series_preserves_observed_at_and_order(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-03", 30, captured_at="2026-09-03T07:00:00+00:00")
    _snap(conn, rid, "2026-09-01", 10, captured_at="2026-09-01T06:15:00+00:00")
    _snap(conn, rid, "2026-09-02", 20, captured_at="2026-09-02T06:40:00+00:00")
    conn.commit()

    series = load_series(conn, rid)
    assert [p["date"] for p in series] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert [p["observed_at"] for p in series] == [
        "2026-09-01T06:15:00+00:00",
        "2026-09-02T06:40:00+00:00",
        "2026-09-03T07:00:00+00:00",
    ]
    assert [p["captured_at"] for p in series] == [p["observed_at"] for p in series]
    assert series[0]["observed_at"] != "2026-09-01"
    layers = card_layers(conn, rid, official=False, observing=True)
    assert layers["fact"]["observed_at"] == "2026-09-03T07:00:00+00:00"
    assert layers["fact"]["first_date"] == "2026-09-01"
    assert layers["fact"]["last_date"] == "2026-09-03"
    assert layers["fact"]["calendar_days"] == 2


def test_star_delta_uses_actual_range_not_assumed_seven_days(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-10", 19)
    conn.commit()

    delta = star_delta(load_series(conn, rid), days=7)
    assert delta["pending"] is False
    assert delta["delta"] == 9
    assert delta["days"] == 9
    assert delta["first_date"] == "2026-09-01"
    assert delta["last_date"] == "2026-09-10"
    assert delta["observed_days"] == 2
    text = interpret_growth(load_series(conn, rid))
    assert "7 日趋势" not in text
    assert "7日增长" not in text
    assert "按实际观察跨度" in text


def test_three_day_span_is_not_labeled_seven_days(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 100)
    _snap(conn, rid, "2026-09-02", 110)
    _snap(conn, rid, "2026-09-03", 125)
    conn.commit()

    delta = star_delta(load_series(conn, rid), days=7)
    assert delta["days"] == 2
    assert delta["days"] != 7
    assert delta["window_complete"] is True


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
    card_layers(conn, rid, official=False, observing=True)
    payload = {
        "candidates": [{"full_name": "acme/x", "status": "preview_top", "stars": 18}],
        "counts": {},
    }
    enrich_board_payload(payload, conn)
    detail = repo_detail(conn, "acme/x")

    assert detail is not None
    assert detail["observation"]["last_observed_on"] == "2026-09-03"
    assert conn.total_changes == before_changes
    assert _fingerprint(conn) == before


def test_observation_view_has_no_github_write_surface():
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


def test_board_fact_chip_does_not_hardcode_seven_day_growth():
    source = WEBAPP_PATH.read_text(encoding="utf-8")
    assert "function factCells" in source
    assert ">7日增长<" not in source
    assert "观察增长" in source
