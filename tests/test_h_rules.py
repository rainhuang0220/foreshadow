from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.h_rules import apply_penalties, evaluate_h, h7_fold


class R:
    def __init__(self, **kw):
        self.__dict__.update(
            {
                "archived": False,
                "disabled": False,
                "is_empty": False,
                "is_fork": False,
                "S": 0,
                "C": 1,
                "C_censored": False,
                "age_days": 12,
                "has_issues": True,
                "I_open": 0,
                "I_closed": 0,
                "fork_star": 0.0014,
                "U_commit_30d": 1,
                "license_spdx": None,
                "pushed_age_days": 10,
                "readme_install": 0,
                "name": "chatgpt-wrapper-pro",
                "full_name": "quick/chatgpt-wrapper-pro",
                "description": "",
                "topics": [],
                "readme_excerpt": "Best ChatGPT wrapper GPT-4 AI Agent 🔥",
                "root_names": ["README.md", "app.py"],
            }
            | kw
        )


def _cs(value=80.0, confidence="high"):
    return ComponentScore(value=value, confidence=confidence)


def _scores(**kw):
    fields = {
        "opportunity": _cs(),
        "explosion": _cs(),
        "contribution": _cs(),
        "momentum": _cs(),
        "real_user": _cs(),
        "gap": _cs(),
        "contribution_opp": _cs(),
        "early_entry": _cs(),
        "direction_fit": _cs(),
        "maintainer": _cs(),
    }
    fields.update(kw)
    return ScoreBreakdown(**fields)


def test_h7_fold_needles_and_haystack():
    assert h7_fold("GPT-4 wrapper") == "gpt 4 wrapper"
    assert h7_fold("gpt-4 wrapper") == "gpt 4 wrapper"
    assert h7_fold("gpt-4 wrapper") in h7_fold("Best GPT-4 wrapper")


def test_12c_fires_h5_h6_h7():
    r = evaluate_h(
        R(
            S=8400,
            C=1,
            age_days=12,
            fork_star=0.0014,
            U_commit_30d=1,
            I_open=0,
            has_issues=True,
        )
    )
    assert r.veto_reason == "H5,H6,H7"


def test_name_only_chatgpt_wrapper_fires_h7():
    r = evaluate_h(
        R(
            S=100,
            C=1,
            age_days=20,
            readme_excerpt="",
            I_open=5,
            fork_star=0.1,
            U_commit_30d=1,
        )
    )
    assert "H7" in r.fired


def test_gpt4_wrapper_readme_fires_h7():
    r = evaluate_h(
        R(
            name="x",
            full_name="a/x",
            S=100,
            C=1,
            age_days=20,
            readme_excerpt="GPT-4 wrapper",
            readme_install=0,
            I_open=5,
            fork_star=0.1,
        )
    )
    assert "H7" in r.fired


def test_gemfile_not_h3():
    r = evaluate_h(
        R(
            S=10,
            C=3,
            age_days=40,
            root_names=["README.md", "Gemfile"],
            readme_excerpt="ok",
            I_open=1,
            fork_star=0.1,
            U_commit_30d=2,
            license_spdx="MIT",
        )
    )
    assert "H3" not in r.fired


def test_h2_always_fires_on_forks():
    r = evaluate_h(
        R(
            is_fork=True,
            S=80,
            C=8,
            age_days=40,
            license_spdx="MIT",
            I_open=3,
            fork_star=0.1,
            name="lib",
            full_name="a/lib",
            readme_excerpt="ok",
        )
    )
    assert r.fired == ["H2"]
    assert r.vetoed is True
    assert r.veto_reason == "H2"


def test_h1_empty_repo():
    r = evaluate_h(
        R(
            is_empty=True,
            S=0,
            name="empty",
            full_name="a/empty",
            readme_excerpt="",
            root_names=[],
        )
    )
    assert "H1" in r.fired


def test_h8_abandoned():
    r = evaluate_h(
        R(
            S=100,
            C=5,
            age_days=200,
            I_open=8,
            U_commit_30d=0,
            pushed_age_days=200,
            license_spdx="MIT",
            fork_star=0.1,
            name="old",
            full_name="a/old",
            readme_excerpt="was maintained",
            root_names=["README.md", "src"],
        )
    )
    assert "H8" in r.fired


def test_h9_noassertion_unlicensed():
    r = evaluate_h(
        R(
            S=300,
            C=5,
            age_days=30,
            license_spdx="NOASSERTION",
            I_open=2,
            fork_star=0.1,
            U_commit_30d=2,
            name="nolicense",
            full_name="a/nolicense",
            readme_excerpt="ok",
            root_names=["README.md", "src"],
        )
    )
    assert "H9" in r.fired


def test_h9_null_license():
    r = evaluate_h(
        R(
            S=300,
            C=5,
            age_days=30,
            license_spdx=None,
            I_open=2,
            fork_star=0.1,
            U_commit_30d=2,
            name="nolicense",
            full_name="a/nolicense",
            readme_excerpt="ok",
            root_names=["README.md", "src"],
        )
    )
    assert "H9" in r.fired


