import inspect

from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.score import ScoredRepo
from foreshadow.pipeline.select import is_official_eligible, select_top


def passing(owner: str, name: str, opp: float) -> ScoredRepo:
    hi = ComponentScore(value=80, confidence="high")
    breakdown = ScoreBreakdown(
        opportunity=ComponentScore(value=opp, confidence="high"),
        explosion=ComponentScore(value=80, confidence="high"),
        contribution=hi,
        momentum=ComponentScore(value=90, confidence="high"),
        real_user=hi,
        gap=hi,
        contribution_opp=hi,
        early_entry=hi,
        direction_fit=hi,
        maintainer=hi,
    )
    return ScoredRepo(owner=owner, full_name=f"{owner}/{name}", breakdown=breakdown)


def test_diversity_skip_and_continue():
    rows = [
        passing("a", "r1", 90),
        passing("a", "r2", 89),
        passing("a", "r3", 88),
        passing("b", "x", 87),
        passing("c", "y", 86),
        passing("d", "z", 85),
    ]
    top = select_top(rows, min_opportunity=55, min_explosion=35, max_per_owner=2)
    names = [r.full_name for r in top]
    assert names == ["a/r1", "a/r2", "b/x", "c/y", "d/z"]
    assert [r.breakdown.selected_rank for r in top] == [1, 2, 3, 4, 5]


def test_no_pad():
    top = select_top([passing("a", "r1", 90), passing("b", "r2", 80)])
    assert len(top) == 2
    assert [r.breakdown.selected_rank for r in top] == [1, 2]


def test_v7_required():
    row = passing("a", "r1", 90)
    row.breakdown.momentum = ComponentScore(value=None, confidence="low")
    row.breakdown.explosion = ComponentScore(value=None, confidence="low")
    assert select_top([row]) == []


def test_momentum_low_confidence_is_not_v7():
    row = passing("a", "r1", 90)
    row.breakdown.momentum = ComponentScore(value=90, confidence="low")
    assert select_top([row]) == []


def test_lifetime_proxy_does_not_satisfy_explosion_gate():
    row = passing("a", "r1", 90)
    row.breakdown.explosion = ComponentScore(
        value=None, confidence="low", missing=["v7"]
    )
    row.evidence["explosion_lifetime_proxy"] = 38.0
    assert select_top([row]) == []


def test_opportunity_below_bar_not_padded():
    assert select_top([passing("a", "r1", 54)]) == []


def test_explosion_below_bar():
    row = passing("a", "r1", 90)
    row.breakdown.explosion = ComponentScore(value=34, confidence="high")
    assert select_top([row]) == []


def test_vetoed_fork_not_selected():
    row = passing("a", "r1", 90)
    row.breakdown.vetoed = True
    row.breakdown.veto_reason = "H2"
    row.breakdown.flags = ["H2"]
    row.breakdown.explosion = ComponentScore(value=None, confidence="low")
    assert select_top([row]) == []


def test_tree_missing_excluded():
    row = passing("a", "r1", 90)
    row.breakdown.flags = ["tree_missing"]
    row.breakdown.opportunity = ComponentScore(value=90, confidence="low")
    assert select_top([row]) == []


def test_direction_fit_below_gate_without_exceptional():
    row = passing("a", "r1", 90)
    row.breakdown.direction_fit = ComponentScore(value=55, confidence="high")
    row.breakdown.exceptional = None
    assert select_top([row]) == []


def test_exceptional_override_weak_fit_may_select():
    row = passing("a", "r1", 80)
    row.breakdown.direction_fit = ComponentScore(value=40, confidence="high")
    row.breakdown.exceptional = "exceptional_override_weak_fit"
    top = select_top([row])
    assert [r.full_name for r in top] == ["a/r1"]
    assert top[0].breakdown.selected_rank == 1


def test_official_select_thresholds_frozen_at_55_35():
    for fn in (select_top, is_official_eligible):
        params = inspect.signature(fn).parameters
        assert params["min_opportunity"].default == 55
        assert params["min_explosion"].default == 35
