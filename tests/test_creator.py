from datetime import UTC, datetime

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.creator import compute_creator_prior

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _node(
    name: str,
    *,
    created: str,
    pushed: str,
    archived: bool = False,
    stars: int = 0,
    releases: int = 0,
    fork: bool = False,
) -> dict:
    return {
        "nameWithOwner": name,
        "createdAt": created,
        "pushedAt": pushed,
        "isArchived": archived,
        "isFork": fork,
        "stargazerCount": stars,
        "forkCount": 0,
        "releases": {"totalCount": releases},
    }


def _owner(nodes: list[dict], *, login: str = "acme", total: int | None = None) -> dict:
    return {
        "__typename": "User",
        "login": login,
        "followers": {"totalCount": 500_000},
        "twitterUsername": "acme",
        "repositories": {
            "totalCount": total if total is not None else len(nodes),
            "nodes": nodes,
        },
    }


def test_celebrity_star_sum_does_not_auto_90_if_abandoned():
    nodes = [
        _node(
            f"celeb/old{i}",
            created="2018-01-01T00:00:00Z",
            pushed="2019-01-01T00:00:00Z",
            archived=True,
            stars=100_000,
        )
        for i in range(3)
    ]
    prior = compute_creator_prior(
        _owner(nodes, login="celeb"),
        current_full_name="celeb/now",
        now=NOW,
    )
    assert prior.score is not None
    assert prior.score < 90
    assert prior.abandoned_n == 3
    assert prior.success_n == 0


def test_three_successful_maintained_repos_prior_in_range():
    nodes = [
        _node(
            f"acme/lib{i}",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            stars=0,
            releases=1,
        )
        for i in range(3)
    ]
    prior = compute_creator_prior(
        _owner(nodes),
        current_full_name="acme/current",
        now=NOW,
    )
    assert prior.score is not None
    assert 0 < prior.score <= 100
    assert prior.success_n == 3
    assert prior.na is False
    assert prior.owner_type == "User"


def test_fewer_than_three_usable_repos_is_na():
    nodes = [
        _node(
            "acme/one",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            releases=1,
        ),
        _node(
            "acme/two",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            releases=1,
        ),
    ]
    prior = compute_creator_prior(
        _owner(nodes),
        current_full_name="acme/current",
        now=NOW,
    )
    assert prior.score is None
    assert prior.na is True
    assert prior.confidence == "low"


def test_current_repo_and_forks_excluded():
    nodes = [
        _node(
            "acme/current",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            releases=1,
        ),
        _node(
            "acme/forked",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            releases=1,
            fork=True,
        ),
        _node(
            "acme/lib1",
            created="2024-01-01T00:00:00Z",
            pushed="2026-08-01T00:00:00Z",
            releases=1,
        ),
    ]
    prior = compute_creator_prior(
        _owner(nodes),
        current_full_name="acme/current",
        now=NOW,
    )
    assert prior.score is None
    assert prior.repo_n == 1


def test_feat_counts_below_3_are_na_not_zero():
    prior = compute_creator_prior(
        None,
        current_full_name="acme/now",
        now=NOW,
        feat=FeaturesBlob(creator_repo_n=2, creator_success_n=2),
    )
    assert prior.score is None
    assert prior.score != 0
