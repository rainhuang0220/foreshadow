import json
from datetime import date

from fakes import seed_repo
from foreshadow.db import connect, migrate
from foreshadow.observation_view import (
    EVENT_LABELS_ZH,
    SPARK_PENDING,
    decision_for,
    delta_pair,
    format_delta_zh,
    interpret_growth,
    load_series,
    sparkline,
    star_delta,
    timeline_for,
)
from foreshadow.pipeline.obs_events import (
    record_observation_events,
    record_potential_ups_for_today,
    record_today_observation_events,
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


def test_sparkline_empty_with_fewer_than_two_points():
    assert SPARK_PENDING == ""
    assert sparkline([]) == ""
    assert sparkline([{"stars": 10}]) == ""


def test_delta_pair_and_format_zh():
    pair = delta_pair([{"contributors": 12}, {"contributors": 17}], "contributors")
    assert pair == {"from": 12, "to": 17, "delta": 5, "pending": False}
    assert format_delta_zh("contributors", pair) == "外部贡献者：12 → 17"
    null_pair = delta_pair([{"stars": None}, {"stars": 5}], "stars")
    assert null_pair["pending"] is True
    assert null_pair["delta"] is None
    assert null_pair["from"] is None
    assert null_pair["from"] != 0


def _kinds(conn, repo_id=None):
    sql = "SELECT kind, payload_json FROM observation_events"
    args = ()
    if repo_id is not None:
        sql += " WHERE repo_id=?"
        args = (repo_id,)
    sql += " ORDER BY kind"
    return [(row[0], json.loads(row[1])) for row in conn.execute(sql, args)]


def test_stars_10_to_12_emits_stars_delta(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn, rid, date(2026, 9, 3), {"stars": 10}, {"stars": 12}
    )
    conn.commit()
    assert n == 1
    assert _kinds(conn, rid) == [("stars_delta", {"from": 10, "to": 12, "delta": 2})]


def test_null_to_five_does_not_claim_delta_from_zero(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn, rid, date(2026, 9, 3), {"stars": None}, {"stars": 5}
    )
    conn.commit()
    assert n == 0
    assert _kinds(conn, rid) == []
    pair = delta_pair([{"stars": None}, {"stars": 5}], "stars")
    assert pair["pending"] is True
    assert pair["delta"] is None
    assert pair["from"] is None


def test_first_snapshot_emits_first_seen_only(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn,
        rid,
        date(2026, 9, 1),
        None,
        {"stars": 10, "contributor_count": 5, "open_issues": 3, "open_prs": 1},
    )
    conn.commit()
    assert n == 1
    assert _kinds(conn, rid) == [("first_seen", {})]


def test_both_sides_null_is_silent(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn,
        rid,
        date(2026, 9, 3),
        {"stars": None, "open_issues": None, "contributor_count": None},
        {"stars": None, "open_issues": None, "contributor_count": None},
    )
    conn.commit()
    assert n == 0
    assert _kinds(conn, rid) == []


def test_first_external_contributor_from_owner_or_unknown(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn,
        rid,
        date(2026, 9, 3),
        {"contributor_count": 1},
        {"contributor_count": 3},
    )
    conn.commit()
    kinds = {k for k, _ in _kinds(conn, rid)}
    assert n == 2
    assert "contributors_delta" in kinds
    assert "first_external_contributor" in kinds
    rid2 = seed_repo(conn, "N2", "acme/y")
    n2 = record_observation_events(
        conn,
        rid2,
        date(2026, 9, 3),
        {"contributor_count": None},
        {"contributor_count": 2},
    )
    conn.commit()
    assert n2 == 1
    assert _kinds(conn, rid2) == [
        ("first_external_contributor", {"from": None, "to": 2})
    ]


def test_record_today_compares_previous_snapshot(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    _snap(conn, rid, "2026-09-01", 10)
    _snap(conn, rid, "2026-09-02", 12)
    conn.commit()
    assert record_today_observation_events(conn, date(2026, 9, 1)) == 1
    assert _kinds(conn, rid) == [("first_seen", {})]
    n = record_today_observation_events(conn, date(2026, 9, 2))
    conn.commit()
    payloads = {k: p for k, p in _kinds(conn, rid)}
    assert n == 1
    assert payloads["first_seen"] == {}
    assert payloads["stars_delta"] == {"from": 10, "to": 12, "delta": 2}


def test_potential_up_when_intel_increases(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    n = record_observation_events(
        conn, rid, date(2026, 9, 3), {"potential": 10}, {"potential": 40}
    )
    conn.commit()
    assert n == 1
    kind, payload = _kinds(conn, rid)[0]
    assert kind == "potential_up"
    assert payload["from"] == 10
    assert payload["to"] == 40
    assert payload["delta"] == 30
    assert (
        record_observation_events(
            conn, rid, date(2026, 9, 4), {"potential": 40}, {"potential": 30}
        )
        == 0
    )


def test_potential_up_from_intel_scores(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")

    def _intel(day: str, potential: float) -> None:
        conn.execute(
            """
            INSERT INTO intel_scores(
              repo_id, as_of_date, model_run_id, score, components_json, scored_at
            ) VALUES (?,?,1,?,?,?)
            """,
            (
                rid,
                day,
                potential,
                json.dumps({"potential": potential}),
                day + "T00:00:00+00:00",
            ),
        )

    _intel("2026-09-01", 10)
    _intel("2026-09-02", 18)
    conn.commit()
    n = record_potential_ups_for_today(conn, date(2026, 9, 2))
    conn.commit()
    assert n == 1
    kind, payload = _kinds(conn, rid)[0]
    assert kind == "potential_up"
    assert payload["delta"] == 8


def test_timeline_uses_stored_event_labels(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    record_observation_events(conn, rid, date(2026, 9, 2), {"stars": 10}, {"stars": 12})
    conn.commit()
    events = timeline_for(conn, rid, today="2026-09-02")
    star = next(e for e in events if e["kind"] == "stars_delta")
    assert star["label_zh"] == format_delta_zh("stars_delta", star["payload"])
    assert EVENT_LABELS_ZH["stars_delta"] == "Stars"
    assert star["payload"]["delta"] == 2
