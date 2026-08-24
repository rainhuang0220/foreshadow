from copy import deepcopy

from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.select import select_top


def test_day1_only_today_not_selected(frozen_clock, repo_fixture):
    repo = deepcopy(repo_fixture("memkit.json"))
    repo["snapshots"] = [s for s in repo["snapshots"] if s["date"] == "2026-08-24"]
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.momentum.value is None
    assert bd.explosion.value is None
    proxy = scored.evidence.get("explosion_lifetime_proxy")
    assert proxy is not None
    assert proxy > 35
    top = select_top([scored])
    assert top == []
    assert bd.selected_rank is None


def test_day8_with_t7_keep(frozen_clock, repo_fixture):
    repo = deepcopy(repo_fixture("memkit.json"))
    repo["snapshots"] = [
        s for s in repo["snapshots"] if s["date"] in {"2026-08-24", "2026-08-17"}
    ]
    scored = score_repo(repo, clock=frozen_clock)
    bd = scored.breakdown
    assert bd.momentum.value is not None
    assert bd.momentum.confidence in {"medium", "high"}
    assert bd.explosion.value is not None
    top = select_top([scored])
    assert [r.full_name for r in top] == ["acme/memkit"]
    assert top[0].breakdown.selected_rank == 1


def test_day31_full_windows_keep(frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    top = select_top([scored])
    assert top[0].breakdown.selected_rank == 1
    assert scored.breakdown.explosion.value is not None
    assert scored.evidence.get("explosion_lifetime_proxy") is None
