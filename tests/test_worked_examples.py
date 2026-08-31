import pytest

from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.select import select_top


def test_12a_memkit_keep(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    bd = scored.breakdown
    assert bd.momentum.value == pytest.approx(95.2, abs=0.5)
    assert bd.real_user.value == pytest.approx(97.5, abs=0.5)
    assert bd.gap.value == pytest.approx(88.9, abs=0.5)
    assert bd.contribution_opp.value == pytest.approx(61.9, abs=0.5)
    assert bd.contribution.value == pytest.approx(61.9, abs=0.5)
    assert bd.early_entry.value == pytest.approx(84.0, abs=0.5)
    assert bd.direction_fit.value == 92
    assert bd.maintainer.value == pytest.approx(77.55, abs=0.05)
    assert bd.opportunity.value == pytest.approx(85.05, abs=0.5)
    assert bd.explosion.value == pytest.approx(93.6, abs=0.5)
    assert bd.vetoed is False
    top = select_top([scored])
    assert [r.full_name for r in top] == ["acme/memkit"]
    assert top[0].breakdown.selected_rank == 1


def test_12b_giant_drop(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("giant.json"), clock=frozen_clock)
    bd = scored.breakdown
    assert bd.gap.value == 10
    assert bd.early_entry.value == pytest.approx(8)
    assert bd.direction_fit.value == 55
    assert bd.momentum.value is not None
    assert bd.momentum.value < 1
    assert bd.explosion.value is not None
    assert bd.explosion.value < 35
    assert bd.opportunity.value is not None
    assert bd.opportunity.value < 55
    assert select_top([scored]) == []
    assert bd.selected_rank is None


def test_12c_wrapper_hard_reject(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("wrapper.json"), clock=frozen_clock)
    bd = scored.breakdown
    assert bd.veto_reason == "H5,H6,H7"
    assert bd.vetoed is True
    assert bd.explosion.value is None
    assert "H3" not in bd.flags
    assert select_top([scored]) == []
    assert bd.selected_rank is None


def test_12a_keep_among_b_and_c(frozen_clock, repo_fixture):
    a = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    b = score_repo(repo_fixture("giant.json"), clock=frozen_clock)
    c = score_repo(repo_fixture("wrapper.json"), clock=frozen_clock)
    top = select_top([a, b, c])
    assert [r.full_name for r in top] == ["acme/memkit"]
    assert top[0].breakdown.selected_rank == 1
    assert b.breakdown.selected_rank is None
    assert c.breakdown.selected_rank is None
