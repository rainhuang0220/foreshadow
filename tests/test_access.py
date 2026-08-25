from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import compute_access
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2
from test_score_v2 import _phase_b, small_active


def test_access_unknown_is_not_zero():
    acc = compute_access(FeaturesBlob())
    assert acc.score is None
    assert acc.classification is None
    assert acc.confidence == "low"


def test_access_empty_pr_sample_is_not_zero_merge_rate():
    acc = compute_access(
        FeaturesBlob(pr_merged_sample_n=0, pr_accept_rate=None, maint_touch=0.8)
    )
    assert acc.merge_rate is None
    assert acc.score is not None
    assert acc.score > 0


def test_high_external_merge_is_high_access():
    acc = compute_access(
        FeaturesBlob(
            pr_merged_sample_n=12,
            pr_external_merged_n=7,
            pr_accept_rate=7 / 12,
            pr_reviewed_n=10,
            pr_review_rate=10 / 12,
            maint_touch=0.8,
            maint_first_response_hours=6,
            gap_docs=0,
            unassigned_help=2,
            help_n=3,
            has_workflows=True,
        )
    )
    assert acc.score is not None
    assert acc.score >= 70
    assert acc.classification in {"HIGH", "VERY_HIGH"}
    assert acc.merge_rate == 7 / 12


def test_silent_maintainer_lowers_access():
    open_ = compute_access(
        FeaturesBlob(
            pr_accept_rate=0.6,
            pr_review_rate=0.7,
            maint_touch=0.9,
            maint_first_response_hours=4,
            gap_docs=0,
        )
    )
    silent = compute_access(
        FeaturesBlob(
            pr_accept_rate=0.05,
            pr_review_rate=0.1,
            maint_touch=0.0,
            maint_first_response_hours=200,
            gap_docs=1,
        )
    )
    assert open_.score is not None and silent.score is not None
    assert silent.score < open_.score
    assert silent.classification in {"VERY_LOW", "LOW", "MEDIUM"}


def test_access_is_not_contributor_gap(frozen_clock):
    repo = small_active()
    repo["features"] = _phase_b(
        pr_accept_rate=0.5,
        pr_review_rate=0.6,
        pr_merged_sample_n=8,
        pr_external_merged_n=4,
        maint_first_response_hours=8,
    )
    v1 = score_repo(repo, clock=frozen_clock)
    v2 = score_repo_v2(repo, clock=frozen_clock)
    assert "access" not in v1.evidence
    acc = v2.evidence["access"]
    assert acc["score"] is not None
    assert "gap is separate" in acc["why"]
    assert v2.breakdown.gap.value is not None


def test_v1_unchanged_by_access(frozen_clock):
    v1 = score_repo(small_active(), clock=frozen_clock)
    assert "access" not in v1.evidence