def test_h4_zero_issues_high_stars():
    r = evaluate_h(
        R(
            S=400,
            C=5,
            age_days=14,
            I_open=0,
            I_closed=0,
            has_issues=True,
            fork_star=0.03,
            license_spdx="MIT",
            name="quiet",
            full_name="a/quiet",
            readme_excerpt="ok",
            root_names=["README.md", "src"],
        )
    )
    assert "H4" in r.fired


def test_h3_readme_only_tree():
    r = evaluate_h(
        R(
            S=10,
            C=5,
            age_days=40,
            license_spdx="MIT",
            I_open=1,
            fork_star=0.1,
            name="docs",
            full_name="a/docs",
            readme_excerpt="hello",
            root_names=["README.md", "LICENSE", ".gitignore"],
        )
    )
    assert "H3" in r.fired


def test_h10_placeholder_readme():
    r = evaluate_h(
        R(
            S=10,
            C=5,
            age_days=40,
            license_spdx="MIT",
            I_open=1,
            fork_star=0.1,
            name="x",
            full_name="a/x",
            readme_excerpt="# project-name\nDescription of the project\n",
            root_names=["README.md", "src"],
        )
    )
    assert "H10" in r.fired


def test_h7_install_verb_blocks():
    r = evaluate_h(
        R(
            S=100,
            C=1,
            age_days=20,
            readme_install=1,
            I_open=5,
            fork_star=0.1,
            U_commit_30d=1,
        )
    )
    assert "H7" not in r.fired


def test_h7_high_c_blocks():
    r = evaluate_h(R(S=100, C=4, age_days=20, I_open=5, fork_star=0.1, U_commit_30d=1))
    assert "H7" not in r.fired


def test_missing_tree_does_not_fire_h3():
    r = evaluate_h(
        R(
            root_names=None,
            S=10,
            C=5,
            age_days=40,
            license_spdx="MIT",
            I_open=1,
            fork_star=0.1,
            name="x",
            full_name="a/x",
            readme_excerpt="ok",
        )
    )
    assert "H3" not in r.fired
    assert r.tree_missing is True


def test_p8_spike_no_committers_penalizes():
    repo = R(
        S=200,
        S_prev=140,
        U_commit_30d=0,
        age_days=40,
        C=5,
        license_spdx="MIT",
        fork_star=0.1,
        I_open=5,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P8" in out.flags
    assert "p8_spike_no_committers" in out.flags
    assert out.explosion.value == 55
    assert out.opportunity.value == 70


def test_p8_requires_yesterday_stars():
    repo = R(
        S=200,
        U_commit_30d=0,
        age_days=40,
        C=5,
        license_spdx="MIT",
        fork_star=0.1,
        I_open=5,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P8" not in out.flags
    assert out.explosion.value == 80


def test_p1_low_fork_star():
    repo = R(
        S=200,
        fork_star=0.02,
        age_days=40,
        C=5,
        license_spdx="MIT",
        I_open=5,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P1" in out.flags
    assert out.explosion.value == 55
    assert out.opportunity.value == 70


def test_p5_flags_without_clipping_gap():
    repo = R(
        S=150,
        C=1,
        age_days=60,
        fork_star=0.1,
        license_spdx="MIT",
        I_open=5,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(gap=_cs(40)), repo)
    assert "P5" in out.flags
    assert out.gap.value == 40


def test_p6_young_repo_caps_explosion():
    repo = R(
        S=80,
        C=5,
        age_days=6,
        fork_star=0.1,
        license_spdx="MIT",
        I_open=2,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P6" in out.flags
    assert out.explosion.value == 40
    assert out.momentum.confidence == "low"


def test_p7_stuffing_penalty():
    repo = R(
        S=80,
        C=5,
        age_days=40,
        fork_star=0.1,
        license_spdx="MIT",
        I_open=2,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        description="awesome best ultimate AI LLM agent",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P7" in out.flags
    assert out.direction_fit.value == 60
    assert out.opportunity.value == 70


def test_p2_mirror_fork_star():
    repo = R(
        S=200,
        C=5,
        age_days=40,
        fork_star=0.9,
        license_spdx="MIT",
        I_open=2,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
    )
    out = apply_penalties(_scores(), repo)
    assert "P2" in out.flags
    assert out.opportunity.value == 65
    assert out.explosion.value == 80


def test_p3_no_workflows_gap_tests():
    repo = R(
        S=80,
        C=5,
        age_days=40,
        fork_star=0.1,
        license_spdx="MIT",
        I_open=2,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
        has_workflows=False,
        gap_tests=1,
    )
    out = apply_penalties(_scores(), repo)
    assert "P3" in out.flags
    assert out.contribution.value == 70
    assert out.maintainer.value == 75


def test_p4_screenshot_only():
    repo = R(
        S=80,
        C=5,
        age_days=40,
        fork_star=0.1,
        license_spdx="MIT",
        I_open=2,
        name="x",
        full_name="a/x",
        readme_excerpt="ok",
        root_names=["README.md", "src"],
        screenshot_only=True,
    )
    out = apply_penalties(_scores(), repo)
    assert "P4" in out.flags
    assert out.real_user.value == 65
