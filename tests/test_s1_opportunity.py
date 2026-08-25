from copy import deepcopy

from foreshadow.pipeline.compare import assign_pool_ranks_v2, identity_key
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2
from test_score_v2 import _phase_b, large_mature, small_active, small_stagnant


def _toy_one_push() -> dict:
    return {
        "owner": "new",
        "name": "spark",
        "full_name": "new/spark",
        "node_id": "R_toy",
        "description": "memory rag llm",
        "license_spdx": "MIT",
        "age_days": 2,
        "pushed_age_days": 0,
        "S": 2,
        "F": 0,
        "C": 1,
        "snapshots": [{"date": "2026-08-24", "stars": 2, "forks": 0}],
        "features": {
            "phase": "M",
            "commits_7d": 1,
            "commits_30d": 1,
            "releases_30d": 0,
            "recent_contributors_7d": 1,
        },
    }


def _low_star_validated() -> dict:
    repo = small_active()
    repo["full_name"] = "seed/validated"
    repo["node_id"] = "R_validated_tiny"
    repo["S"] = 3
    repo["age_days"] = 14
    repo["C"] = 4
    repo["U_issue"] = 5
    repo["features"] = _phase_b(
        commits_7d=20,
        commits_30d=42,
        releases_30d=2,
        recent_contributors_7d=4,
        u_issue=5,
        issue_sample_n=8,
        maint_touch=0.8,
        pr_accept_rate=0.5,
        unassigned_help=2,
    )
    repo["snapshots"] = [{"date": "2026-08-24", "stars": 3, "forks": 2}]
    return repo


def _mid_breakout() -> dict:
    repo = small_active()
    repo["full_name"] = "lab/breakout"
    repo["node_id"] = "R_breakout_300"
    repo["S"] = 300
    repo["age_days"] = 60
    repo["C"] = 8
    repo["U_issue"] = 12
    repo["features"] = _phase_b(
        commits_7d=40,
        commits_30d=90,
        releases_30d=3,
        recent_contributors_7d=6,
        u_issue=12,
        issue_sample_n=20,
        maint_touch=0.7,
        pr_accept_rate=0.4,
        unassigned_help=3,
    )
    repo["snapshots"] = [{"date": "2026-08-24", "stars": 300, "forks": 20}]
    return repo


def _high_star_breakout() -> dict:
    repo = small_active()
    repo["full_name"] = "eco/wave"
    repo["node_id"] = "R_breakout_5k"
    repo["S"] = 5000
    repo["age_days"] = 120
    repo["C"] = 12
    repo["U_issue"] = 15
    repo["features"] = _phase_b(
        commits_7d=50,
        commits_30d=120,
        releases_30d=3,
        recent_contributors_7d=7,
        u_issue=15,
        issue_sample_n=25,
        maint_touch=0.6,
        pr_accept_rate=0.45,
        unassigned_help=2,
    )
    repo["snapshots"] = [{"date": "2026-08-24", "stars": 5000, "forks": 80}]
    return repo


def test_low_star_low_evidence_does_not_win(frozen_clock):
    toy = score_repo_v2(_toy_one_push(), clock=frozen_clock)
    good = score_repo_v2(small_active(), clock=frozen_clock)
    assert toy.evidence["s1"]["pool"] == "experimental"
    assert toy.evidence["s1"]["stage"] == "EXPERIMENTAL"
    assert toy.evidence["s1"]["evidence"] < 20
    assert good.breakdown.opportunity.value > toy.breakdown.opportunity.value


def test_low_star_high_evidence_can_remain(frozen_clock):
    tiny = score_repo_v2(_low_star_validated(), clock=frozen_clock)
    s1 = tiny.evidence["s1"]
    assert s1["pool"] == "main"
    assert s1["evidence"] >= 24
    assert s1["stage"] in {"VALIDATED_EARLY", "BREAKOUT", "EMERGING"}
    assert tiny.breakdown.opportunity.value is not None


