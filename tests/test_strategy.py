from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.s1 import compute_s1
from foreshadow.pipeline.strategy import recommend_entry
from test_s1_opportunity import _toy_one_push


def test_not_all_projects_recommend_pr():
    toy = recommend_entry(FeaturesBlob())
    assert toy.path == "ISSUE" or toy.path == "DISCUSSION"
    assert toy.allows_direct_pr is False
    bugs = recommend_entry(FeaturesBlob(bug_n=4, issue_sample_n=8, maint_touch=0.5))
    assert bugs.path == "REPRODUCTION"
    assert bugs.allows_direct_pr is False
    docs = recommend_entry(FeaturesBlob(gap_docs=1, issue_sample_n=2))
    assert docs.path == "DOCUMENTATION"


def test_experimental_uses_discussion():
    from datetime import UTC, datetime

    from foreshadow.clock import Clock
    from foreshadow.pipeline.activity import compute_activity
    from foreshadow.pipeline.score_v2 import score_repo_v2

    scored = score_repo_v2(_toy_one_push(), clock=Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC)))
    feat = FeaturesBlob.model_validate(_toy_one_push()["features"])
    s1 = compute_s1(
        age_days=2,
        contributors=1,
        stars=2,
        pushed_age_days=0,
        unique_issue_authors=None,
        feat=feat,
        activity=compute_activity(feat),
    )
    strat = recommend_entry(feat, s1=s1)
    assert strat.path == "DISCUSSION"
    assert scored.evidence["strategy"]["allows_direct_pr"] is False


def test_help_wanted_is_issue_not_pr_magnet():
    strat = recommend_entry(
        FeaturesBlob(help_n=2, unassigned_help=2, bug_n=0, gap_docs=0, gap_tests=0)
    )
    assert strat.path == "ISSUE"
    assert "onboarding" in " ".join(strat.why).lower() or "Issue" in strat.summary_zh


def test_reproduction_still_cites_a_concrete_issue():
    strat = recommend_entry(
        FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
        )
    )
    assert strat.path == "REPRODUCTION"
    assert "#73" in " ".join(strat.why)


def test_hard_language_does_not_recommend_core_rewrite():
    strat = recommend_entry(
        FeaturesBlob(
            bug_n=4,
            issue_sample_n=8,
            maint_touch=0.5,
            pr_accept_rate=0.5,
            pr_merged_sample_n=8,
        ),
        language="Rust",
        skills=("Python", "docs"),
    )
    assert strat.path in {"ISSUE", "DISCUSSION", "DOCUMENTATION", "RESEARCH"}
    assert strat.allows_direct_pr is False
    blob = " ".join(strat.steps_zh + strat.why + [strat.summary_zh])
    assert "重写整个" not in blob
    assert "inference engine" not in blob.lower()


def test_long_term_unknown_is_not_zero():
    strat = recommend_entry(FeaturesBlob())
    assert strat.long_term.get("score") is None or strat.long_term.get("missing")
    if strat.long_term.get("score") is None:
        assert "not 0" in strat.long_term.get("why", "").lower()
