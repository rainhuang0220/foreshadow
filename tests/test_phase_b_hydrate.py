from datetime import UTC, datetime
from types import SimpleNamespace

from foreshadow.config import DiscoverySettings
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.direction import load_direction_bags
from foreshadow.pipeline.hydrate import (
    _pr_acceptance,
    classify_data_completeness,
    medium_shortlist,
    phase_b_shortlist,
    pre_rank_key,
)

NOW = datetime(2026, 8, 25, 0, 5, tzinfo=UTC)
BAGS = load_direction_bags()
CFG = DiscoverySettings()


def _repo(**kw):
    return SimpleNamespace(
        node_id=kw.get("node_id", "R_x"),
        name=kw.get("name", "x"),
        full_name=kw.get("full_name", "o/x"),
        description=kw.get("description", "long-term memory embedding layer"),
        language=kw.get("language", "Python"),
        topics=kw.get("topics", ["memory", "rag"]),
        stargazerCount=kw.get("stargazerCount", 100),
        pushed_at=kw.get("pushed_at", datetime(2026, 8, 25, tzinfo=UTC)),
        is_fork=False,
        is_archived=False,
        is_disabled=False,
        is_empty=False,
        status="active",
        pool=kw.get("pool"),
        query_key=kw.get("query_key"),
    )


def test_phase_b_does_not_rank_by_raw_stars():
    small = _repo(node_id="R_small", stargazerCount=70, pool="A", query_key="A_mcp")
    large = _repo(node_id="R_large", stargazerCount=5000, pool="A", query_key="A_mcp")
    k_s = pre_rank_key(small, cfg=CFG, bags=BAGS, now=NOW)
    k_l = pre_rank_key(large, cfg=CFG, bags=BAGS, now=NOW)
    assert k_s[0] == k_l[0]
    assert k_s[1] == k_l[1]
    assert k_s[2] == k_l[2]
    assert len(k_s) == 4
    assert k_s[3] == "R_small"
    assert 70 not in k_s
    assert 5000 not in k_l
    others = [
        _repo(
            node_id=f"R_b_{i}",
            full_name=f"b/r{i}",
            stargazerCount=2000,
            pool="B",
            query_key="B_mcp",
            description="generic filler without keywords",
            topics=[],
        )
        for i in range(40)
    ]
    phase = phase_b_shortlist(
        [large, small, *others],
        {},
        max_deep=30,
        cfg=CFG,
        bags=BAGS,
        now=NOW,
    )
    ids = {c.node_id for c in phase}
    assert "R_small" in ids
    assert "R_large" in ids


def test_pool_a_help_can_reach_deep_hydration():
    """A_help without direction tokens still gets the per-query floor among 5 A queries."""
    a_help = [
        _repo(
            node_id=f"R_ah_{i}",
            full_name=f"help/r{i}",
            pool="A",
            query_key="A_help",
            stargazerCount=20 + i,
            description="small CLI with help-wanted issues",
            topics=["help-wanted"],
        )
        for i in range(8)
    ]
    a_other = []
    for qk in ("A_mcp", "A_agent", "A_memory", "A_eval"):
        for i in range(8):
            a_other.append(
                _repo(
                    node_id=f"R_{qk}_{i}",
                    full_name=f"{qk}/r{i}",
                    pool="A",
                    query_key=qk,
                    stargazerCount=80 + i,
                )
            )
    b_hits = [
        _repo(
            node_id=f"R_bh_{i}",
            full_name=f"big/r{i}",
            pool="B",
            query_key="B_mcp",
            stargazerCount=1800,
            description="long-term memory embedding layer",
        )
        for i in range(40)
    ]
    phase = phase_b_shortlist(
        a_help + a_other + b_hits,
        {},
        max_deep=30,
        cfg=CFG,
        bags=BAGS,
        now=NOW,
    )
    keys = [getattr(c, "query_key", None) for c in phase]
    pools = [getattr(c, "pool", None) for c in phase]
    assert keys.count("A_help") >= CFG.phase_b_per_query_floor
    assert keys.count("A_help") >= 2
    assert pools.count("A") == CFG.phase_b_pool_a
    assert pools.count("B") >= CFG.phase_b_pool_b
    assert len(phase) == 30