def test_mid_star_breakout_can_beat_large_mature(frozen_clock):
    mid = score_repo_v2(_mid_breakout(), clock=frozen_clock)
    giant = score_repo_v2(large_mature(), clock=frozen_clock)
    assert mid.evidence["s1"]["opportunity_window"] > giant.evidence["s1"]["opportunity_window"]
    assert mid.breakdown.opportunity.value > giant.breakdown.opportunity.value
    assert giant.evidence["s1"]["stage"] in {"MATURE", "ESTABLISHED", "STAGNANT"}


def test_high_star_breakout_can_remain_high_opportunity(frozen_clock):
    wave = score_repo_v2(_high_star_breakout(), clock=frozen_clock)
    s1 = wave.evidence["s1"]
    assert s1["pool"] == "main"
    assert s1["earlyness"] >= 50
    assert s1["stage"] in {"BREAKOUT", "VALIDATED_EARLY", "EMERGING"}
    assert wave.breakdown.vetoed is False
    assert s1["opportunity_window"] >= 50


def test_high_star_mature_gets_lower_entry_window(frozen_clock):
    giant = score_repo_v2(large_mature(), clock=frozen_clock)
    wave = score_repo_v2(_high_star_breakout(), clock=frozen_clock)
    assert giant.evidence["s1"]["earlyness"] < wave.evidence["s1"]["earlyness"]
    assert giant.evidence["s1"]["opportunity_window"] < wave.evidence["s1"]["opportunity_window"]


def test_old_low_activity_repo_is_not_early_opportunity(frozen_clock):
    stale = score_repo_v2(small_stagnant(), clock=frozen_clock)
    s1 = stale.evidence["s1"]
    assert s1["stage"] == "STAGNANT"
    assert (s1["earlyness"] or 0) < 55
    assert (s1["opportunity_window"] or 0) <= 22


def test_young_repo_with_real_users_is_validated_early(frozen_clock):
    tiny = score_repo_v2(_low_star_validated(), clock=frozen_clock)
    assert tiny.evidence["s1"]["stage"] in {"VALIDATED_EARLY", "BREAKOUT", "EMERGING"}
    assert tiny.evidence["s1"]["quadrant"] in {"gold", "too_early"}


def test_experimental_is_separate_from_main_opportunity_pool(frozen_clock):
    toy = score_repo_v2(_toy_one_push(), clock=frozen_clock)
    good = score_repo_v2(small_active(), clock=frozen_clock)
    items = [
        (toy, {"node_id": "R_toy", "S": 2}),
        (good, {"node_id": "R_small_active", "S": 73}),
    ]
    ranks = assign_pool_ranks_v2(items)
    assert ranks[identity_key(good, items[1][1])] == 1
    assert ranks[identity_key(toy, items[0][1])] == 2
    assert toy.evidence["s1"]["pool"] == "experimental"
    assert good.evidence["s1"]["pool"] == "main"


def test_star_is_not_hard_veto(frozen_clock):
    wave = score_repo_v2(_high_star_breakout(), clock=frozen_clock)
    v1 = score_repo(_high_star_breakout(), clock=frozen_clock)
    assert wave.breakdown.vetoed is False
    assert v1.breakdown.vetoed is False
    assert wave.evidence["s1"]["pool"] == "main"


def test_star_is_not_direct_opportunity_bonus(frozen_clock):
    a = _low_star_validated()
    b = deepcopy(a)
    b["full_name"] = "seed/same-but-50"
    b["node_id"] = "R_same_50"
    b["S"] = 50
    b["snapshots"] = [{"date": "2026-08-24", "stars": 50, "forks": 2}]
    sa = score_repo_v2(a, clock=frozen_clock)
    sb = score_repo_v2(b, clock=frozen_clock)
    # Stars must not be the ranking magnet.
    assert abs(sa.evidence["s1"]["earlyness"] - sb.evidence["s1"]["earlyness"]) < 8
    assert abs(sa.breakdown.opportunity.value - sb.breakdown.opportunity.value) < 8
    assert sa.evidence["s1"]["pool"] == sb.evidence["s1"]["pool"] == "main"


def test_v1_opportunity_unchanged_by_s1(frozen_clock):
    repo = small_active()
    v1 = score_repo(repo, clock=frozen_clock)
    assert "s1" not in v1.evidence
    v2 = score_repo_v2(repo, clock=frozen_clock)
    assert v2.evidence["score_version"] == "v2"
    assert "s1" in v2.evidence
