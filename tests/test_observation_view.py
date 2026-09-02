from fakes import seed_repo
from foreshadow.db import connect, migrate
from foreshadow.observation_view import (
    SPARK_PENDING,
    decision_for,
    interpret_growth,
    load_series,
    sparkline,
    star_delta,
    timeline_for,
)


def _snap(conn, rid, day, stars, issues=None, prs=None, release=None):
    conn.execute(
        """
        INSERT INTO snapshots(
          repo_id, snapshot_date, captured_at, stars, open_issues, open_prs,
          last_pushed_at, completeness
        ) VALUES (?,?,?,?,?,?,?,1)
        """,
        (rid, day, day + "T00:00:00+00:00", stars, issues, prs, release),
    )


def test_one_snapshot_does_not_fake_a_seven_day_curve(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-02", 1200)
    conn.commit()
    series = load_series(conn, rid)
    assert [p["stars"] for p in series] == [1200]
    assert sparkline(series) == SPARK_PENDING
    delta = star_delta(series, days=7)
    assert delta["pending"] is True
    assert delta["delta"] is None
    assert interpret_growth(series) == "增长历史还不够，7 日趋势尚未形成。"


def test_real_deltas_only_when_consecutive_snapshots_differ(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    conn.execute(
        "UPDATE repos SET first_seen_at=? WHERE id=?",
        ("2026-09-01T00:00:00+00:00", rid),
    )
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-09-01", "2026-09-03", "2026-09-15", "opportunity"),
    )
    _snap(conn, rid, "2026-09-01", 1200, issues=10, prs=2)
    _snap(conn, rid, "2026-09-02", 1216, issues=12, prs=2)
    _snap(conn, rid, "2026-09-03", 1247, issues=12, prs=5)
    conn.commit()
    series = load_series(conn, rid)
    line = sparkline(series)
    assert line
    assert len(line) == 3
    delta = star_delta(series, days=7)
    assert delta["pending"] is False
    assert delta["delta"] == 47
    events = timeline_for(conn, rid, today="2026-09-03")
    kinds = [e["kind"] for e in events]
    assert "FIRST_SEEN" in kinds
    assert "PROMOTED_TO_OBSERVATION" in kinds
    star_events = [e for e in events if e["kind"] == "STAR_DELTA"]
    assert [e["payload"]["delta"] for e in star_events] == [16, 31]
    issue_events = [e for e in events if e["kind"] == "ISSUE_DELTA"]
    assert issue_events and issue_events[0]["payload"]["delta"] == 2
    assert interpret_growth(series).startswith("近")
    assert decision_for(series, official=False, observing=True) == "继续观察"


def test_enrich_attaches_layers_and_filters(tmp_home):
    from foreshadow.observation_view import enrich_board_payload

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-02", 10)
    conn.commit()
    payload = {
        "candidates": [{"full_name": "acme/x", "status": "preview_top", "stars": 10}],
        "counts": {},
    }
    enrich_board_payload(payload, conn)
    card = payload["candidates"][0]
    assert card["star_delta"]["pending"] is True
    assert "增长历史还不够" in card["interpretation"]
    assert card["decision"] == "候选"
    assert any(f["id"] == "observing" for f in payload["filters"])


def test_sparkline_does_not_interpolate_missing_days(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-03", 40)
    conn.commit()
    series = load_series(conn, rid)
    assert [p["date"] for p in series] == ["2026-09-01", "2026-09-03"]
    assert len(sparkline(series)) == 2