def test_pr_acceptance_empty_sample_is_unknown():
    n, ext, rate, rev, rrate = _pr_acceptance({})
    assert n is None and ext is None and rate is None
    assert rev is None and rrate is None
    n, ext, rate, rev, rrate = _pr_acceptance({"prsMerged": {"nodes": []}})
    assert n == 0
    assert ext is None
    assert rate is None
    assert rev is None and rrate is None
    n, ext, rate, rev, rrate = _pr_acceptance(
        {
            "prsMerged": {
                "nodes": [
                    {
                        "authorAssociation": "CONTRIBUTOR",
                        "reviews": {"totalCount": 1},
                    },
                    {"authorAssociation": "OWNER", "reviews": {"totalCount": 0}},
                ]
            }
        }
    )
    assert n == 2
    assert ext == 1
    assert rate == 0.5
    assert rev == 1
    assert rrate == 0.5


def test_activity_counts_are_not_star_growth(frozen_clock):
    from foreshadow.pipeline.score import score_repo

    repo = {
        "owner": "acme",
        "name": "toy",
        "full_name": "acme/toy",
        "description": "memory rag llm",
        "license_spdx": "MIT",
        "age_days": 40,
        "pushed_age_days": 1,
        "S": 80,
        "F": 4,
        "snapshots": [{"date": "2026-08-25", "stars": 80, "forks": 4}],
        "features": {"phase": "M", "commits_7d": 20, "commits_30d": 40},
    }
    scored = score_repo(repo, clock=frozen_clock)
    assert scored.breakdown.explosion.value is None
    assert scored.evidence["windows"]["v7"] is None
    assert "commits_7d" not in str(scored.evidence["windows"])


def test_phase_b_unused_c_quota_still_fills_thirty():
    """Underfilled C does not leave Phase B short; leftover is not a star sort."""
    a_hits = [
        _repo(
            node_id=f"R_a_{i}",
            full_name=f"early/r{i}",
            pool="A",
            query_key="A_mcp",
            stargazerCount=20 + i,
        )
        for i in range(25)
    ]
    b_hits = [
        _repo(
            node_id=f"R_bb_{i}",
            full_name=f"mid/r{i}",
            pool="B",
            query_key="B_mcp",
            stargazerCount=1800,
            description="generic filler without keywords",
            topics=[],
        )
        for i in range(25)
    ]
    c_hits = [
        _repo(
            node_id="R_c_only",
            full_name="new/one",
            pool="C",
            query_key="C_mcp",
            stargazerCount=4,
        )
    ]
    phase = phase_b_shortlist(
        a_hits + b_hits + c_hits,
        {},
        max_deep=30,
        cfg=CFG,
        bags=BAGS,
        now=NOW,
    )
    pools = [getattr(c, "pool", None) for c in phase]
    assert len(phase) == 30
    assert pools.count("A") >= CFG.phase_b_pool_a
    assert pools.count("B") >= CFG.phase_b_pool_b
    assert pools.count("C") == 1
    assert "R_c_only" in {c.node_id for c in phase}


def test_medium_shortlist_does_not_rank_by_raw_stars():
    small = _repo(node_id="R_ms", stargazerCount=70, pool="A", query_key="A_mcp")
    large = _repo(node_id="R_ml", stargazerCount=5000, pool="A", query_key="A_mcp")
    others = [
        _repo(
            node_id=f"R_mb_{i}",
            full_name=f"mb/r{i}",
            stargazerCount=2000,
            pool="B",
            query_key="B_mcp",
            description="generic filler without keywords",
            topics=[],
        )
        for i in range(40)
    ]
    medium = medium_shortlist(
        [large, small, *others],
        already=[],
        cfg=CFG,
        bags=BAGS,
        now=NOW,
    )
    ids = {c.node_id for c in medium}
    assert "R_ms" in ids
    assert "R_ml" in ids
    assert len(medium) == CFG.max_medium_hydrate


def test_completeness_does_not_use_zero_for_missing():
    low = classify_data_completeness(None, None)
    assert low == "low"
    med = classify_data_completeness(
        FeaturesBlob(phase="M", commits_30d=4), contributor_count=3
    )
    assert med == "medium"
    high = classify_data_completeness(
        FeaturesBlob(
            phase="B",
            issue_sample_n=4,
            tree_names=["src"],
            maint_touch=0.5,
            pr_merged_sample_n=3,
        ),
        contributor_count=5,
    )
    assert high == "high"
