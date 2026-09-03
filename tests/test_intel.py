from datetime import UTC, datetime
from pathlib import Path

import pytest

from foreshadow.models import ComponentScore, FeaturesBlob
from foreshadow.pipeline.intel import score_intel
from foreshadow.pipeline.wilson import wilson_lower_bound

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _val(part) -> float | None:
    if part is None:
        return None
    if isinstance(part, ComponentScore):
        return part.value
    if hasattr(part, "value"):
        return part.value
    if isinstance(part, dict) and "value" in part:
        return part["value"]
    return part


def _success_owner() -> dict:
    nodes = [
        {
            "nameWithOwner": f"acme/lib{i}",
            "createdAt": "2024-01-01T00:00:00Z",
            "pushedAt": "2026-08-01T00:00:00Z",
            "isArchived": False,
            "isFork": False,
            "stargazerCount": 0,
            "releases": {"totalCount": 1},
        }
        for i in range(3)
    ]
    return {
        "__typename": "User",
        "login": "acme",
        "repositories": {"totalCount": 3, "nodes": nodes},
    }


def test_na_never_becomes_zero():
    result = score_intel()
    for name in ("potential", "creator_prior", "openness", "entry_fit", "eev"):
        value = _val(getattr(result, name))
        assert value is None
        assert value != 0
    assert result.decision == "数据不足"
    assert result.high_confidence is False


def test_n_ext_3_openness_na_not_94():
    feat = FeaturesBlob(pr_external_closed_n=3, pr_external_merged_closed_n=3)
    result = score_intel(feat=feat)
    assert _val(result.openness) is None
    assert _val(result.openness) != 94
    assert _val(result.openness) != 0


def test_n_ext_10_openness_wilson_below_100():
    feat = FeaturesBlob(pr_external_closed_n=10, pr_external_merged_closed_n=10)
    result = score_intel(feat=feat)
    value = _val(result.openness)
    assert value is not None
    assert value < 100
    lb = wilson_lower_bound(10, 10)
    assert lb is not None
    assert value == round(lb * 100, 4)


def test_eev_na_if_only_potential_known():
    feat = FeaturesBlob(
        commits_30d=30,
        recent_contributors_7d=4,
        releases_30d=1,
    )
    result = score_intel(feat=feat, pushed_age_days=3)
    assert _val(result.potential) is not None
    assert _val(result.openness) is None
    assert _val(result.entry_fit) is None
    assert _val(result.eev) is None
    assert result.decision == "数据不足"


def test_eev_defined_if_potential_and_openness_known():
    feat = FeaturesBlob(
        commits_30d=30,
        recent_contributors_7d=4,
        releases_30d=1,
        pr_external_closed_n=10,
        pr_external_merged_closed_n=8,
    )
    result = score_intel(
        feat=feat,
        pushed_age_days=3,
        direction_fit=80,
        contribution_opp=80,
        strategy_path="issue-first",
    )
    assert _val(result.potential) is not None
    assert _val(result.openness) is not None
    assert _val(result.entry_fit) is not None
    assert _val(result.eev) is not None
    assert _val(result.eev) != 0
    assert result.decision != "数据不足"


def test_eev_not_creator_only():
    result = score_intel(
        owner_payload=_success_owner(),
        current_full_name="acme/current",
        now=NOW,
    )
    assert _val(result.creator_prior) is not None
    assert 0 < _val(result.creator_prior) <= 100
    assert _val(result.potential) is None
    assert _val(result.eev) is None


def test_prior_weight_decreases_with_snapshot_count():
    a = score_intel(snapshot_count=0)
    b = score_intel(snapshot_count=4)
    c = score_intel(snapshot_count=10)
    assert a.prior_weight == pytest.approx(1.0)
    assert b.prior_weight == pytest.approx(1 / 5)
    assert c.prior_weight == pytest.approx(1 / 11)
    assert a.prior_weight > b.prior_weight > c.prior_weight


def test_intel_independent_of_official_formula():
    import ast

    import foreshadow.pipeline.intel as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.append(module)
            names = {alias.name for alias in node.names}
            assert "mix_opportunity" not in names
            assert module != "foreshadow.pipeline.select"
            assert module != "foreshadow.pipeline.score"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
                assert alias.name != "foreshadow.pipeline.select"
    assert "foreshadow.pipeline.select" not in imported


def test_raw_stars_are_not_potential():
    result = score_intel(stars=100_000, windows_v7=80)
    assert _val(result.potential) is None
    assert _val(result.potential) != 80


def test_missing_openness_does_not_beat_known_low():
    from foreshadow.pipeline.intel import _eev

    kw = {
        "potential": 80.0,
        "entry_fit": 90.0,
        "creator": None,
        "prior_weight": 0.0,
        "pot_conf": "medium",
        "open_conf": "medium",
        "entry_conf": "medium",
    }
    miss, *_ = _eev(openness=None, **kw)
    low, *_ = _eev(openness=25.0, **kw)
    high, *_ = _eev(openness=80.0, **kw)
    terrible, *_ = _eev(openness=5.0, **kw)
    assert (
        miss is not None
        and low is not None
        and high is not None
        and terrible is not None
    )
    assert miss < low
    assert miss < high
    assert miss > terrible
    assert miss != low


def test_eev_requires_potential_and_entry_fit():
    from foreshadow.pipeline.intel import _eev

    kw = {
        "creator": None,
        "prior_weight": 0.0,
        "pot_conf": "medium",
        "open_conf": "medium",
        "entry_conf": "medium",
    }
    none_p, *_ = _eev(potential=None, entry_fit=90.0, openness=80.0, **kw)
    none_e, *_ = _eev(potential=80.0, entry_fit=None, openness=80.0, **kw)
    ok, *_ = _eev(potential=80.0, entry_fit=90.0, openness=80.0, **kw)
    assert none_p is None
    assert none_e is None
    assert ok is not None


def test_pr_accept_rate_is_not_openness():
    feat = FeaturesBlob(
        pr_accept_rate=0.94,
        pr_merged_sample_n=3,
        pr_external_merged_n=3,
    )
    result = score_intel(feat=feat)
    assert _val(result.openness) is None
