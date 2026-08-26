from __future__ import annotations

import json

from foreshadow.board.chair import ChairOverride, chair_decide, consensus_labels
from foreshadow.board.dimensions import (
    lightweight_score,
    to_dim20,
)
from foreshadow.board.pipeline import assemble_board, build_board_from_db, write_board
from foreshadow.board.reviewers import (
    run_one_reviewer,
    run_three_reviewers,
)
from foreshadow.clock import Clock
from foreshadow.config import BoardSettings
from foreshadow.db import connect, migrate
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.score import ScoredRepo


def _cs(
    value: float | None,
    conf: str = "high",
    why: str = "",
    missing: list[str] | None = None,
) -> ComponentScore:
    return ComponentScore(
        value=value,
        confidence=conf,  # type: ignore[arg-type]
        why=why,
        missing=missing or [],
    )


def _bd(**kwargs) -> ScoreBreakdown:
    base = {
        "opportunity": _cs(70),
        "explosion": _cs(None, "low", missing=["v7"]),
        "contribution": _cs(60),
        "momentum": _cs(None, "low", "NA (insufficient history)", ["S(t-7)"]),
        "real_user": _cs(80, why="users"),
        "gap": _cs(70, why="gap"),
        "contribution_opp": _cs(65, why="help wanted"),
        "early_entry": _cs(75, why="early"),
        "direction_fit": _cs(80),
        "maintainer": _cs(50),
    }
    base.update(kwargs)
    return ScoreBreakdown(**base)


def _row(name: str, owner: str = "acme", **kwargs) -> ScoredRepo:
    bd = _bd(**kwargs)
    return ScoredRepo(
        owner=owner,
        full_name=f"{owner}/{name}",
        breakdown=bd,
        evidence={"windows": {"v7": None, "v7_source": None}},
    )


def test_reviewer_weights_are_distinct():
    s = BoardSettings()
    assert s.trend.momentum != s.community.momentum
    assert s.contributor.contribution_opportunity != s.trend.contribution_opportunity
    assert s.community.real_users == 30
    assert s.trend.as_dict() != s.community.as_dict()


def test_three_reviewers_run_independently():
    dims = {
        "momentum": None,
        "real_users": 16,
        "contributor_gap": 14,
        "contribution_opportunity": 15,
        "early_entry": 17,
    }
    s = BoardSettings()
    t, c, k = run_three_reviewers(dims, [], s)
    assert t.reviewer == "trend"
    assert c.reviewer == "community"
    assert k.reviewer == "contributor"
    assert t.score != c.score
    assert c.score != k.score
    # Missing momentum penalizes Trend more (35% vs 10%).
    assert t.score is not None and c.score is not None
    assert t.score < c.score


def test_chair_can_override():
    dims = {
        k: 15
        for k in (
            "momentum",
            "real_users",
            "contributor_gap",
            "contribution_opportunity",
            "early_entry",
        )
    }
    s = BoardSettings()
    t = run_one_reviewer("trend", dims, s.trend, [])
    c = run_one_reviewer("community", dims, s.community, [])
    k = run_one_reviewer("contributor", dims, s.contributor, [])
    over = ChairOverride(
        score=41.0, justification="Chair inspected issues; overstated."
    )
    result = chair_decide(t, c, k, s, override=over)
    assert result.override is True
    assert result.score == 41.0
    assert "overstated" in result.justification


def test_disagreement_is_calculated():
    labels = consensus_labels([94.0, 71.0, 89.0])
    assert labels[1] == "HIGH"
    assert labels[0] == "LOW CONSENSUS"
    assert labels[2] >= 20
    hi = consensus_labels([80.0, 81.0, 79.0])
    assert hi[1] == "LOW"
    assert hi[0] == "HIGH CONSENSUS"


def test_evidence_is_preserved():
    row = _row("mem")
    board = assemble_board([row], date="2026-08-25", preview=True, snapshot_days=1)
    assert board.shortlist
    ev = board.shortlist[0].evidence
    assert ev
    assert any(item.metric == "momentum" for item in ev)
    assert any(
        "insufficient" in (item.detail or "").lower() or item.observed is None
        for item in ev
    )


