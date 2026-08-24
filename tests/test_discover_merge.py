from datetime import date

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline.discover import (
    SEARCH_QUERY_TEMPLATES,
    cap_candidates,
    discover_hydrate_snapshot,
    search_candidates,
)


def test_search_queries_have_no_fork_false():
    for key, q in SEARCH_QUERY_TEMPLATES.items():
        assert "fork:false" not in q
        assert "fork: false" not in q
        if key == "breakout":
            assert "sort:stars" in q
        else:
            assert "sort:stars" not in q


def test_search_candidates_templates_and_no_fork_false(frozen_clock):
    gh = FakeGitHub(search_nodes=[repo_node("R_a", "acme/a")])
    hits = search_candidates(gh, Settings(), frozen_clock.today())
    assert hits
    assert len(gh.search_queries) == 12
    for q in gh.search_queries:
        assert "fork:false" not in q
    assert any("sort:stars" in q for q in gh.search_queries)
    breakout = [q for q in gh.search_queries if "sort:stars" in q]
    assert len(breakout) == 1
    q0 = gh.search_queries[0]
    assert "stars:50..8000" in q0
    assert "pushed:>2026-07-10" in q0


def test_two_queries_one_node_one_candidate(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_same", "acme/dup", description="one node two queries")
    gh = FakeGitHub(
        nodes={node["id"]: node},
        search_pages=[[node], [node]] + [[]] * 10,
    )
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    rows = conn.execute(
        "SELECT repo_id, discovery_source FROM candidates WHERE run_id=?",
        (result.run_id,),
    ).fetchall()
    assert len(rows) == 1
    names = conn.execute("SELECT full_name FROM repos").fetchall()
    assert [n[0] for n in names] == ["acme/dup"]


def test_discovery_source_watchlist_plus_search(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_w", "acme/watched", topics=["mcp"])
    rid = seed_repo(conn, "R_w", "acme/watched")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(nodes={node["id"]: node}, search_pages=[[node]] + [[]] * 11)
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    source = conn.execute(
        "SELECT discovery_source FROM candidates WHERE run_id=?",
        (result.run_id,),
    ).fetchone()[0]
    assert source.startswith("watchlist")
    assert "+search:" in source


def test_cap_dedupes_watchlist_and_search():
    from foreshadow.pipeline.discover import SearchHit

    hits = [
        SearchHit(node_id="R_w", full_name="a/w", query_key="mcp"),
        SearchHit(node_id="R_s", full_name="a/s", query_key="mcp"),
    ]
    cap = cap_candidates(["R_w"], hits, max_candidates=120)
    ids = [c.node_id for c in cap.candidates]
    assert ids == ["R_w", "R_s"]
    assert cap.search_capped is False
    assert cap.watchlist_truncated is False


def test_search_candidates_today_type():
    gh = FakeGitHub()
    hits = search_candidates(gh, Settings(), date(2026, 8, 24))
    assert hits == []
    assert len(gh.search_queries) == 12
