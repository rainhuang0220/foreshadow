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
    docs = recommend_entry(
        FeaturesBlob(
            gap_docs=1,
            issue_sample_n=2,
            pr_accept_rate=0.5,
            pr_review_rate=0.5,
            maint_touch=0.5,
            pr_merged_sample_n=4,
        )
    )
    assert docs.path == "DOCUMENTATION"
    closed_docs = recommend_entry(FeaturesBlob(gap_docs=1, issue_sample_n=2))
    assert closed_docs.path == "ISSUE"
    assert closed_docs.allows_direct_pr is False
    assert "CONTRIBUTING.md" in " ".join(closed_docs.why)


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


def test_report_copy_does_not_say_add_contributing():
    from foreshadow.pipeline.report import _help_bullets

    bullets = _help_bullets({"gap_docs": 1, "help_n": 0, "bug_n": 0})
    blob = " ".join(bullets).lower()
    assert "add contributing.md" not in blob
    assert "add ci workflow" not in blob


def test_unknown_acceptance_is_not_a_docs_pr():
    strat = recommend_entry(FeaturesBlob(gap_docs=1, gap_tests=1, gap_ci=1))
    assert strat.path not in {"DOCUMENTATION", "TEST", "TOOLING", "FEATURE", "BUG_FIX"}
    assert strat.allows_direct_pr is False
    blob = " ".join(strat.steps_zh + strat.why + [strat.summary_zh])
    assert "open a PR" not in blob.lower()


def test_long_term_unknown_is_not_zero():
    strat = recommend_entry(FeaturesBlob())
    assert strat.long_term.get("score") is None or strat.long_term.get("missing")
    if strat.long_term.get("score") is None:
        assert "not 0" in strat.long_term.get("why", "").lower()


def test_screenshot_with_source_is_benchmark_not_pr():
    strat = recommend_entry(
        FeaturesBlob(screenshot_only=True, tree_kind="has_source"),
        full_name="acme/demo",
    )
    assert strat.path == "BENCHMARK"
    assert strat.allows_direct_pr is False
    blob = " ".join(strat.steps_zh + strat.why + [strat.summary_zh]).lower()
    assert "open a pr" not in blob
    assert "create_pr" not in blob
    assert "第一步" in strat.steps_zh[0]
    assert "测量" in " ".join(strat.steps_zh) or "数字" in " ".join(strat.steps_zh)


def test_blurb_lands_in_first_step():
    strat = recommend_entry(
        FeaturesBlob(),
        full_name="acme/toy",
        blurb="tiny memory layer for agents",
    )
    assert "acme/toy" in strat.steps_zh[0]
    assert "tiny memory layer" in strat.steps_zh[0]
    assert strat.allows_direct_pr is False


def test_screenshot_without_source_stays_research():
    strat = recommend_entry(FeaturesBlob(screenshot_only=True, tree_kind="readme_only"))
    assert strat.path == "RESEARCH"
    assert strat.allows_direct_pr is False


def test_screenshot_plus_source_beats_docs_gap():
    strat = recommend_entry(
        FeaturesBlob(
            screenshot_only=True,
            tree_kind="has_source",
            tree_names=["README.md", "src", "main.py"],
            gap_docs=1,
            gap_tests=1,
            gap_ci=1,
            open_issue_titles=["#19 measure decode latency"],
        ),
        language="Python",
        full_name="acme/demo",
    )
    assert strat.path == "BENCHMARK"
    assert strat.allows_direct_pr is False
    blob = " ".join(strat.why + strat.steps_zh + [strat.summary_zh])
    assert "#19" in blob
    assert "Python" in blob
    assert "open a pr" not in blob.lower()


def test_wrapper_app_py_counts_as_source_for_benchmark():
    strat = recommend_entry(
        FeaturesBlob(
            screenshot_only=True,
            tree_kind="readme_plus_app",
            tree_names=["README.md", "app.py"],
            gap_docs=1,
        ),
        language="Python",
    )
    assert strat.path == "BENCHMARK"
    assert strat.allows_direct_pr is False