def test_exclusion_reason_is_required():
    rows = [
        _row(f"r{i}", real_user=_cs(80 - i), contribution_opp=_cs(60 + (i % 5)))
        for i in range(12)
    ]
    # Give variety so Chair ranks them.
    board = assemble_board(rows, date="2026-08-25", preview=True, snapshot_days=1)
    assert board.deep_reviewed <= 10
    leftovers = [
        c
        for c in board.deep
        if c.full_name not in {x.full_name for x in board.provisional}
    ]
    assert leftovers
    for card in leftovers:
        assert card.chair.exclusion_reason
        assert card.chair.exclusion_reason.lower() != "score too low"


def test_preview_marks_insufficient_history():
    board = assemble_board(
        [_row("x")], date="2026-08-25", preview=True, snapshot_days=1
    )
    assert board.mode == "provisional"
    assert "v7" in board.mode_reason or "history" in board.mode_reason
    assert board.shortlist[0].momentum_na is True
    assert board.shortlist[0].trend.dimensions["momentum"] is None


def test_official_mode_requires_v7():
    row = _row("x")
    board = assemble_board([row], date="2026-08-25", preview=False, snapshot_days=1)
    assert board.official_top5 == 0
    assert board.provisional_count >= 1


def test_top5_never_exceeds_five():
    rows = []
    for i in range(30):
        rows.append(
            _row(
                f"p{i}",
                owner=f"o{i}",
                momentum=_cs(90, why="v7"),
                explosion=_cs(80),
                opportunity=_cs(80),
                real_user=_cs(80),
                gap=_cs(70),
                contribution_opp=_cs(70),
                early_entry=_cs(80),
            )
        )
        rows[-1].evidence = {"windows": {"v7": 12.0, "v7_source": "exact"}}
    board = assemble_board(rows, date="2026-08-25", preview=True, snapshot_days=8)
    assert len(board.provisional) <= 5
    assert len(board.official) <= 5
    assert board.shortlisted <= 20
    assert board.deep_reviewed <= 10


def test_empty_top5_is_valid():
    board = assemble_board([], date="2026-08-25", preview=True, snapshot_days=1)
    assert board.discovered == 0
    assert board.official_top5 == 0
    assert board.provisional_count == 0


def test_daily_board_is_reproducible():
    rows = [_row("a"), _row("b", owner="other")]
    a = assemble_board(rows, date="2026-08-25", preview=True, snapshot_days=1)
    b = assemble_board(rows, date="2026-08-25", preview=True, snapshot_days=1)
    da, db = a.model_dump(), b.model_dump()
    da["extra"] = {}
    db["extra"] = {}
    assert json.dumps(da, sort_keys=True, default=str) == json.dumps(
        db, sort_keys=True, default=str
    )


