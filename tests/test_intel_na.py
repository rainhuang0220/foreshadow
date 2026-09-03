from __future__ import annotations

import pytest

intel = pytest.importorskip("foreshadow.pipeline.intel")
score_intel = getattr(intel, "score_intel", None)
if score_intel is None:
    pytest.skip("score_intel not exported", allow_module_level=True)

from foreshadow.models import FeaturesBlob


def _value(result, name: str):
    field = getattr(result, name, None)
    if field is None and isinstance(result, dict):
        field = result.get(name)
    if field is None:
        return None
    if hasattr(field, "value"):
        return field.value
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def test_empty_inputs_are_na_not_zero():
    result = score_intel()
    for name in ("potential", "creator_prior", "openness", "entry_fit", "eev"):
        assert _value(result, name) is None


def test_one_core_score_does_not_make_eev():
    result = score_intel(direction_fit=80)
    assert _value(result, "entry_fit") is not None
    assert _value(result, "potential") is None
    assert _value(result, "openness") is None
    assert _value(result, "eev") is None


def test_openness_na_when_external_closed_prs_below_8():
    feat = FeaturesBlob(pr_external_closed_n=7, pr_external_merged_closed_n=7)
    result = score_intel(feat=feat)
    assert _value(result, "openness") is None


def test_openness_is_not_access_score():
    feat = FeaturesBlob(
        pr_accept_rate=0.9,
        pr_merged_sample_n=20,
        pr_external_merged_n=18,
        pr_external_closed_n=3,
        pr_external_merged_closed_n=3,
        maint_touch=0.9,
    )
    result = score_intel(feat=feat)
    assert _value(result, "openness") is None


def test_creator_prior_na_when_fewer_than_3_past_repos():
    owner = {
        "__typename": "User",
        "login": "acme",
        "repositories": {
            "totalCount": 2,
            "nodes": [
                {"nameWithOwner": "acme/old1", "isFork": False},
                {"nameWithOwner": "acme/old2", "isFork": False},
            ],
        },
    }
    result = score_intel(owner_payload=owner, current_full_name="acme/now")
    assert _value(result, "creator_prior") is None


def test_creator_repo_n_below_3_is_na():
    feat = FeaturesBlob(creator_repo_n=2, creator_success_n=2)
    result = score_intel(feat=feat)
    # formula-v1 reads owner_payload first; feat counts still must not 0-fill.
    assert _value(result, "creator_prior") is None


def test_explosion_or_v7_is_not_potential():
    result = score_intel(windows_v7=80)
    assert _value(result, "potential") is None
    assert _value(result, "potential") != 80


def test_eev_omits_na_and_does_not_zero_fill():
    feat = FeaturesBlob(
        pr_external_closed_n=20,
        pr_external_merged_closed_n=20,
    )
    result = score_intel(feat=feat, direction_fit=81, contribution_opp=81)
    assert _value(result, "potential") is None
    assert _value(result, "openness") is not None
    assert _value(result, "entry_fit") is not None
    eev = _value(result, "eev")
    assert eev is not None
    assert eev != 0
    assert eev > 40
