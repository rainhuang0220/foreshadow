"""Golden Path: discover → observe → v7 → board → local entry → remote refuse.

Walks the production pipeline with FakeGitHub. Does not insert final DB state,
skip admission, hand-write v7, or mock run_pipeline.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fakes import FakeGitHub, repo_node, seed_repo
from foreshadow.auth import ensure_local_user
from foreshadow.board.pipeline import build_board_from_db
from foreshadow.board.present import present_board
from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.db import connect, migrate
from foreshadow.mission import (
    REMOTE_ACTIONS,
    create_for_user,
    record_remote_refused,
    refuse_remote_action,
    setup_local_environment,
)
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline import FINISHED_RUN_STATUSES, load_score_input, run_pipeline
from foreshadow.pipeline.observation import admit_from_scores, load_active
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.select import is_official_eligible

_DESC = (
    "Persistent memory layer for MCP agents with tests, issues, "
    "and a contributing guide."
)


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("FORESHADOW_SKIP_CLONE", raising=False)


def _keep(stars: int, full_name: str = "acme/keep") -> dict:
    return repo_node(
        "R_keep",
        full_name,
        stargazerCount=stars,
        forkCount=8,
        topics=["mcp", "agents", "llm"],
        description=_DESC,
        issuesOpen={"totalCount": 16},
        issuesClosed={"totalCount": 12},
        prsOpen={"totalCount": 3},
        contributing={"text": "# Contributing\nWe welcome issues and small PRs.\n"},
        readme={
            "text": "# keep\n\npip install keep\n\nMCP agent memory.\n",
            "byteSize": 80,
        },
        gfi={"totalCount": 4},
        helpWanted={"totalCount": 3},
    )


def _fresh(day: int) -> dict:
    return repo_node(
        f"R_new{day}",
        f"acme/fresh{day}",
        topics=["mcp"],
        forkCount=2,
        description="A substantial project description for discovery tests.",
    )


def _stub_git(root: Path) -> None:
    git = root / ".git"
    git.mkdir(parents=True, exist_ok=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    pack = git / "objects" / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "pack-stub.pack").write_bytes(b"PACK")


def _clone_runner():
    def runner(cmd, **_k):
        if "clone" in cmd:
            dest = Path(cmd[-1])
            dest.mkdir(parents=True)
            _stub_git(dest)
            (dest / "README.md").write_text("# keep\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return runner


def test_golden_path_observe_v7_board_enter_remote_refused(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    settings = Settings()
    assert settings.scoring.min_opportunity == 55
    assert settings.scoring.min_explosion == 35
    assert settings.discovery.observation_admit_min == 25
    node = _keep(100)
    gh = FakeGitHub(
        nodes={"R_keep": node},
        search_by_day={"2026-08-24": [node]},
        contributors={
            "acme/keep": [
                {"login": "alice", "type": "User"},
                {"login": "bob", "type": "User"},
                {"login": "carol", "type": "User"},
            ]
        },
    )
    start = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    day0_hydrated = None
    for day in range(8):
        clock = Clock(now=start + timedelta(days=day))
        today = clock.today().isoformat()
        gh.begin_day(clock.today())
        node["stargazerCount"] = 100 + day * 10
        fresh = _fresh(day)
        gh.nodes[fresh["id"]] = fresh
        if day == 0:
            gh.search_by_day[today] = [node]
        else:
            gh.search_by_day[today] = [fresh]
        result = run_pipeline(
            clock=clock, force=False, llm=False, client=gh, settings=settings
        )
        assert result.skipped is False
        assert "R_keep" in gh.hydrate_ids
        if day == 0:
            day0_hydrated = list(gh.hydrate_ids)
            assert result.source_health.get("system_observed_count", 0) >= 1
            md = Path(result.report_path).read_text(encoding="utf-8")
            assert "observation panel" in md
            board0, before0, after0 = build_board_from_db(
                date=today, preview=False, clock=clock
            )
            assert before0 == after0
            card0 = next(
                (c for c in board0.shortlist if c.full_name == "acme/keep"), None
            )
            assert card0 is not None
            assert card0.observation_reason
            assert "opportunity" in card0.observation_reason
        else:
            assert "R_keep" in gh.hydrate_ids
            assert fresh["id"] in gh.nodes
            assert result.source_health.get("fresh_discovery_count", 0) >= 1
        dup = run_pipeline(
            clock=clock, force=False, llm=False, client=gh, settings=settings
        )
        assert dup.skipped is True
        assert dup.skip_reason == "same_day"
        assert dup.status in {"complete", "degraded"}

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
    assert len(dates) == 8
    obs = conn.execute(
        """
        SELECT o.added_on, o.expires_on, o.state, r.node_id
        FROM observations o JOIN repos r ON r.id=o.repo_id
        WHERE r.node_id='R_keep'
        """
    ).fetchone()
    assert obs is not None, "production admission must seat Repo A on Day 0"
    assert obs[0] == "2026-08-24"
    assert obs[2] == "active"
    v7 = conn.execute(
        """
        SELECT json_extract(s.evidence_json, '$.windows.v7')
        FROM scores s
        JOIN daily_runs d ON d.id=s.run_id
        JOIN repos r ON r.id=s.repo_id
        WHERE d.run_date='2026-08-31' AND r.node_id='R_keep' AND s.score_version='v1'
        """
    ).fetchone()
    assert v7 is not None and v7[0] is not None
    assert abs(float(v7[0]) - 10.0) < 1e-9
    explosion = conn.execute(
        """
        SELECT s.explosion FROM scores s
        JOIN daily_runs d ON d.id=s.run_id
        JOIN repos r ON r.id=s.repo_id
        WHERE d.run_date='2026-08-31' AND r.node_id='R_keep' AND s.score_version='v1'
        """
    ).fetchone()
    assert explosion is not None and explosion[0] is not None
    rid = conn.execute("SELECT id FROM repos WHERE node_id='R_keep'").fetchone()[0]
    data = load_score_input(conn, int(rid))
    scored = score_repo(
        data,
        clock=Clock(now=datetime(2026, 8, 31, 0, 5, tzinfo=UTC)),
        scoring=settings.scoring,
    )
    eligible = is_official_eligible(
        scored,
        min_opportunity=settings.scoring.min_opportunity,
        min_explosion=settings.scoring.min_explosion,
    )
    selected = conn.execute(
        """
        SELECT selected_rank FROM scores s
        JOIN daily_runs d ON d.id=s.run_id
        WHERE d.run_date='2026-08-31' AND s.repo_id=? AND s.score_version='v1'
        """,
        (rid,),
    ).fetchone()
    if eligible:
        assert selected is not None and selected[0] == 1
    stars = conn.execute(
        """
        SELECT s.stars FROM snapshots s JOIN repos r ON r.id=s.repo_id
        WHERE r.node_id='R_keep' AND s.snapshot_date='2026-08-31'
        """
    ).fetchone()[0]
    assert stars == 170
    assert day0_hydrated is not None

    clock = Clock(now=datetime(2026, 8, 31, 12, 0, tzinfo=UTC))
    doc, before, after = build_board_from_db(
        date="2026-08-31", preview=False, clock=clock
    )
    assert before == after
    view = present_board(doc)
    names = [c["full_name"] for c in view["candidates"]]
    assert "acme/keep" in names or any("keep" in n for n in names)
    keep_card = next((c for c in view["candidates"] if "keep" in c["full_name"]), None)
    if keep_card is not None:
        assert keep_card.get("observation_zh")

    uid = ensure_local_user(conn)
    mission = create_for_user(
        conn, user_id=uid, full_name="acme/keep", data_dir=tmp_home
    )
    setup = setup_local_environment(
        conn,
        mission.id or 0,
        uid,
        tmp_home,
        runner=_clone_runner(),
    )
    dest_status = setup["mission"].get("status")
    assert dest_status == "WAITING_USER_APPROVAL"
    assert setup["clone"].get("ok") is True
    local = Path(str(setup["mission"].get("local_path") or mission.local_path))
    assert (local / "FORESHADOW.md").is_file()
    assert (local / "ISSUE_DRAFT.md").is_file()
    for action in ("create_pr", "push", "comment"):
        refused = refuse_remote_action(action)
        assert refused["ok"] is False
        assert refused["blocked"] is True
        assert refused["status"] == "WAITING_USER_APPROVAL"
    for action in REMOTE_ACTIONS:
        out = record_remote_refused(
            conn, user_id=uid, action=action, mission_id=mission.id
        )
        assert out["blocked"] is True
        assert out["ok"] is False


def test_degraded_same_day_skips_without_force(tmp_home, frozen_clock, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    node = _keep(100)
    gh = FakeGitHub(
        nodes={"R_keep": node},
        search_nodes=[node],
        search_total_override=100,
    )
    first = run_pipeline(
        clock=frozen_clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert first.skipped is False
    assert first.status == "degraded"
    calls = gh.hydrate_calls
    second = run_pipeline(
        clock=frozen_clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert second.skipped is True
    assert second.status == "degraded"
    assert second.skip_reason == "same_day"
    assert gh.hydrate_calls == calls
    forced = run_pipeline(
        clock=frozen_clock, force=True, llm=False, client=gh, settings=Settings()
    )
    assert forced.skipped is False
    assert gh.hydrate_calls > calls


def test_complete_same_day_skips_without_force(tmp_home, frozen_clock, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    node = repo_node(
        "R_toy",
        "acme/toy",
        topics=["mcp"],
        description="A substantial project description for skip tests.",
    )
    gh = FakeGitHub(nodes={"R_toy": node}, search_nodes=[node])
    first = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert first.skipped is False
    assert first.status == "complete"
    n1 = gh.hydrate_calls
    skipped = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert skipped.skipped is True
    assert skipped.status == "complete"
    assert skipped.skip_reason == "same_day"
    assert skipped.status in FINISHED_RUN_STATUSES
    assert gh.hydrate_calls == n1
    forced = run_pipeline(clock=frozen_clock, force=True, llm=False, client=gh)
    assert forced.skipped is False
    assert gh.hydrate_calls > n1


def test_timezone_shanghai_matches_utc_snapshot_date(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    utc = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
    shanghai = utc.astimezone(ZoneInfo("Asia/Shanghai"))
    assert shanghai.date().isoformat() == "2026-08-25"
    clock_utc = Clock(now=utc)
    clock_sha = Clock(now=shanghai)
    assert clock_utc.today() == clock_sha.today()
    assert clock_utc.today().isoformat() == "2026-08-24"
    node = repo_node(
        "R_tz",
        "acme/tz",
        topics=["mcp"],
        description="A substantial project description for timezone identity.",
    )
    gh = FakeGitHub(nodes={"R_tz": node}, search_nodes=[node])
    gh.begin_day(clock_utc.today())
    first = run_pipeline(clock=clock_utc, force=False, llm=False, client=gh)
    assert first.skipped is False
    n1 = gh.hydrate_calls
    skipped = run_pipeline(clock=clock_sha, force=False, llm=False, client=gh)
    assert skipped.skipped is True
    assert skipped.status in FINISHED_RUN_STATUSES
    assert gh.hydrate_calls == n1
    conn = connect(tmp_home / "foreshadow.sqlite3")
    dates = {
        row[0] for row in conn.execute("SELECT DISTINCT snapshot_date FROM snapshots")
    }
    assert dates == {"2026-08-24"}
    runs = {row[0] for row in conn.execute("SELECT run_date FROM daily_runs")}
    assert runs == {"2026-08-24"}


def test_ttl_day14_inclusive_day15_expires(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    settings = Settings()
    assert settings.discovery.observation_ttl_days == 14
    node = _keep(100)
    fresh = repo_node(
        "R_fresh",
        "acme/fresh",
        topics=["mcp"],
        forkCount=2,
        description="A substantial fresh discovery subject used in TTL tests.",
    )
    start = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    gh = FakeGitHub(
        nodes={"R_keep": node, "R_fresh": fresh},
        search_by_day={"2026-08-24": [node]},
        contributors={
            "acme/keep": [
                {"login": "alice", "type": "User"},
                {"login": "bob", "type": "User"},
                {"login": "carol", "type": "User"},
            ],
            "acme/fresh": [{"login": "dana", "type": "User"}],
        },
    )
    clock0 = Clock(now=start)
    gh.begin_day(clock0.today())
    day0 = run_pipeline(
        clock=clock0, force=False, llm=False, client=gh, settings=settings
    )
    assert day0.skipped is False
    conn = connect(tmp_home / "foreshadow.sqlite3")
    row = conn.execute(
        """
        SELECT o.added_on, o.expires_on, o.state
        FROM observations o JOIN repos r ON r.id=o.repo_id
        WHERE r.node_id='R_keep'
        """
    ).fetchone()
    assert row == ("2026-08-24", "2026-09-07", "active")

    clock14 = Clock(now=start + timedelta(days=14))
    assert clock14.today().isoformat() == "2026-09-07"
    gh.begin_day(clock14.today())
    gh.search_by_day["2026-09-07"] = [fresh]
    day14 = run_pipeline(
        clock=clock14, force=False, llm=False, client=gh, settings=settings
    )
    assert day14.skipped is False
    conn = connect(tmp_home / "foreshadow.sqlite3")
    assert any(e.node_id == "R_keep" for e in load_active(conn, clock14.today()))
    run14 = conn.execute(
        "SELECT id FROM daily_runs WHERE run_date='2026-09-07'"
    ).fetchone()[0]
    ids14 = {
        r[0]
        for r in conn.execute(
            "SELECT r.node_id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
            (run14,),
        )
    }
    assert "R_keep" in ids14
    assert "R_keep" in gh.hydrate_ids

    clock15 = Clock(now=start + timedelta(days=15))
    assert clock15.today().isoformat() == "2026-09-08"
    gh.begin_day(clock15.today())
    gh.search_by_day["2026-09-08"] = [fresh]
    day15 = run_pipeline(
        clock=clock15, force=False, llm=False, client=gh, settings=settings
    )
    assert day15.skipped is False
    conn = connect(tmp_home / "foreshadow.sqlite3")
    active = load_active(conn, clock15.today())
    assert all(e.node_id != "R_keep" for e in active)
    assert any(e.node_id == "R_fresh" for e in active)
    state = conn.execute(
        """
        SELECT o.state FROM observations o JOIN repos r ON r.id=o.repo_id
        WHERE r.node_id='R_keep'
        """
    ).fetchone()[0]
    assert state == "expired"
    run15 = conn.execute(
        "SELECT id FROM daily_runs WHERE run_date='2026-09-08'"
    ).fetchone()[0]
    ids15 = {
        r[0]
        for r in conn.execute(
            "SELECT r.node_id FROM candidates c JOIN repos r ON r.id=c.repo_id WHERE c.run_id=?",
            (run15,),
        )
    }
    assert "R_keep" not in ids15
    assert "R_fresh" in ids15


def test_rename_day3_continues_lineage(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    settings = Settings()
    node = _keep(100, full_name="owner/A")
    fresh = repo_node(
        "R_fresh",
        "owner/fresh",
        topics=["mcp"],
        forkCount=2,
        description="A substantial fresh discovery subject used in rename tests.",
    )
    gh = FakeGitHub(
        nodes={"R_keep": node, "R_fresh": fresh},
        search_by_day={"2026-08-24": [node]},
        contributors={
            "owner/A": [
                {"login": "alice", "type": "User"},
                {"login": "bob", "type": "User"},
            ],
            "owner/B": [
                {"login": "alice", "type": "User"},
                {"login": "bob", "type": "User"},
            ],
            "owner/fresh": [{"login": "carol", "type": "User"}],
        },
    )
    start = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    rid = None
    for day in range(4):
        clock = Clock(now=start + timedelta(days=day))
        today = clock.today().isoformat()
        gh.begin_day(clock.today())
        node["stargazerCount"] = 100 + day * 10
        if day == 0:
            gh.search_by_day[today] = [node]
        else:
            gh.search_by_day[today] = [fresh]
        if day == 3:
            node["nameWithOwner"] = "owner/B"
            node["url"] = "https://github.com/owner/B"
        result = run_pipeline(
            clock=clock, force=False, llm=False, client=gh, settings=settings
        )
        assert result.skipped is False
        conn = connect(tmp_home / "foreshadow.sqlite3")
        row = conn.execute(
            "SELECT id, full_name FROM repos WHERE node_id='R_keep'"
        ).fetchone()
        rid = int(row[0])
        if day < 3:
            assert row[1] == "owner/A"
        else:
            assert row[1] == "owner/B"
        assert "R_keep" in gh.hydrate_ids
    conn = connect(tmp_home / "foreshadow.sqlite3")
    assert (
        conn.execute("SELECT COUNT(*) FROM repos WHERE node_id='R_keep'").fetchone()[0]
        == 1
    )
    aliases = {
        a[0]
        for a in conn.execute(
            "SELECT full_name FROM repo_aliases WHERE repo_id=?", (rid,)
        )
    }
    assert "owner/A" in aliases
    dates = [
        row[0]
        for row in conn.execute(
            """
            SELECT s.snapshot_date FROM snapshots s
            WHERE s.repo_id=? ORDER BY s.snapshot_date
            """,
            (rid,),
        )
    ]
    assert dates == ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27"]
    obs = conn.execute(
        "SELECT repo_id, state FROM observations WHERE repo_id=?", (rid,)
    ).fetchone()
    assert obs == (rid, "active")


def _equal_opp_scored(full_name: str) -> ScoredRepo:
    hi = ComponentScore(value=40.0, confidence="medium")
    bd = ScoreBreakdown(
        opportunity=hi,
        explosion=ComponentScore(value=None, confidence="low", missing=["v7"]),
        contribution=hi,
        momentum=ComponentScore(value=None, confidence="low", missing=["v7"]),
        real_user=hi,
        gap=hi,
        contribution_opp=hi,
        early_entry=hi,
        direction_fit=hi,
        maintainer=hi,
    )
    return ScoredRepo(
        owner=full_name.split("/", 1)[0],
        full_name=full_name,
        breakdown=bd,
    )


def test_admission_shuffled_equal_opportunity_is_deterministic(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    scored_rows = []
    for node_id, full_name in (("R_c", "acme/c"), ("R_a", "acme/a"), ("R_b", "acme/b")):
        rid = seed_repo(conn, node_id, full_name)
        scored_rows.append((rid, _equal_opp_scored(full_name), {"node_id": node_id}))
    conn.commit()
    disc = DiscoverySettings(observation_admit_max=2, observation_admit_min=25)
    admitted: list[list[str]] = []
    rng = random.Random(0)
    for _ in range(8):
        shuffled = list(scored_rows)
        rng.shuffle(shuffled)
        conn.execute("DELETE FROM observations")
        conn.commit()
        n = admit_from_scores(
            conn,
            today=datetime(2026, 8, 24, tzinfo=UTC).date(),
            scored_rows=shuffled,
            selected_ids=set(),
            watchlist_ids=set(),
            disc=disc,
        )
        assert n == 2
        got = [
            row[0]
            for row in conn.execute(
                """
                SELECT r.node_id FROM observations o
                JOIN repos r ON r.id=o.repo_id
                ORDER BY r.node_id
                """
            )
        ]
        admitted.append(got)
        assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
    assert admitted[0] == ["R_a", "R_b"]
    assert all(item == admitted[0] for item in admitted)