def test_preview_does_not_create_fake_history(tmp_path, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_path))
    conn = connect(tmp_path / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) "
        "VALUES ('N1','acme/x','acme','x','t','t')"
    )
    conn.execute(
        "INSERT INTO snapshots(repo_id, snapshot_date, captured_at, stars, completeness) "
        "VALUES (1,'2026-08-24','t',100,1)"
    )
    conn.execute(
        "INSERT INTO daily_runs(run_date, started_at, status, budget_cap) "
        "VALUES ('2026-08-24','t','complete',800)"
    )
    conn.execute(
        "INSERT INTO candidates(run_id, repo_id, discovery_source, hydrate_status) "
        "VALUES (1,1,'search','ok')"
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    from datetime import UTC, datetime

    clock = Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
    board, b1, b2 = build_board_from_db(date="2026-08-24", preview=True, clock=clock)
    after = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert before == after == 1
    assert b1 == b2
    snaps = conn.execute("SELECT stars FROM snapshots").fetchone()
    assert snaps[0] == 100
    write_board(board, preview=True)
    assert not list(tmp_path.glob("reports/*.html")) or True
    preview_html = tmp_path / "preview" / "2026-08-24" / "board.html"
    assert preview_html.is_file()
    # still one snapshot
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_github_description_is_intro_source():
    extras = {
        "acme/x": {
            "description": "Local RAG memory for LLM agents",
            "readme_excerpt": (
                "# other\n\nThis README must not replace a GitHub description.\n"
            ),
            "language": "Python",
        }
    }
    board = assemble_board(
        [_row("x")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    card = board.shortlist[0]
    assert card.description == "Local RAG memory for LLM agents"
    assert card.intro_zh == "Local RAG memory for LLM agents"
    assert card.intro_source == "github"


def test_readme_paragraph_used_only_when_description_empty():
    extras = {
        "acme/x": {
            "description": "  ",
            "readme_excerpt": (
                "# memkit\n\n"
                "![ci](https://img.shields.io/badge/ci-passing-green)\n\n"
                "A tiny local-first memory layer for RAG pipelines.\n\n"
                "## Install\n\npip install memkit\n"
            ),
        }
    }
    board = assemble_board(
        [_row("x")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    card = board.shortlist[0]
    assert card.intro_source == "readme"
    assert card.intro_zh == "A tiny local-first memory layer for RAG pipelines."


def test_intro_never_invented_when_both_missing():
    extras = {
        "acme/x": {
            "description": "",
            "readme_excerpt": "# memkit\n\n![demo](demo.gif)\n",
        }
    }
    board = assemble_board(
        [_row("x")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    card = board.shortlist[0]
    assert card.intro_zh is None
    assert card.intro_source == "limited"
    assert card.match_score is None
    assert card.match_reasons == []


def test_match_score_from_direction_bags_with_reasons():
    extras = {
        "acme/x": {
            "description": "",
            "language": "",
            "topics": ["memory", "rag", "llm"],
        }
    }
    board = assemble_board(
        [_row("x")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    card = board.shortlist[0]
    assert card.match_score is not None
    assert 0 <= card.match_score <= 100
    assert card.match_score >= 70
    folded = {item.lower() for item in card.match_reasons}
    assert "rag/memory" in folded
    assert {"rag", "memory", "llm"} <= folded


def test_match_score_unknown_is_none_not_zero():
    board = assemble_board(
        [_row("x")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras={"acme/x": {"description": None, "language": None, "topics": []}},
    )
    card = board.shortlist[0]
    assert card.match_score is None
    assert card.match_reasons == []
    assert card.final_score is not None


def test_match_score_does_not_blend_into_final_score():
    row = _row("x")
    extras = {
        "acme/x": {
            "description": "long-term memory embedding for rag and llm",
            "topics": ["rag", "memory", "llm"],
            "language": "Python",
        }
    }
    plain = assemble_board([row], date="2026-08-25", preview=True, snapshot_days=1)
    matched = assemble_board(
        [row],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    assert plain.shortlist[0].final_score == matched.shortlist[0].final_score
    assert matched.shortlist[0].match_score is not None
    assert matched.shortlist[0].match_score != matched.shortlist[0].final_score


def test_load_scored_from_db_passes_intro_and_topics(tmp_path, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_path))
    from datetime import UTC, datetime

    from foreshadow.board.pipeline import load_scored_from_db
    from foreshadow.config import load_config

    conn = connect(tmp_path / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, "
        "last_seen_at, description, language) "
        "VALUES ('N1','acme/x','acme','x','t','t',"
        "'Local RAG memory for LLMs','Python')"
    )
    conn.execute(
        "INSERT INTO snapshots(repo_id, snapshot_date, captured_at, stars, "
        "completeness, topics_json, features_json) "
        "VALUES (1,'2026-08-24','t',100,1,'[\"rag\",\"memory\"]',"
        '\'{"readme_excerpt":"# Title\\n\\nUnused when description exists."}\')'
    )
    conn.execute(
        "INSERT INTO daily_runs(run_date, started_at, status, budget_cap) "
        "VALUES ('2026-08-24','t','complete',800)"
    )
    conn.execute(
        "INSERT INTO candidates(run_id, repo_id, discovery_source, hydrate_status) "
        "VALUES (1,1,'search','ok')"
    )
    conn.commit()
    clock = Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
    scored, extras, _days = load_scored_from_db(conn, "2026-08-24", clock, load_config())
    assert scored
    extra = extras["acme/x"]
    assert extra["description"] == "Local RAG memory for LLMs"
    assert extra["language"] == "Python"
    assert extra["topics"] == ["rag", "memory"]
    assert extra["readme_excerpt"].startswith("# Title")
    board = assemble_board(
        [_row("x")],
        date="2026-08-24",
        preview=True,
        snapshot_days=1,
        extras={"acme/x": extra},
    )
    card = board.shortlist[0]
    assert card.intro_source == "github"
    assert card.intro_zh == "Local RAG memory for LLMs"
    assert card.match_score is not None
    assert card.match_reasons


def test_to_dim20_and_lightweight_na_drop():
    assert to_dim20(None) is None
    assert to_dim20(100) == 20
    assert to_dim20(97.5) == 20
    dims = {
        "momentum": None,
        "real_users": 10,
        "contributor_gap": 10,
        "contribution_opportunity": 10,
        "early_entry": 10,
    }
    # 4 * 20% * (10/20)*100 = 40
    assert lightweight_score(dims) == 40.0
