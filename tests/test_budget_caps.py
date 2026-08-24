from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from fakes import FakeGitHub, repo_node, review_time, seed_repo, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.github.client import GitHubClient, GitHubError
from foreshadow.github.queries import HYDRATE_A_NODE, SEARCH_REPOS
from foreshadow.pipeline.discover import (
    cap_candidates,
    discover_hydrate_snapshot,
    identity_ids,
    is_degraded,
)
from foreshadow.pipeline.hydrate import phase_b_shortlist


def _cand(node_id: str, stars: int = 100, **kw):
    return SimpleNamespace(
        node_id=node_id,
        name=node_id,
        full_name=kw.get("full_name", f"o/{node_id}"),
        description=kw.get("description", ""),
        language=kw.get("language", "Python"),
        topics=kw.get("topics", []),
        stargazerCount=stars,
        pushed_at=kw.get("pushed_at"),
        is_fork=False,
        is_archived=False,
        is_disabled=False,
        is_empty=False,
        status="active",
    )


def test_historical_400_plus_12_search_phase_a_bounded(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    for i in range(400):
        seed_repo(conn, f"R_hist_{i}", f"hist/r{i}")
    conn.commit()
    search = [
        repo_node(f"R_search_{i}", f"find/r{i}", stargazerCount=80 + i)
        for i in range(12)
    ]
    gh = FakeGitHub(
        nodes={n["id"]: n for n in search},
        search_nodes=search,
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    collisions = result.collisions
    assert result.candidate_count == 12
    assert gh.hydrate_a_calls <= 12 + len(collisions)
    hist_hydrated = [i for i in gh.hydrate_ids if i.startswith("R_hist_")]
    assert hist_hydrated == [] or set(hist_hydrated) <= collisions
    assert len([i for i in gh.hydrate_ids if i.startswith("R_hist_")]) <= len(
        collisions
    )


def test_watchlist_150_truncated_extra_not_hydrated(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    watch_nodes = []
    for i in range(150):
        nid = f"R_w_{i}"
        node = repo_node(nid, f"watch/r{i}")
        watch_nodes.append(node)
        rid = seed_repo(conn, nid, f"watch/r{i}")
        seed_review(conn, rid, "watch", review_time(i))
    search = [repo_node(f"R_s_{i}", f"find/s{i}") for i in range(200)]
    conn.commit()
    gh = FakeGitHub(
        nodes={n["id"]: n for n in watch_nodes + search},
        search_nodes=search,
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    assert result.candidate_count == 120
    assert result.source_health["watchlist_truncated"] is True
    extra = {f"R_w_{i}" for i in range(120, 150)}
    assert extra.isdisjoint(set(gh.hydrate_ids))
    ids = identity_ids(result.capped, conn)
    assert extra.isdisjoint(ids)
    cand_ids = {c.node_id for c in result.capped.candidates}
    assert extra.isdisjoint(cand_ids)
    assert {f"R_w_{i}" for i in range(120)} <= cand_ids


def test_enter_not_in_phase_b():
    enter = [_cand(f"R_e_{i}", stars=200) for i in range(20)]
    rankable = [_cand(f"R_r_{i}", stars=150) for i in range(10)]
    search = [_cand(f"R_s_{i}", stars=80 + i) for i in range(90)]
    candidates = enter + rankable + search
    actions = {c.node_id: "enter" for c in enter}
    actions.update({c.node_id: "watch" for c in rankable})
    phase_b = phase_b_shortlist(
        candidates,
        actions,
        max_deep=30,
        max_watchlist_deep=20,
        now=datetime(2026, 8, 24, tzinfo=UTC),
    )
    b_ids = {c.node_id for c in phase_b}
    assert len(phase_b) == 30
    assert b_ids.isdisjoint({c.node_id for c in enter})
    w_ids = {c.node_id for c in rankable}
    assert len(b_ids & w_ids) >= min(20, 10)
    assert len(b_ids & w_ids) == 10


def test_search_capped_is_not_degraded(tmp_home, frozen_clock):
    from foreshadow.pipeline.discover import SearchHit

    watch = [f"R_w_{i}" for i in range(50)]
    hits = [
        SearchHit(node_id=f"R_s_{i}", full_name=f"find/s{i}", query_key="mcp")
        for i in range(120)
    ]
    cap = cap_candidates(watch, hits, max_candidates=120)
    assert (
        cap.candidate_count == 120
        if hasattr(cap, "candidate_count")
        else len(cap.candidates) == 120
    )
    assert len(cap.candidates) == 120
    assert cap.search_capped is True
    assert cap.watchlist_truncated is False
    health = {
        "search_truncated": False,
        "search_capped": True,
        "budget_abort": False,
        "hydrate_failed": 0,
        "watchlist_truncated": False,
    }
    assert is_degraded(health) is False

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    watch_nodes = []
    for i in range(50):
        nid = f"R_w_{i}"
        node = repo_node(nid, f"watch/r{i}")
        watch_nodes.append(node)
        rid = seed_repo(conn, nid, f"watch/r{i}")
        seed_review(conn, rid, "watch", review_time(i))
    search = [repo_node(f"R_s_{i}", f"find/s{i}") for i in range(120)]
    conn.commit()
    gh = FakeGitHub(
        nodes={n["id"]: n for n in watch_nodes + search},
        search_nodes=search,
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    assert result.candidate_count == 120
    assert result.source_health["search_capped"] is True
    assert result.source_health["watchlist_truncated"] is False
    assert is_degraded(result.source_health) is False
    status = conn.execute(
        "SELECT status FROM daily_runs WHERE id=?", (result.run_id,)
    ).fetchone()[0]
    assert status == "complete"
    phase_b = result.phase_b_ids
    w = {f"R_w_{i}" for i in range(50)}
    assert len(phase_b) == 30
    assert len(set(phase_b) & w) >= 20


def test_rankable_50_phase_b_invariants():
    watch = [_cand(f"R_w_{i}", stars=50 + i) for i in range(50)]
    search = [_cand(f"R_s_{i}", stars=40) for i in range(70)]
    actions = {c.node_id: "interested" for c in watch}
    phase_b = phase_b_shortlist(
        watch + search,
        actions,
        max_deep=30,
        max_watchlist_deep=20,
        now=datetime(2026, 8, 24, tzinfo=UTC),
    )
    b_ids = {c.node_id for c in phase_b}
    w_ids = {c.node_id for c in watch}
    assert len(phase_b) == 30
    assert len(b_ids & w_ids) >= 20


def test_hydrate_a_node_not_blocked_by_budget(respx_mock):
    repo = {
        "id": "R_1",
        "nameWithOwner": "a/b",
        "stargazerCount": 10,
        "forkCount": 1,
        "isFork": False,
        "isArchived": False,
        "isDisabled": False,
        "isEmpty": False,
        "createdAt": "2026-01-01T00:00:00Z",
        "issuesOpen": {"totalCount": 2},
        "prsOpen": {"totalCount": 1},
    }
    route = respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "rateLimit": {
                        "cost": 1,
                        "remaining": 10,
                        "limit": 5000,
                        "resetAt": "2026-08-24T01:00:00Z",
                    },
                    "node": repo,
                }
            },
        )
    )
    c = GitHubClient(token="x", sleep=lambda _: None)
    c.graphql_used = 800
    c.graphql_remaining = 10
    body = c.graphql(HYDRATE_A_NODE, {"id": "R_1"})
    assert body["data"]["node"]["stargazerCount"] == 10
    assert route.call_count == 1
    with pytest.raises(GitHubError) as ei:
        c.graphql(SEARCH_REPOS, {"q": "x", "n": 1})
    assert ei.value.reason == "budget"
    assert route.call_count == 1


def test_phase_a_finishes_capped_when_budget_exhausted(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    search = [
        repo_node(f"R_s_{i}", f"find/s{i}", stargazerCount=80 + i) for i in range(5)
    ]
    gh = FakeGitHub(nodes={n["id"]: n for n in search}, search_nodes=search)
    gh.budget_graphql_points = 92
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    assert gh.hydrate_a_calls == 5
    assert result.source_health["budget_abort"] is True
    stars = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE stars IS NOT NULL"
    ).fetchone()[0]
    assert stars == 5
    assert gh.hydrate_b_calls == 0
