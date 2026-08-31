from datetime import date

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline.discover import (
    MAGNET_TERMS,
    SEARCH_QUERY_TEMPLATES,
    SearchHit,
    boolean_operator_count,
    cap_candidates,
    discover_hydrate_snapshot,
    lightweight_keep,
    pool_of,
    search_candidates,
)

_N = len(SEARCH_QUERY_TEMPLATES)
_DESC = "A substantial project description for discovery tests."


def _hit(**kw) -> SearchHit:
    key = kw.get("query_key", "B_mcp")
    return SearchHit(
        node_id=kw["node_id"],
        full_name=kw.get("full_name", "acme/tool"),
        query_key=key,
        pool=kw.get("pool") or pool_of(key),
        description=kw.get("description", _DESC),
        topics=kw.get("topics", ("mcp",)),
        fork_count=kw.get("fork_count", 2),
        stargazer_count=kw.get("stars", 80),
        has_issues=kw.get("has_issues", True),
        is_fork=kw.get("is_fork", False),
        is_archived=kw.get("is_archived", False),
        is_disabled=kw.get("is_disabled", False),
        is_empty=kw.get("is_empty", False),
    )


def test_search_queries_avoid_github_zero_result_or_mix():
    """topic:X OR topic:Y and topic:X OR \"phrase\" return 0 hits on GitHub search."""
    import re

    for q in SEARCH_QUERY_TEMPLATES.values():
        assert '"' not in q
        assert not re.search(r"topic:\S+\s+OR\s+topic:", q)
        assert not re.search(r"topic:\S+\s+OR\s+", q)
        assert not re.search(r"\s+OR\s+topic:", q)


def test_search_queries_have_no_fork_false():
    assert len(SEARCH_QUERY_TEMPLATES) == 14
    for key, q in SEARCH_QUERY_TEMPLATES.items():
        assert "fork:false" not in q
        assert "fork: false" not in q
        assert "sort:stars" not in q
        assert "sort:updated" in q
        assert boolean_operator_count(q) <= 5
        lowered = q.lower()
        for magnet in MAGNET_TERMS:
            assert magnet not in lowered
        if key.startswith("A_"):
            assert "stars:{early}" in q
        if key.startswith("B_"):
            assert "stars:{rising}" in q
        if key.startswith("C_"):
            assert "stars:" not in q
            assert "created:>{created180}" in q


def test_search_candidates_templates_and_no_fork_false(frozen_clock):
    gh = FakeGitHub(search_nodes=[repo_node("R_a", "acme/a")])
    hits = search_candidates(gh, Settings(), frozen_clock.today())
    assert hits
    assert len(gh.search_queries) == _N
    for q in gh.search_queries:
        assert "fork:false" not in q
        assert "sort:stars" not in q
    assert any("stars:10..400" in q for q in gh.search_queries)
    assert any("stars:100..3000" in q for q in gh.search_queries)
    q0 = gh.search_queries[0]
    assert "stars:10..400" in q0
    assert "pushed:>2026-07-10" in q0
    assert "sort:updated" in q0


