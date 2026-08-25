from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.activity import compute_activity
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2
from test_score_v2 import _phase_b, small_active


def test_single_recent_push_is_not_high_activity():
    feat = FeaturesBlob(
        commits_7d=1,
        commits_30d=1,
        releases_30d=0,
        recent_contributors_7d=1,
    )
    act = compute_activity(feat)
    assert act.momentum is not None
    assert act.momentum < 20
    assert act.classification == "VERY_LOW"


def test_many_recent_commits_is_high_activity():
    feat = FeaturesBlob(
        commits_7d=10,
        commits_30d=25,
        releases_30d=2,
        recent_contributors_7d=5,
    )
    act = compute_activity(feat)
    assert act.momentum is not None
    assert act.momentum >= 75
    assert act.classification in {"HIGH", "VERY_HIGH"}


def test_recent_contributor_diversity_affects_activity():
    solo = compute_activity(
        FeaturesBlob(
            commits_7d=20,
            commits_30d=20,
            releases_30d=0,
            recent_contributors_7d=1,
        )
    )
    diverse = compute_activity(
        FeaturesBlob(
            commits_7d=20,
            commits_30d=20,
            releases_30d=0,
            recent_contributors_7d=5,
        )
    )
    assert solo.momentum is not None
    assert diverse.momentum is not None
    assert diverse.momentum > solo.momentum
    assert solo.classification in {"MEDIUM", "HIGH"}
    assert diverse.classification in {"HIGH", "VERY_HIGH"}


def test_release_activity_affects_activity():
    none = compute_activity(
        FeaturesBlob(
            commits_7d=8,
            commits_30d=16,
            releases_30d=0,
            recent_contributors_7d=3,
        )
    )
    shipped = compute_activity(
        FeaturesBlob(
            commits_7d=8,
            commits_30d=16,
            releases_30d=2,
            recent_contributors_7d=3,
        )
    )
    assert none.momentum is not None
    assert shipped.momentum is not None
    assert shipped.momentum > none.momentum


def test_activity_is_not_star_growth(frozen_clock):
    repo = small_active()
    repo["features"] = _phase_b(
        commits_7d=20, commits_30d=40, releases_30d=1, recent_contributors_7d=4
    )
    v1 = score_repo(repo, clock=frozen_clock)
    v2 = score_repo_v2(repo, clock=frozen_clock)
    assert v1.breakdown.explosion.value is None
    assert v2.breakdown.explosion.value is None
    assert v1.evidence["windows"]["v7"] is None
    assert v2.evidence["windows"]["v7"] is None
    assert "commits_7d" not in str(v2.evidence["windows"])
    assert v2.evidence["star_growth"] is None
    assert v2.evidence["star_growth_status"] == "UNKNOWN"
    assert "not star growth" in v2.evidence["activity"]["note"].lower()
    assert v1.breakdown.momentum.value is None
    assert v2.breakdown.momentum.value is not None
    assert v2.evidence["activity"]["momentum"] == v2.breakdown.momentum.value


def test_zero_30d_activity_is_safe():
    act = compute_activity(
        FeaturesBlob(
            commits_7d=0,
            commits_30d=0,
            releases_30d=0,
            recent_contributors_7d=0,
        )
    )
    assert act.concentration == 0.0
    assert act.momentum == 0.0
    assert act.classification == "VERY_LOW"


def test_activity_unknown_is_not_zero():
    act = compute_activity(FeaturesBlob())
    assert act.momentum is None
    assert act.classification is None
    assert act.confidence == "low"
    assert "commits_30d" in act.missing
    empty = compute_activity(None)
    assert empty.momentum is None


def test_small_active_repo_keeps_activity_advantage(frozen_clock):
    strong = small_active()
    strong["features"] = _phase_b(
        commits_7d=10, commits_30d=25, releases_30d=2, recent_contributors_7d=5
    )
    weak = small_active()
    weak["full_name"] = "seed/onepush"
    weak["features"] = _phase_b(
        commits_7d=1, commits_30d=1, releases_30d=0, recent_contributors_7d=1
    )
    s = score_repo_v2(strong, clock=frozen_clock)
    w = score_repo_v2(weak, clock=frozen_clock)
    assert s.evidence["activity"]["momentum"] > w.evidence["activity"]["momentum"]
    assert s.breakdown.opportunity.value > w.breakdown.opportunity.value
    assert s.evidence["activity"]["class"] in {"HIGH", "VERY_HIGH"}
    assert w.evidence["activity"]["class"] == "VERY_LOW"


def test_new_one_push_repo_does_not_get_fake_activity_boost(frozen_clock):
    repo = {
        "owner": "new",
        "name": "spark",
        "full_name": "new/spark",
        "description": "memory rag llm",
        "license_spdx": "MIT",
        "age_days": 1,
        "pushed_age_days": 0,
        "S": 1,
        "F": 0,
        "C": 1,
        "snapshots": [{"date": "2026-08-25", "stars": 1, "forks": 0}],
        "features": {
            "phase": "M",
            "commits_7d": 1,
            "commits_30d": 1,
            "releases_30d": 0,
            "recent_contributors_7d": 1,
        },
    }
    v2 = score_repo_v2(repo, clock=frozen_clock)
    act = v2.evidence["activity"]
    assert act["class"] == "VERY_LOW"
    assert act["momentum"] is not None
    assert act["momentum"] < 20
    v1 = score_repo(repo, clock=frozen_clock)
    assert v1.breakdown.momentum.value is None
