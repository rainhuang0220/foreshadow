from datetime import UTC, datetime
from types import SimpleNamespace

from foreshadow.config import DiscoverySettings
from foreshadow.pipeline.direction import load_direction_bags
from foreshadow.pipeline.hydrate import phase_b_shortlist, pre_rank_key

NOW = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
CFG = DiscoverySettings()
BAGS = load_direction_bags()


def _repo(**kw):
    return SimpleNamespace(
        node_id=kw.get("node_id", "R_x"),
        name=kw.get("name", "x"),
        full_name=kw.get("full_name", "o/x"),
        description=kw.get("description", ""),
        language=kw.get("language", "Python"),
        topics=kw.get("topics", []),
        stargazerCount=kw.get("stargazerCount", 100),
        pushed_at=kw.get("pushed_at", datetime(2026, 8, 20, tzinfo=UTC)),
        is_fork=False,
        is_archived=False,
        is_disabled=False,
        is_empty=False,
        status="active",
    )


def _fillers(n: int, start: int = 0) -> list:
    out = []
    for i in range(start, start + n):
        out.append(
            _repo(
                node_id=f"R_fill_{i:03d}",
                name=f"fill{i}",
                full_name=f"fill/r{i}",
                description="generic filler",
                stargazerCount=60 + i,
                pushed_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
    return out


def _three_fixtures() -> list:
    memkit = _repo(
        node_id="R_memkit",
        name="memkit",
        full_name="acme/memkit",
        description="long-term memory embedding layer",
        topics=["memory", "rag"],
        stargazerCount=900,
        pushed_at=datetime(2026, 8, 23, tzinfo=UTC),
        language="Python",
    )
    giant = _repo(
        node_id="R_giant",
        name="infra",
        full_name="giant/infra",
        description="Core infrastructure",
        topics=["infra"],
        stargazerCount=100000,
        pushed_at=datetime(2026, 8, 22, tzinfo=UTC),
        language="Go",
    )
    wrapper = _repo(
        node_id="R_wrap",
        name="chatgpt-wrapper-pro",
        full_name="quick/chatgpt-wrapper-pro",
        description="",
        stargazerCount=200,
        pushed_at=datetime(2026, 6, 1, tzinfo=UTC),
        language="Python",
    )
    return [memkit, giant, wrapper]


def test_three_fixtures_always_same_30():
    fixtures = _three_fixtures()
    pool = fixtures + _fillers(30)
    first = phase_b_shortlist(
        pool, {}, max_deep=30, max_watchlist_deep=20, cfg=CFG, bags=BAGS, now=NOW
    )
    second = phase_b_shortlist(
        list(reversed(pool)),
        {},
        max_deep=30,
        max_watchlist_deep=20,
        cfg=CFG,
        bags=BAGS,
        now=NOW,
    )
    assert [c.node_id for c in first] == [c.node_id for c in second]
    assert len(first) == 30
    keys = [pre_rank_key(c, cfg=CFG, bags=BAGS, now=NOW) for c in first]
    assert keys == sorted(keys, reverse=True)
    assert first[0].node_id == "R_memkit"


def test_node_id_tiebreak_does_not_scramble():
    shared = {
        "description": "no keywords here",
        "language": "Python",
        "stargazerCount": 120,
        "pushed_at": datetime(2026, 8, 10, tzinfo=UTC),
    }
    a = _repo(node_id="R_aaa", name="a", full_name="o/a", **shared)
    b = _repo(node_id="R_bbb", name="b", full_name="o/b", **shared)
    rest = _fillers(28)
    phase = phase_b_shortlist(
        [a, b, *rest], {}, max_deep=30, cfg=CFG, bags=BAGS, now=NOW
    )
    ids = [c.node_id for c in phase]
    # reverse=True lexicographic → R_bbb before R_aaa among ties
    assert ids.index("R_bbb") < ids.index("R_aaa")
    rest_ids = [i for i in ids if i not in {"R_aaa", "R_bbb"}]
    a2 = _repo(node_id="R_zzz", name="a", full_name="o/a", **shared)
    phase2 = phase_b_shortlist(
        [a2, b, *rest], {}, max_deep=30, cfg=CFG, bags=BAGS, now=NOW
    )
    ids2 = [c.node_id for c in phase2]
    rest_ids2 = [i for i in ids2 if i not in {"R_zzz", "R_bbb"}]
    assert rest_ids == rest_ids2
    assert ids2.index("R_zzz") < ids2.index("R_bbb")


def test_pre_rank_key_spec_order():
    memkit, giant, wrapper = _three_fixtures()
    k_m = pre_rank_key(memkit, cfg=CFG, bags=BAGS, now=NOW)
    k_g = pre_rank_key(giant, cfg=CFG, bags=BAGS, now=NOW)
    k_w = pre_rank_key(wrapper, cfg=CFG, bags=BAGS, now=NOW)
    assert k_m[0] == 1  # direction hit
    assert k_m[1] == 1  # in star band
    assert k_m[2] == 2  # recency <=14
    assert k_g[1] == 0  # 100k out of band
    assert k_w[0] == 0
    assert k_w[2] == 0
    assert k_m > k_g
    assert k_m > k_w
