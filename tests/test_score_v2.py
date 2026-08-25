from copy import deepcopy

from fakes import FakeGitHub, repo_node
from foreshadow.db import connect
from foreshadow.pipeline.compare import assign_pool_ranks, rank_delta
from foreshadow.pipeline.score import late, score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2
from foreshadow.pipeline.select import select_top


def _phase_b(**over) -> dict:
    feat = {
        "phase": "B",
        "u_issue": 8,
        "u_issue_ext": 7,
        "issue_sample_n": 20,
        "bug_n": 4,
        "talk_n": 3,
        "usage_closed_n": 2,
        "help_n": 1,
        "unassigned_help": 2,
        "repeat_clusters": 2,
        "maint_touch": 0.85,
        "health_percentage": 80,
        "readme_install": True,
        "readme_excerpt": "pip install toy\n",
        "gap_ci": 0,
        "gap_tests": 0,
        "gap_docs": 0,
        "tree_names": ["src", "pyproject.toml", "README.md"],
        "has_workflows": True,
    }
    feat.update(over)
    return feat


def small_active() -> dict:
    return {
        "owner": "seed",
        "name": "tinykit",
        "full_name": "seed/tinykit",
        "node_id": "R_small_active",
        "description": "long-term memory embedding layer for agents",
        "topics": ["memory", "rag", "llm"],
        "language": "Python",
        "license_spdx": "MIT",
        "age_days": 41,
        "pushed_age_days": 1,
        "S": 73,
        "F": 9,
        "C": 5,
        "has_issues": True,
        "U_issue": 9,
        "U_commit_30d": 4,
        "I_open": 6,
        "snapshots": [{"date": "2026-08-24", "stars": 73, "forks": 9}],
        "features": _phase_b(),
    }


def small_stagnant() -> dict:
    return {
        "owner": "old",
        "name": "tinykit",
        "full_name": "old/tinykit",
        "node_id": "R_small_stale",
        "description": "abandoned memory notes",
        "topics": ["memory"],
        "language": "Python",
        "license_spdx": "MIT",
        "age_days": 800,
        "pushed_age_days": 220,
        "S": 73,
        "F": 1,
        "C": 5,
        "has_issues": True,
        "U_issue": 0,
        "U_commit_30d": 0,
        "I_open": 1,
        "snapshots": [{"date": "2026-08-24", "stars": 73, "forks": 1}],
        "features": _phase_b(
            u_issue=0,
            u_issue_ext=0,
            issue_sample_n=3,
            bug_n=0,
            talk_n=0,
            usage_closed_n=0,
            help_n=0,
            unassigned_help=0,
            repeat_clusters=0,
            maint_touch=0.0,
            health_percentage=20,
        ),
    }


def large_mature() -> dict:
    return {
        "owner": "giant",
        "name": "infra",
        "full_name": "giant/infra",
        "node_id": "R_large_mature",
        "description": "core infrastructure runtime",
        "topics": ["infra"],
        "language": "Go",
        "license_spdx": "MIT",
        "age_days": 1400,
        "pushed_age_days": 12,
        "S": 2800,
        "F": 240,
        "C": 190,
        "has_issues": True,
        "U_issue": 40,
        "U_commit_30d": 25,
        "I_open": 80,
        "snapshots": [{"date": "2026-08-24", "stars": 2800, "forks": 240}],
        "features": _phase_b(
            u_issue=40,
            u_issue_ext=30,
            issue_sample_n=80,
            bug_n=20,
            talk_n=15,
            usage_closed_n=10,
            help_n=8,
            unassigned_help=0,
            repeat_clusters=1,
            maint_touch=0.05,
            health_percentage=90,
            tree_names=["src", "go.mod", "README.md", "CONTRIBUTING.md"],
        ),
    }


def test_v1_score_unchanged(frozen_clock):
    repo = small_active()
    v1 = score_repo(deepcopy(repo), clock=frozen_clock)
    again = score_repo(deepcopy(repo), clock=frozen_clock)
    assert v1.breakdown.opportunity.value == again.breakdown.opportunity.value
    assert v1.breakdown.early_entry.why.startswith("micro/early") or "late_" in (
        v1.breakdown.early_entry.why or ""
    )
    assert late(20_000, 1) is True
    assert late(73, 5) is False
    assert "score_version" not in v1.evidence


def test_v2_score_is_versioned(frozen_clock):
    scored = score_repo_v2(small_active(), clock=frozen_clock)
    assert scored.evidence["score_version"] == "v2"
    assert scored.breakdown.opportunity.value is not None
    assert "star_growth_status" in scored.evidence
    assert scored.evidence["star_growth"] is None


def test_rank_delta_is_correct():
    assert rank_delta(34, 5) == 29
    assert rank_delta(6, 31) == -25
    assert rank_delta(None, 1) is None
    a = score_repo(small_active())
    b = score_repo(large_mature())
    items = [
        (a, {"S": 73, "node_id": "R_small_active"}),
        (b, {"S": 2800, "node_id": "R_large_mature"}),
    ]
    ranks = assign_pool_ranks(items)
    assert set(ranks) == {"R_small_active", "R_large_mature"}
    assert sorted(ranks.values()) == [1, 2]


