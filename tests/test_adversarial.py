"""Fuzz / edge cases for observation, identity, and partial GitHub. No score retune."""

from __future__ import annotations

from datetime import date
from random import Random

import pytest
from typer.testing import CliRunner

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.cli import app
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.db import connect, migrate
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.discover import (
    SearchHit,
    cap_candidates,
    discover_hydrate_snapshot,
    is_degraded,
    load_watchlist,
)
from foreshadow.pipeline.observation import (
    ObservationEntry,
    admit_from_scores,
    panel_cap,
)
from foreshadow.pipeline.score import ScoredRepo

_DESC = "A substantial project description for discovery tests."


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def _keep(node_id: str, full_name: str, **over) -> dict:
    over.setdefault("topics", ["mcp"])
    over.setdefault("forkCount", 3)
    over.setdefault("description", _DESC)
    return repo_node(node_id, full_name, **over)


def _hit(node_id: str, full_name: str) -> SearchHit:
    return SearchHit(
        node_id=node_id,
        full_name=full_name,
        query_key="A_mcp",
        pool="A",
        description=_DESC,
        topics=("mcp",),
        fork_count=2,
    )


def _entry(node_id: str, full_name: str, added: str, repo_id: int) -> ObservationEntry:
    return ObservationEntry(
        repo_id=repo_id,
        node_id=node_id,
        full_name=full_name,
        added_on=added,
        last_observed_on=added,
        expires_on="2099-01-01",
        reason="test",
    )


def _scored(full_name: str, opportunity: float, *, vetoed: bool = False) -> ScoredRepo:
    mid = ComponentScore(value=20, confidence="medium")
    bd = ScoreBreakdown(
        opportunity=ComponentScore(value=opportunity, confidence="medium"),
        explosion=ComponentScore(value=None, confidence="low", missing=["v7"]),
        contribution=mid,
        momentum=ComponentScore(value=None, confidence="low", missing=["v7"]),
        real_user=mid,
        gap=mid,
        contribution_opp=mid,
        early_entry=mid,
        direction_fit=ComponentScore(value=80, confidence="medium"),
        maintainer=mid,
        vetoed=vetoed,
        veto_reason="H2" if vetoed else None,
    )
    return ScoredRepo(
        owner=full_name.split("/", 1)[0],
        full_name=full_name,
        breakdown=bd,
        evidence={},
    )


def test_empty_watchlist_and_empty_observations_seats_search():
    hits = [_hit(f"R_s{i}", f"find/s{i}") for i in range(10)]
    cap = cap_candidates([], hits, max_candidates=120)
    assert cap.candidates
    assert all(c.origin == "search" for c in cap.candidates)
    assert cap.watchlist_truncated is False


def test_watchlist_fills_entire_cap_starves_observation_and_search():
    watch = [f"R_w{i:03d}" for i in range(120)]
    obs = [_entry(f"R_o{i:03d}", f"obs/r{i}", "2026-08-01", i + 1) for i in range(50)]
    hits = [_hit(f"R_s{i}", f"find/s{i}") for i in range(80)]
    cap = cap_candidates(watch, hits, max_candidates=120, observations=obs)
    assert len(cap.candidates) == 120
    assert all(c.origin == "watchlist" for c in cap.candidates)
    assert cap.watchlist_truncated is False
    assert {c.node_id for c in cap.candidates} == set(watch)


def test_watchlist_one_over_cap_truncates():
    watch = [f"R_w{i:03d}" for i in range(121)]
    cap = cap_candidates(watch, [], max_candidates=120)
    assert len(cap.candidates) == 120
    assert cap.watchlist_truncated is True
    assert cap.candidates[-1].node_id == "R_w119"


def test_panel_cap_extremes():
    assert panel_cap(DiscoverySettings()) == 96
    assert panel_cap(DiscoverySettings(max_candidates=0, fresh_discovery_floor=24)) == 0
    assert panel_cap(DiscoverySettings(max_candidates=1, fresh_discovery_floor=24)) == 0
    assert (
        panel_cap(DiscoverySettings(max_candidates=24, fresh_discovery_floor=24)) == 0
    )
    assert (
        panel_cap(DiscoverySettings(max_candidates=25, fresh_discovery_floor=24)) == 1
    )


