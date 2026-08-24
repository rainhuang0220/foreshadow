from copy import deepcopy

import pytest

from foreshadow.config import ScoringSettings
from foreshadow.models import ComponentScore
from foreshadow.pipeline.score import mix_opportunity, score_repo
from foreshadow.pipeline.select import select_top


def _hi(value: float = 100.0) -> ComponentScore:
    return ComponentScore(value=value, confidence="high")


def test_na_mix_drops_momentum_term_no_renormalize():
    na = ComponentScore(value=None, confidence="low", missing=["v7"])
    components = {
        "momentum": na,
        "real_user": _hi(),
        "gap": _hi(),
        "contribution_opp": _hi(),
        "early_entry": _hi(),
        "direction_fit": _hi(),
        "maintainer": _hi(),
    }
    opp = mix_opportunity(components, ScoringSettings())
    assert opp.value == pytest.approx(80)
    assert opp.value != pytest.approx(90)
    assert opp.value != pytest.approx(100)
    assert opp.value != pytest.approx(50)
    assert "momentum" in opp.missing
    assert components["momentum"].value is None


def test_na_mix_drops_two_terms():
    na = ComponentScore(value=None, confidence="low")
    components = {
        "momentum": na,
        "real_user": _hi(),
        "gap": _hi(),
        "contribution_opp": _hi(),
        "early_entry": _hi(),
        "direction_fit": _hi(),
        "maintainer": na,
    }
    opp = mix_opportunity(components, ScoringSettings())
    assert opp.value == pytest.approx(75)


def test_phase_a_components_na_when_c_missing(frozen_clock):
    repo = {
        "owner": "acme",
        "name": "partial",
        "full_name": "acme/partial",
        "description": "memory rag llm",
        "license_spdx": "MIT",
        "age_days": 75,
        "pushed_age_days": 1,
        "S": 900,
        "F": 85,
        "has_issues": True,
        "direction_fit": 80,
        "snapshots": [
            {"date": "2026-08-24", "stars": 900, "forks": 85},
            {"date": "2026-08-17", "stars": 200, "forks": 18},
            {"date": "2026-07-25", "stars": 180, "forks": 15},
        ],
        "features": {"phase": "A", "readme_excerpt": "pip install partial\n"},
    }
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.real_user.value is None
    assert bd.contribution_opp.value is None
    assert bd.gap.value is None
    assert bd.early_entry.value is None
    assert bd.momentum.value is not None


def test_confidence_low_first_when_tree_missing(frozen_clock, repo_fixture):
    repo = repo_fixture("memkit.json")
    repo["features"] = {**repo["features"], "tree_names": None}
    scored = score_repo(repo, clock=frozen_clock)
    assert scored.breakdown.momentum.value is not None
    assert scored.breakdown.momentum.confidence in {"medium", "high"}
    assert scored.breakdown.opportunity.confidence == "low"
    assert "tree_missing" in scored.breakdown.flags
    assert select_top([scored]) == []


def test_confidence_low_when_v7_na(frozen_clock, repo_fixture):
    repo = repo_fixture("memkit.json")
    repo["snapshots"] = [repo["snapshots"][0]]
    scored = score_repo(repo, clock=frozen_clock)
    assert scored.breakdown.momentum.value is None
    assert scored.breakdown.opportunity.confidence == "low"


def test_missing_tree_not_guessed_as_zero(frozen_clock, repo_fixture):
    repo = repo_fixture("memkit.json")
    repo["features"] = {k: v for k, v in repo["features"].items() if k != "tree_names"}
    repo["features"]["tree_names"] = None
    repo["features"]["gap_ci"] = None
    repo["features"]["gap_tests"] = None
    repo["features"]["gap_docs"] = None
    scored = score_repo(repo, clock=frozen_clock)
    assert scored.breakdown.contribution_opp.value is None
    assert scored.breakdown.opportunity.confidence == "low"
    assert select_top([scored]) == []


def test_organic_spike_no_h_flag_high_explosion(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("organic_spike.json"), clock=frozen_clock)
    bd = scored.breakdown
    assert bd.vetoed is False
    assert not any(flag.startswith("H") for flag in bd.flags)
    assert bd.explosion.value is not None
    assert bd.explosion.value >= 35


def test_commit_count_is_not_a_kpi(frozen_clock, repo_fixture):
    base = repo_fixture("memkit.json")
    doubled = deepcopy(base)
    base["commit_count"] = 40
    doubled["commit_count"] = 80
    a = score_repo(base, clock=frozen_clock)
    b = score_repo(doubled, clock=frozen_clock)
    assert a.breakdown.opportunity.value == b.breakdown.opportunity.value
    assert a.breakdown.contribution.value == b.breakdown.contribution.value


def test_zero_contributors_low_contribution(frozen_clock, repo_fixture):
    repo = repo_fixture("memkit.json")
    repo["C"] = 0
    repo["U_commit_30d"] = 0
    repo["features"] = {
        **repo["features"],
        "help_n": 0,
        "repeat_clusters": 0,
        "gap_ci": 0,
        "gap_tests": 0,
        "gap_docs": 0,
        "bots_dropped": ["dependabot[bot]"],
    }
    scored = score_repo(repo, clock=frozen_clock)
    assert scored.breakdown.contribution.value is not None
    assert scored.breakdown.contribution.value <= 40


def test_12a_opportunity_confidence_high(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    assert scored.breakdown.opportunity.confidence == "high"
