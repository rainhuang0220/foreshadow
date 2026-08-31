from copy import deepcopy

from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.select import select_top


def _memkit_day31(repo_fixture, **overrides) -> dict:
    repo = deepcopy(repo_fixture("memkit.json"))
    features = overrides.pop("features", None)
    repo.update(overrides)
    if features:
        repo["features"] = {**repo["features"], **features}
    return repo


def test_weak_fit_override_day31(frozen_clock, repo_fixture):
    repo = _memkit_day31(
        repo_fixture,
        direction_fit=40,
        features={
            "help_n": 5,
            "repeat_clusters": 3,
            "gap_ci": 1,
            "gap_tests": 1,
            "gap_docs": 1,
            "maint_touch": 1.0,
        },
    )
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.momentum.value is not None
    assert bd.direction_fit.value == 40
    five = _five(bd)
    assert five >= 85
    assert _five_min(bd) >= 75
    assert bd.exceptional == "exceptional_override_weak_fit"
    top = select_top([scored])
    assert [r.full_name for r in top] == ["acme/memkit"]


def test_direction_30_crypto_not_eligible(frozen_clock, repo_fixture):
    repo = _memkit_day31(
        repo_fixture,
        direction_fit=30,
        C=1,
        description="free crypto airdrop",
        features={
            "readme_install": False,
            "readme_excerpt": "free crypto tokens\n",
        },
    )
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.direction_fit.value == 30
    assert "H7" in (bd.veto_reason or "")
    assert bd.exceptional is None or bd.vetoed
    assert select_top([scored]) == []


def test_off_direction_but_strong_day31(frozen_clock, repo_fixture):
    repo = _memkit_day31(repo_fixture, direction_fit=60)
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.direction_fit.value == 60
    assert bd.opportunity.value is not None
    assert bd.opportunity.value >= 75
    assert bd.exceptional == "off_direction_but_strong"
    top = select_top([scored])
    assert [r.full_name for r in top] == ["acme/memkit"]


def _five(bd) -> float:
    vals = [
        c.value
        for c in (
            bd.momentum,
            bd.real_user,
            bd.gap,
            bd.contribution_opp,
            bd.early_entry,
        )
        if c.value is not None
    ]
    return sum(vals) / len(vals)


def _five_min(bd) -> float:
    vals = [
        c.value
        for c in (
            bd.momentum,
            bd.real_user,
            bd.gap,
            bd.contribution_opp,
            bd.early_entry,
        )
        if c.value is not None
    ]
    return min(vals)