def test_single_observation_and_single_search():
    obs = [_entry("R_o", "obs/one", "2026-08-20", 1)]
    hits = [_hit("R_s", "find/one")]
    cap = cap_candidates([], hits, max_candidates=120, observations=obs)
    origins = [c.origin for c in cap.candidates]
    assert origins[0] == "observation"
    assert "search" in origins
    assert {c.node_id for c in cap.candidates} == {"R_o", "R_s"}


def test_admission_determinism_thirty_tied_opportunity(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rng = Random(20260824)
    ids = list(range(30))
    rng.shuffle(ids)
    rows: list[tuple[int, ScoredRepo, dict]] = []
    for i in ids:
        nid = f"R_{i:02d}"
        full = f"acme/r{i:02d}"
        rid = seed_repo(conn, nid, full)
        rows.append((rid, _scored(full, 25), {"node_id": nid}))
    conn.commit()
    disc = DiscoverySettings()
    admitted_sets: list[frozenset[str]] = []
    for _ in range(8):
        shuffled = list(rows)
        rng.shuffle(shuffled)
        conn.execute("DELETE FROM observations")
        n = admit_from_scores(
            conn,
            today=frozen_clock.today(),
            scored_rows=shuffled,
            selected_ids=set(),
            watchlist_ids=set(),
            disc=disc,
        )
        assert n == disc.observation_admit_max
        nids = frozenset(
            row[0]
            for row in conn.execute(
                "SELECT r.node_id FROM observations o JOIN repos r ON r.id=o.repo_id"
            )
        )
        admitted_sets.append(nids)
    assert len(set(admitted_sets)) == 1
    assert admitted_sets[0] == frozenset(f"R_{i:02d}" for i in range(24))
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_admission_skips_vetoed_even_when_tied(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rows = []
    for i in range(3):
        nid = f"R_v{i}"
        rid = seed_repo(conn, nid, f"acme/v{i}")
        rows.append((rid, _scored(f"acme/v{i}", 25, vetoed=(i == 1)), {"node_id": nid}))
    n = admit_from_scores(
        conn,
        today=frozen_clock.today(),
        scored_rows=list(reversed(rows)),
        selected_ids=set(),
        watchlist_ids=set(),
        disc=DiscoverySettings(),
    )
    assert n == 2
    nids = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM observations o JOIN repos r ON r.id=o.repo_id"
        )
    }
    assert nids == {"R_v0", "R_v2"}


def test_rename_keeps_observation_lineage(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_keep", "acme/old")
    conn.execute(
        """
        INSERT INTO observations(repo_id, added_on, last_observed_on, expires_on, reason, state)
        VALUES (?,?,?,?,?, 'active')
        """,
        (rid, "2026-08-20", "2026-08-20", "2026-09-03", "opportunity 40"),
    )
    conn.execute(
        """
        INSERT INTO snapshots(repo_id, snapshot_date, captured_at, stars, completeness)
        VALUES (?,?,?,?,1)
        """,
        (rid, "2026-08-20", "t", 50),
    )
    conn.commit()
    node = _keep("R_keep", "acme/new")
    gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[])
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    repo = conn.execute(
        "SELECT id, node_id, full_name, status FROM repos WHERE node_id='R_keep'"
    ).fetchone()
    assert repo == (rid, "R_keep", "acme/new", "active")
    aliases = {
        row[0]
        for row in conn.execute(
            "SELECT full_name FROM repo_aliases WHERE repo_id=?", (rid,)
        )
    }
    assert "acme/old" in aliases
    obs = conn.execute(
        "SELECT repo_id, added_on, expires_on, reason, state FROM observations"
    ).fetchone()
    assert obs == (rid, "2026-08-20", "2026-09-03", "opportunity 40", "active")
    dates = {
        row[0]
        for row in conn.execute(
            "SELECT snapshot_date FROM snapshots WHERE repo_id=?", (rid,)
        )
    }
    assert dates == {"2026-08-20", "2026-08-24"}
    cand = conn.execute(
        "SELECT r.id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
        (result.run_id,),
    ).fetchone()
    assert cand[0] == rid


