from datetime import UTC, datetime

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.openness import (
    compute_openness,
    compute_openness_from_prs,
)
from foreshadow.pipeline.wilson import wilson_lower_bound


def _pr(
    n: int,
    *,
    assoc: str = "NONE",
    login: str = "alice",
    merged: bool = True,
    type_: str = "User",
    reviews: int = 1,
) -> dict:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    merged_at = datetime(2026, 1, 2, tzinfo=UTC) if merged else None
    return {
        "number": n,
        "author": {"login": login, "type": type_},
        "authorAssociation": assoc,
        "createdAt": created.isoformat(),
        "mergedAt": merged_at.isoformat() if merged_at else None,
        "reviews": {"totalCount": reviews},
        "comments": {"nodes": []},
    }


def test_wilson_n_zero_is_none():
    assert wilson_lower_bound(0, 0) is None
    assert wilson_lower_bound(3, 0) is None


def test_n_ext_3_openness_is_na_not_94():
    merged = [_pr(i) for i in range(3)]
    result = compute_openness_from_prs(merged, [])
    assert result.na is True
    assert result.score is None
    assert result.score != 94
    assert result.score != 0.94
    assert result.closed_ext == 3
    assert result.confidence == "low"


def test_n_ext_10_all_merged_external_wilson_below_100():
    merged = [_pr(i) for i in range(10)]
    result = compute_openness_from_prs(merged, [])
    assert result.na is False
    assert result.score is not None
    assert result.score < 100
    assert result.score != 0
    lb = wilson_lower_bound(10, 10)
    assert lb is not None
    assert result.score == round(lb * 100, 4)
    assert result.confidence == "medium"
    assert result.sample_n == 10


def test_openness_does_not_use_pr_accept_rate():
    feat = FeaturesBlob(
        pr_accept_rate=0.94,
        pr_merged_sample_n=3,
        pr_external_merged_n=3,
    )
    result = compute_openness(feat)
    assert result.score is None
    assert result.na is True


def test_bots_never_count_as_external():
    bots = [
        _pr(1, login="dependabot[bot]", type_="Bot"),
        _pr(2, login="renovate", type_="User"),
        _pr(3, login="greenkeeper", type_="User"),
        _pr(4, login="github-actions", type_="User"),
        _pr(5, login="helper[bot]"),
    ]
    humans = [_pr(10 + i, login=f"human{i}") for i in range(3)]
    result = compute_openness_from_prs(bots + humans, [])
    assert result.closed_ext == 3
    assert result.score is None
    assert result.na is True


def test_maintainers_are_not_external():
    owners = [_pr(i, assoc="OWNER", login=f"own{i}") for i in range(10)]
    result = compute_openness_from_prs(owners, [])
    assert result.closed_ext == 0
    assert result.score is None


def test_feat_n_ext_10_matches_wilson():
    feat = FeaturesBlob(
        pr_closed_sample_n=10,
        pr_external_closed_n=10,
        pr_external_merged_closed_n=10,
    )
    result = compute_openness(feat)
    assert result.na is False
    assert result.score is not None
    assert result.score < 100
