"""Persistent observation panel. Does not retune Official 55/35 or v7."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.board.pipeline import build_board_from_db
from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.discover import (
    SearchHit,
    cap_candidates,
    discover_hydrate_snapshot,
)
from foreshadow.pipeline.observation import (
    ObservationEntry,
    admit_from_scores,
    expire_due,
    load_active,
)
from foreshadow.pipeline.score import ScoredRepo
from foreshadow.pipeline.select import is_official_eligible, select_top


def _hit(node_id: str, full_name: str, query_key: str = "A_mcp") -> SearchHit:
    return SearchHit(
        node_id=node_id,
        full_name=full_name,
        query_key=query_key,
        pool="A",
        description="A substantial project description for discovery tests.",
        topics=("mcp",),
        fork_count=2,
    )


def _entry(
    node_id: str, full_name: str, added: str, repo_id: int = 1
) -> ObservationEntry:
    return ObservationEntry(
        repo_id=repo_id,
        node_id=node_id,
        full_name=full_name,
        added_on=added,
        last_observed_on=added,
        expires_on="2099-01-01",
        reason="test",
    )


def _keep_node(stars: int = 100) -> dict:
    return repo_node(
        "R_keep",
        "acme/keep",
        stargazerCount=stars,
        topics=["mcp"],
        description="Persistent observation subject used in longitudinal tests.",
        forkCount=3,
    )


def test_official_thresholds_unchanged():
    assert is_official_eligible.__defaults__ == (55, 35)
    assert select_top.__kwdefaults__["min_opportunity"] == 55
    assert select_top.__kwdefaults__["min_explosion"] == 35


def test_search_miss_still_hydrates(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = _keep_node()
    rid = seed_repo(conn, "R_keep", "acme/keep")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-08-24", "2026-08-24", "2026-09-07", "seed"),
    )
    conn.commit()
    other = repo_node("R_new", "acme/new", topics=["mcp"])
    gh = FakeGitHub(nodes={"R_keep": node, "R_new": other}, search_nodes=[other])
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    ids = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
            (result.run_id,),
        )
    }
    assert "R_keep" in ids
    snap = conn.execute(
        "SELECT stars FROM snapshots WHERE repo_id=? AND snapshot_date='2026-08-24'",
        (rid,),
    ).fetchone()
    assert snap is not None
    assert snap[0] == 100


def test_day0_to_day7_search_miss_forms_v7(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    node = _keep_node(100)
    gh = FakeGitHub(
        nodes={"R_keep": node},
        search_by_day={"2026-08-24": [node]},
    )
    settings = Settings()
    settings.discovery.observation_admit_min = 0
    start = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    for day in range(8):
        clock = Clock(now=start + timedelta(days=day))
        gh.begin_day(clock.today())
        node["stargazerCount"] = 100 + day * 10
        result = run_pipeline(
            clock=clock, force=False, llm=False, client=gh, settings=settings
        )
        assert result.skipped is False
        assert "R_keep" in gh.hydrate_ids
    conn = connect(tmp_home / "foreshadow.sqlite3")
    dates = [
        row[0]
        for row in conn.execute(
            """
            SELECT s.snapshot_date FROM snapshots s
            JOIN repos r ON r.id=s.repo_id
            WHERE r.node_id='R_keep'
            ORDER BY s.snapshot_date
            """
        )
    ]
    assert dates[0] == "2026-08-24"
    assert dates[-1] == "2026-08-31"
    assert "2026-08-24" in dates and "2026-08-31" in dates
    v7 = conn.execute(
        """
        SELECT json_extract(s.evidence_json, '$.windows.v7')
        FROM scores s
        JOIN daily_runs d ON d.id=s.run_id
        JOIN repos r ON r.id=s.repo_id
        WHERE d.run_date='2026-08-31' AND r.node_id='R_keep' AND s.score_version='v1'
        """
    ).fetchone()
    assert v7 is not None
    assert v7[0] is not None
    assert abs(float(v7[0]) - 10.0) < 1e-9  # (170-100)/7


def test_ttl_expires_system_row(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_old", "acme/old")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-08-01", "2026-08-10", "2026-08-15", "stale"),
    )
    conn.commit()
    n = expire_due(conn, frozen_clock.today())
    assert n == 1
    assert load_active(conn, frozen_clock.today()) == []
    node = repo_node("R_fresh", "acme/fresh", topics=["mcp"])
    gh = FakeGitHub(
        nodes={"R_old": repo_node("R_old", "acme/old"), "R_fresh": node},
        search_nodes=[node],
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
            (result.run_id,),
        )
    }
    assert "R_old" not in names
    assert "R_fresh" in names


def test_watchlist_survives_system_ttl(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    watched = seed_repo(conn, "R_watch", "acme/watched")
    seed_review(conn, watched, "watch", "2026-08-20T00:00:00+00:00")
    stale = seed_repo(conn, "R_sys", "acme/sys")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (stale, "2026-08-01", "2026-08-01", "2026-08-15", "stale"),
    )
    conn.commit()
    wnode = repo_node("R_watch", "acme/watched", topics=["mcp"])
    snode = repo_node("R_sys", "acme/sys", topics=["mcp"])
    gh = FakeGitHub(
        nodes={"R_watch": wnode, "R_sys": snode},
        search_nodes=[],
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    ids = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
            (result.run_id,),
        )
    }
    assert "R_watch" in ids
    assert "R_sys" not in ids
    reviews = conn.execute(
        "SELECT action FROM reviews WHERE repo_id=?", (watched,)
    ).fetchall()
    assert reviews == [("watch",)]


def test_observation_and_search_dedupe():
    obs = [_entry("R_a", "acme/a", "2026-08-20")]
    hits = [_hit("R_a", "acme/a"), _hit("R_b", "acme/b")]
    cap = cap_candidates([], hits, max_candidates=120, observations=obs)
    ids = [c.node_id for c in cap.candidates]
    assert ids.count("R_a") == 1
    assert cap.candidates[0].origin == "observation"


def test_fresh_discovery_floor_when_panel_large():
    disc = DiscoverySettings(fresh_discovery_floor=24, max_candidates=120)
    obs = [
        _entry(f"R_o{i:03d}", f"obs/r{i}", "2026-08-20", repo_id=i) for i in range(200)
    ]
    hits = [_hit(f"R_s{i}", f"find/s{i}") for i in range(80)]
    cap = cap_candidates([], hits, max_candidates=120, disc=disc, observations=obs)
    origins = [c.origin for c in cap.candidates]
    assert origins.count("observation") == 96
    assert origins.count("search") > 0
    assert len(cap.candidates) <= 120
    assert origins.count("observation") <= 120 - 24


def test_preview_does_not_write_observations(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_keep", "acme/keep")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-08-24", "2026-08-24", "2026-09-07", "seed"),
    )
    conn.commit()
    before = conn.execute(
        "SELECT added_on, last_observed_on, state FROM observations"
    ).fetchall()
    board, snap_before, snap_after = build_board_from_db(
        date="2026-08-24", preview=True, clock=frozen_clock
    )
    assert board.mode == "provisional"
    assert snap_before == snap_after
    after = conn.execute(
        "SELECT added_on, last_observed_on, state FROM observations"
    ).fetchall()
    assert after == before
    n = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert n == 1


def test_identity_is_repo_id_across_rename(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_keep", "acme/keep")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-08-24", "2026-08-24", "2026-09-07", "seed"),
    )
    conn.execute(
        "UPDATE repos SET full_name='acme/renamed', name='renamed' WHERE id=?", (rid,)
    )
    conn.commit()
    node = repo_node("R_keep", "acme/renamed", topics=["mcp"])
    gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[])
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        "SELECT r.node_id, r.full_name FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
        (result.run_id,),
    ).fetchone()
    assert row == ("R_keep", "acme/renamed")
    obs = conn.execute("SELECT repo_id FROM observations").fetchall()
    assert obs == [(rid,)]


def test_seat_order_deterministic_when_budget_short():
    disc = DiscoverySettings(fresh_discovery_floor=1, max_candidates=3)
    obs = [
        _entry("R_c", "acme/c", "2026-08-22", repo_id=3),
        _entry("R_a", "acme/a", "2026-08-20", repo_id=1),
        _entry("R_b", "acme/b", "2026-08-21", repo_id=2),
    ]
    hits = [_hit("R_z", "acme/z")]
    cap = cap_candidates([], hits, max_candidates=3, disc=disc, observations=obs)
    # remaining 3, floor 1 → 2 observation seats, oldest added_on first
    assert [c.node_id for c in cap.candidates if c.origin == "observation"] == [
        "R_a",
        "R_b",
    ]
    assert cap.candidates[-1].origin == "search"
    cap2 = cap_candidates(
        [], hits, max_candidates=3, disc=disc, observations=list(reversed(obs))
    )
    assert [c.node_id for c in cap.candidates] == [c.node_id for c in cap2.candidates]


def test_admission_does_not_write_reviews_or_selected_rank(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_keep", "acme/keep")
    from foreshadow.models import ComponentScore, ScoreBreakdown

    bd = ScoreBreakdown(
        opportunity=ComponentScore(value=40, confidence="medium"),
        explosion=ComponentScore(value=None, confidence="low", missing=["v7"]),
        contribution=ComponentScore(value=20, confidence="medium"),
        momentum=ComponentScore(value=None, confidence="low", missing=["v7"]),
        real_user=ComponentScore(value=20, confidence="medium"),
        gap=ComponentScore(value=20, confidence="medium"),
        contribution_opp=ComponentScore(value=20, confidence="medium"),
        early_entry=ComponentScore(value=20, confidence="medium"),
        direction_fit=ComponentScore(value=80, confidence="medium"),
        maintainer=ComponentScore(value=20, confidence="medium"),
    )
    scored = ScoredRepo(owner="acme", full_name="acme/keep", breakdown=bd, evidence={})
    n = admit_from_scores(
        conn,
        today=frozen_clock.today(),
        scored_rows=[(rid, scored, {"node_id": "R_keep"})],
        selected_ids=set(),
        watchlist_ids=set(),
        disc=DiscoverySettings(),
    )
    assert n == 1
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
    assert conn.execute("SELECT selected_rank FROM scores").fetchall() == []
    reason = conn.execute(
        "SELECT reason FROM observations WHERE repo_id=?", (rid,)
    ).fetchone()[0]
    assert "opportunity" in reason


def test_low_opportunity_not_admitted(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_low", "acme/low")
    from foreshadow.models import ComponentScore, ScoreBreakdown

    bd = ScoreBreakdown(
        opportunity=ComponentScore(value=10, confidence="low"),
        explosion=ComponentScore(value=None, confidence="low", missing=["v7"]),
        contribution=ComponentScore(value=10, confidence="low"),
        momentum=ComponentScore(value=None, confidence="low", missing=["v7"]),
        real_user=ComponentScore(value=10, confidence="low"),
        gap=ComponentScore(value=10, confidence="low"),
        contribution_opp=ComponentScore(value=10, confidence="low"),
        early_entry=ComponentScore(value=10, confidence="low"),
        direction_fit=ComponentScore(value=10, confidence="low"),
        maintainer=ComponentScore(value=10, confidence="low"),
    )
    scored = ScoredRepo(owner="acme", full_name="acme/low", breakdown=bd)
    n = admit_from_scores(
        conn,
        today=frozen_clock.today(),
        scored_rows=[(rid, scored, {"node_id": "R_low"})],
        selected_ids=set(),
        watchlist_ids=set(),
        disc=DiscoverySettings(),
    )
    assert n == 0