def test_missing_credential_exits_2_not_crash(tmp_home, frozen_clock, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.setattr("foreshadow.github.client.shutil.which", lambda _cmd: None)
    with pytest.raises(SystemExit) as ei:
        run_pipeline(clock=frozen_clock, force=False, llm=False)
    assert ei.value.code == 2
    db = tmp_home / "foreshadow.sqlite3"
    assert db.is_file()
    runner = CliRunner()
    cli = runner.invoke(app, ["run"])
    assert cli.exit_code == 2
    blob = (cli.stderr or "") + (cli.output or "")
    assert "missing GitHub token" in blob or "GitHub credentials unavailable" in blob


def test_one_repo_404_does_not_crash(tmp_home, frozen_clock, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    ok = _keep("R_ok", "acme/ok")
    gone = _keep("R_gone", "acme/gone")
    rid_ok = seed_repo(conn, "R_ok", "acme/ok")
    rid_gone = seed_repo(conn, "R_gone", "acme/gone")
    seed_review(conn, rid_ok, "watch", "2026-08-23T00:00:00+00:00")
    seed_review(conn, rid_gone, "watch", "2026-08-23T00:01:00+00:00")
    conn.commit()
    gh = FakeGitHub(
        nodes={"R_ok": ok, "R_gone": gone},
        missing={"R_gone"},
        search_nodes=[],
    )
    result = run_pipeline(
        clock=frozen_clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert result.skipped is False
    assert result.status in {"complete", "degraded"}
    statuses = {
        row[0]: row[1]
        for row in conn.execute(
            """
            SELECT r.node_id, c.hydrate_status
            FROM candidates c JOIN repos r ON r.id=c.repo_id
            """
        )
    }
    assert statuses["R_gone"] == "not_found"
    assert statuses["R_ok"] in {"ok", "incomplete"}
    snaps = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM snapshots s JOIN repos r ON r.id=s.repo_id"
        )
    }
    assert "R_ok" in snaps
    assert "R_gone" not in snaps
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 2


def test_rate_limit_one_repo_degrades_not_crash(tmp_home, frozen_clock, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    ok = _keep("R_ok", "acme/ok")
    rl = _keep("R_rl", "acme/limited")
    rid_ok = seed_repo(conn, "R_ok", "acme/ok")
    rid_rl = seed_repo(conn, "R_rl", "acme/limited")
    seed_review(conn, rid_ok, "watch", "2026-08-23T00:00:00+00:00")
    seed_review(conn, rid_rl, "watch", "2026-08-23T00:01:00+00:00")
    conn.commit()
    gh = FakeGitHub(
        nodes={"R_ok": ok, "R_rl": rl},
        rate_limit_ids={"R_rl"},
        search_nodes=[],
    )
    result = run_pipeline(
        clock=frozen_clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert result.skipped is False
    assert result.status == "degraded"
    assert is_degraded(result.source_health)
    assert int(result.source_health.get("hydrate_failed") or 0) >= 1
    statuses = {
        row[0]: row[1]
        for row in conn.execute(
            """
            SELECT r.node_id, c.hydrate_status
            FROM candidates c JOIN repos r ON r.id=c.repo_id
            """
        )
    }
    assert statuses["R_rl"] == "failed"
    assert statuses["R_ok"] in {"ok", "incomplete"}
    snaps = {
        row[0]
        for row in conn.execute(
            "SELECT r.node_id FROM snapshots s JOIN repos r ON r.id=s.repo_id"
        )
    }
    assert "R_ok" in snaps
    assert conn.execute("SELECT status FROM daily_runs").fetchone()[0] == "degraded"


def test_mixed_404_and_rate_limit_and_ok(tmp_home, frozen_clock, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    nodes = {
        "R_ok": _keep("R_ok", "acme/ok"),
        "R_gone": _keep("R_gone", "acme/gone"),
        "R_rl": _keep("R_rl", "acme/limited"),
    }
    for nid, full, when in (
        ("R_ok", "acme/ok", "2026-08-23T00:00:00+00:00"),
        ("R_gone", "acme/gone", "2026-08-23T00:01:00+00:00"),
        ("R_rl", "acme/limited", "2026-08-23T00:02:00+00:00"),
    ):
        rid = seed_repo(conn, nid, full)
        seed_review(conn, rid, "watch", when)
    conn.commit()
    gh = FakeGitHub(
        nodes=nodes,
        missing={"R_gone"},
        rate_limit_ids={"R_rl"},
        search_nodes=[],
    )
    result = run_pipeline(
        clock=frozen_clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert result.status == "degraded"
    watch = load_watchlist(conn, date(2026, 8, 24), Settings().scoring)
    assert {w.node_id for w in watch} == {"R_ok", "R_gone", "R_rl"}