def test_two_queries_one_node_one_candidate(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_same", "acme/dup", description="one node two queries")
    gh = FakeGitHub(
        nodes={node["id"]: node},
        search_pages=[[node], [node]] + [[]] * _N,
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
    gh = FakeGitHub(nodes={node["id"]: node}, search_pages=[[node]] + [[]] * _N)
    result = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    source = conn.execute(
        "SELECT discovery_source FROM candidates WHERE run_id=?",
        (result.run_id,),
    ).fetchone()[0]
    assert source.startswith("watchlist")
    assert "+search:" in source


def test_cap_dedupes_watchlist_and_search():
    hits = [
        _hit(node_id="R_w", full_name="a/w", query_key="A_mcp"),
        _hit(node_id="R_s", full_name="a/s", query_key="A_mcp"),
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
    assert len(gh.search_queries) == _N


def test_lightweight_keep_drops_stuffed_and_empty_desc():
    good = _hit(node_id="R_ok", query_key="A_mcp", stars=40)
    assert lightweight_keep(good)
    empty = _hit(
        node_id="R_empty",
        query_key="A_mcp",
        description="",
        topics=(),
        fork_count=0,
    )
    assert not lightweight_keep(empty)
    stuffed = _hit(
        node_id="R_st",
        query_key="B_mcp",
        description="best ultimate awesome ai llm agent gpt rag toolkit",
    )
    assert not lightweight_keep(stuffed)
    awesome = _hit(node_id="R_aw", full_name="org/awesome-llm", query_key="C_mcp")
    assert not lightweight_keep(awesome)
    pool_c_thin = _hit(node_id="R_c", query_key="C_mcp", description="short")
    assert not lightweight_keep(pool_c_thin)
    pool_c_lonely = _hit(
        node_id="R_c0",
        query_key="C_mcp",
        description=_DESC,
        topics=(),
        fork_count=0,
    )
    assert not lightweight_keep(pool_c_lonely)
    pool_c_zero = _hit(
        node_id="R_c00",
        query_key="C_mcp",
        description=_DESC,
        topics=("mcp",),
        fork_count=0,
        stars=0,
    )
    assert not lightweight_keep(pool_c_zero)
    pool_c_ok = _hit(node_id="R_c2", query_key="C_mcp", description=_DESC)
    assert lightweight_keep(pool_c_ok)


def test_cap_round_robin_pool_a_not_starved():
    b_hits = [
        _hit(node_id=f"R_b_{i}", full_name=f"big/r{i}", query_key="B_mcp", stars=2000)
        for i in range(40)
    ]
    a_hits = [
        _hit(node_id=f"R_a_{i}", full_name=f"early/r{i}", query_key="A_mcp", stars=40)
        for i in range(15)
    ]
    cap = cap_candidates([], b_hits + a_hits, max_candidates=120)
    pools = [c.pool for c in cap.candidates]
    assert pools.count("A") == 15
    assert pools.count("B") == 40
    assert cap.search_capped is False
    assert len(cap.candidates) == 55


def test_cap_does_not_fifo_fill_unused_quota():
    b_hits = [
        _hit(node_id=f"R_b_{i}", full_name=f"big/r{i}", query_key="B_mcp", stars=1800)
        for i in range(80)
    ]
    cap = cap_candidates([], b_hits, max_candidates=120)
    assert len(cap.candidates) == 50
    assert all(c.pool == "B" for c in cap.candidates)
    assert cap.search_capped is True


def test_pool_a_underfill_does_not_backfill_junk():
    junk = [
        _hit(
            node_id=f"R_j_{i}",
            full_name=f"x/awesome-list-{i}",
            query_key="A_mcp",
            description="best ultimate awesome ai llm",
        )
        for i in range(40)
    ]
    good = [_hit(node_id="R_g", full_name="acme/real-mcp", query_key="A_mcp")]
    cap = cap_candidates([], junk + good, max_candidates=120)
    assert [c.node_id for c in cap.candidates] == ["R_g"]


def test_dedup_prefers_pool_a_over_b(frozen_clock):
    node = repo_node("R_both", "acme/both", description=_DESC, topics=["mcp"])
    gh = FakeGitHub(
        nodes={node["id"]: node},
        search_pages=[[node]] + [[]] * 4 + [[node]] + [[]] * _N,
    )
    hits = search_candidates(gh, Settings(), frozen_clock.today())
    by_id = {h.node_id: h for h in hits}
    assert by_id["R_both"].pool == "A"
    assert by_id["R_both"].query_key.startswith("A_")


def test_round_robin_per_query_inside_pool():
    hits = []
    for i in range(10):
        hits.append(_hit(node_id=f"R_m_{i}", full_name=f"a/m{i}", query_key="A_mcp"))
    for i in range(10):
        hits.append(_hit(node_id=f"R_h_{i}", full_name=f"a/h{i}", query_key="A_help"))
    disc = DiscoverySettings(pool_a_quota=12, pool_b_quota=0, pool_c_quota=0)
    cap = cap_candidates([], hits, max_candidates=120, disc=disc)
    keys = [c.query_key for c in cap.candidates]
    assert keys.count("A_mcp") == 6
    assert keys.count("A_help") == 6


def test_unused_a_quota_is_not_given_to_extra_b():
    a_hits = [
        _hit(node_id=f"R_a_{i}", full_name=f"early/r{i}", query_key="A_mcp", stars=40)
        for i in range(10)
    ]
    b_hits = [
        _hit(node_id=f"R_b_{i}", full_name=f"big/r{i}", query_key="B_mcp", stars=1800)
        for i in range(80)
    ]
    cap = cap_candidates([], a_hits + b_hits, max_candidates=120)
    pools = [c.pool for c in cap.candidates]
    assert pools.count("A") == 10
    assert pools.count("B") == 50
    assert len(cap.candidates) == 60
    assert cap.search_capped is True


def test_pool_a_requires_fork_or_topics_or_help():
    bare = _hit(
        node_id="R_bare",
        query_key="A_mcp",
        topics=(),
        fork_count=0,
        description=_DESC,
    )
    assert not lightweight_keep(bare)
    forked = _hit(
        node_id="R_forked",
        query_key="A_mcp",
        topics=(),
        fork_count=3,
        description=_DESC,
    )
    assert lightweight_keep(forked)
    help_hit = _hit(
        node_id="R_help",
        query_key="A_help",
        topics=(),
        fork_count=0,
        description=_DESC,
    )
    assert lightweight_keep(help_hit)


def test_pool_c_always_runs_lightweight_keep():
    junk = [
        _hit(
            node_id=f"R_c_{i}",
            full_name=f"org/awesome-agents-{i}",
            query_key="C_mcp",
            description=_DESC,
        )
        for i in range(30)
    ]
    archived = _hit(
        node_id="R_arch",
        query_key="C_agent",
        is_archived=True,
        description=_DESC,
    )
    thin = _hit(
        node_id="R_thin",
        query_key="C_memory",
        description="tiny",
        topics=("memory",),
    )
    good = _hit(node_id="R_okc", query_key="C_bench", description=_DESC)
    cap = cap_candidates([], junk + [archived, thin, good], max_candidates=120)
    assert [c.node_id for c in cap.candidates] == ["R_okc"]
    assert all(c.pool == "C" for c in cap.candidates)


def test_tiny_remaining_prefers_pool_a_not_zero_quotas():
    hits = [
        _hit(node_id="R_a", full_name="early/one", query_key="A_mcp", stars=30),
        _hit(node_id="R_b", full_name="big/one", query_key="B_mcp", stars=900),
    ]
    cap = cap_candidates([], hits, max_candidates=1)
    assert [c.node_id for c in cap.candidates] == ["R_a"]
    assert cap.search_capped is True