def test_small_active_beats_large_mature(frozen_clock):
    small = score_repo_v2(small_active(), clock=frozen_clock)
    large = score_repo_v2(large_mature(), clock=frozen_clock)
    s_opp = small.breakdown.opportunity.value
    l_opp = large.breakdown.opportunity.value
    assert s_opp is not None and l_opp is not None
    assert s_opp > l_opp


def test_small_stagnant_does_not_win(frozen_clock):
    stale = score_repo_v2(small_stagnant(), clock=frozen_clock)
    large = score_repo_v2(large_mature(), clock=frozen_clock)
    active = score_repo_v2(small_active(), clock=frozen_clock)
    stale_opp = stale.breakdown.opportunity.value
    assert stale_opp is not None
    assert stale_opp < 40
    assert stale_opp < active.breakdown.opportunity.value
    assert stale.breakdown.early_entry.value < active.breakdown.early_entry.value
    # Being small is not enough: stagnant 73★ must not beat the mature repo
    # solely on star count. If it does, the formula is wrong — fail honestly.
    assert stale_opp < large.breakdown.opportunity.value


def test_maturity_penalty_is_soft(frozen_clock):
    large = score_repo_v2(large_mature(), clock=frozen_clock)
    assert large.breakdown.vetoed is False
    assert large.breakdown.opportunity.value is not None
    assert large.breakdown.early_entry.value is not None
    assert large.breakdown.early_entry.value > 0
    why = large.breakdown.early_entry.why
    assert "late_now" not in why
    assert "entry_window" in why


def test_unknown_is_not_zero(frozen_clock):
    repo = {
        "owner": "acme",
        "name": "partial",
        "full_name": "acme/partial",
        "description": "memory rag llm",
        "license_spdx": "MIT",
        "age_days": 75,
        "pushed_age_days": 1,
        "S": 90,
        "F": 8,
        "has_issues": True,
        "snapshots": [{"date": "2026-08-24", "stars": 90, "forks": 8}],
        "features": {"phase": "A", "readme_excerpt": "pip install partial\n"},
    }
    v1 = score_repo(repo, clock=frozen_clock)
    v2 = score_repo_v2(repo, clock=frozen_clock)
    assert v1.breakdown.gap.value is None
    assert v2.breakdown.gap.value is None
    assert v1.breakdown.early_entry.value is None
    assert v2.breakdown.early_entry.value is None
    assert v2.evidence["star_growth"] is None
    assert v2.breakdown.momentum.value is None or v2.breakdown.explosion.value is None


def test_external_activity_is_not_star_growth(frozen_clock):
    repo = small_active()
    repo["features"] = _phase_b()
    repo["features"]["commits_7d"] = 20
    repo["features"]["issues_created_7d"] = 12
    scored = score_repo_v2(repo, clock=frozen_clock)
    assert scored.evidence["star_growth"] is None
    assert scored.evidence["star_growth_status"] == "UNKNOWN"
    assert scored.breakdown.explosion.value is None
    assert "v7" in (scored.breakdown.explosion.missing or [])
    assert scored.evidence["windows"]["v7"] is None
    assert "commits_7d" not in str(scored.evidence["windows"])


def test_official_v7_requirement_unchanged(frozen_clock):
    v1 = score_repo(small_active(), clock=frozen_clock)
    assert v1.breakdown.explosion.value is None
    assert v1.breakdown.momentum.value is None or v1.breakdown.momentum.missing
    top = select_top(
        [v1], min_opportunity=55, min_explosion=35, max_per_owner=2
    )
    assert top == []
    v2 = score_repo_v2(small_active(), clock=frozen_clock)
    assert v2.breakdown.explosion.value is None
    assert select_top([v2], min_opportunity=55, min_explosion=35) == []


def test_official_top5_still_uses_v1(tmp_home, frozen_clock, monkeypatch):
    from foreshadow.config import Settings
    from foreshadow.pipeline import run_pipeline

    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    node = repo_node("R_toy", "acme/toy", description="long-term memory embedding layer")
    gh = FakeGitHub(nodes={"R_toy": node}, search_nodes=[node])
    result = run_pipeline(
        clock=frozen_clock, force=True, llm=False, client=gh, settings=Settings()
    )
    conn = connect(tmp_home / "foreshadow.sqlite3")
    versions = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT score_version FROM scores WHERE run_id IN "
            "(SELECT id FROM daily_runs)"
        )
    }
    assert versions == {"v1", "v2"}
    v2_sel = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE score_version='v2' AND selected_rank IS NOT NULL"
    ).fetchone()[0]
    assert v2_sel == 0
    v1_sel = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE score_version='v1' AND selected_rank IS NOT NULL"
    ).fetchone()[0]
    assert v1_sel == 0
    assert result.top5_count == 0
    compared = conn.execute("SELECT COUNT(*) FROM score_compare").fetchone()[0]
    assert compared >= 1