def test_cloned_steps_cite_real_file_and_issue_command():
    from foreshadow.pipeline.strategy import customize_steps

    steps = customize_steps(
        "REPRODUCTION",
        full_name="acme/toy",
        inspect={
            "related_files": ["src/retriever.py"],
            "test_files": ["tests/test_retriever.py"],
            "issue_commands": ["pytest tests/test_retriever.py"],
        },
        cited={"number": 123, "title": "empty retriever", "body": "pytest tests/test_retriever.py"},
        cloned=True,
    )
    blob = " ".join(steps)
    assert steps[0] == (
        "第一步：运行 `pytest tests/test_retriever.py`，核对 Issue #123 描述的行为。"
        "缺依赖就停，不要擅自安装。"
    )
    assert "FORESHADOW.md" not in steps[0]
    assert "ISSUE_DRAFT.md" not in steps[0]
    assert "src/retriever.py" in blob
    assert "#123" in blob
    assert "pytest tests/test_retriever.py" in blob
    assert "src/memory/missing.py" not in blob
    assert "open a pr" not in blob.lower()
    assert "后台记录在 FORESHADOW.md" in blob
    assert not blob.startswith("第一步：打开")


def test_cloned_first_step_uses_existing_test_collect_only():
    from foreshadow.pipeline.strategy import customize_steps

    steps = customize_steps(
        "ISSUE",
        full_name="acme/toy",
        inspect={
            "test_files": ["tests/test_retriever.py"],
            "related_files": ["src/retriever.py"],
        },
        cloned=True,
    )
    assert steps[0] == "第一步：对仓库已有 `tests/test_retriever.py` 做安全检查（只列路径，不执行 pytest）。"
    assert "FORESHADOW.md" not in steps[0]
    assert "ISSUE_DRAFT.md" not in steps[0]
    blob = " ".join(steps)
    assert "src/retriever.py" in blob
    assert "src/memory/missing.py" not in blob
    assert "后台记录在 FORESHADOW.md" in blob


def test_cloned_first_step_uses_related_file_as_evidence():
    from foreshadow.pipeline.strategy import customize_steps

    steps = customize_steps(
        "ISSUE",
        full_name="acme/toy",
        inspect={"related_files": ["src/retriever.py"]},
        cloned=True,
    )
    assert steps[0] == "第一步：对照 Issue，验证 `src/retriever.py` 中的行为（路径仅作证据）。"
    assert "FORESHADOW.md" not in steps[0]
    blob = " ".join(steps)
    assert "src/memory/missing.py" not in blob
    assert "后台记录在 FORESHADOW.md" in blob


def test_cloned_steps_mark_unknown_when_no_files():
    from foreshadow.pipeline.strategy import customize_steps

    steps = customize_steps("ISSUE", full_name="acme/toy", inspect={}, cloned=True)
    assert "UNKNOWN" in steps[0]
    assert "不要编造" in steps[0]
    assert "FORESHADOW.md" not in steps[0]
    assert "ISSUE_DRAFT.md" not in steps[0]
    blob = " ".join(steps)
    assert "src/memory/retriever.py" not in blob
    assert "后台记录在 FORESHADOW.md" in blob


def test_cloned_first_step_is_work_not_notes():
    from foreshadow.pipeline.strategy import customize_steps

    steps = customize_steps(
        "ISSUE",
        full_name="acme/toy",
        inspect={
            "clone_ok": True,
            "readme_headings": ["Install"],
            "tests": {"kind": "node", "status": "skipped"},
        },
        cloned=True,
    )
    assert "UNKNOWN" in steps[0]
    assert "FORESHADOW.md" not in steps[0]
    assert "ISSUE_DRAFT.md" not in steps[0]
    assert "克隆仓库" not in " ".join(steps)
    first = steps[0].lower()
    assert "push" not in first
    assert "create_pr" not in first
    assert any("npm" in s and "跳过" in s for s in steps)
    assert any("后台记录在 FORESHADOW.md" in s for s in steps[1:])


def test_default_issue_cites_number_and_language():
    strat = recommend_entry(
        FeaturesBlob(open_issue_titles=["#88 latency on first token"]),
        language="Go",
        full_name="acme/svc",
    )
    assert strat.path == "ISSUE"
    blob = " ".join(strat.why + strat.steps_zh)
    assert "#88" in blob
    assert "Go" in blob
    assert strat.allows_direct_pr is False


def test_steps_cite_issue_heading_and_repo():
    strat = recommend_entry(
        FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
            readme_headings=["Install", "Usage", "Memory API"],
            tree_names=["src", "pyproject.toml", "README.md"],
        ),
        full_name="acme/toy",
    )
    blob = " ".join(strat.steps_zh)
    assert strat.path == "REPRODUCTION"
    assert "#73" in blob
    assert "Install" in blob
    assert "acme/toy" in blob
    assert "第一步" in blob
    assert "ISSUE_DRAFT.md" in blob
    assert "open a pr" not in blob.lower()
    assert "停在这里" in blob
