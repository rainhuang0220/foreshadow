"""v1 vs v2 ranking helpers. Official Top 5 stays on v1 via select.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from foreshadow.pipeline.score import ScoredRepo

KNOWN_BIAS_RECENCY = "discovery_recency_bias"


def pool_rank_key(scored: ScoredRepo, data: dict[str, Any]) -> tuple:
    """Sort reverse=True among ALL scored rows (not official Top 5).

    Opportunity DESC (NULL last), Explosion DESC (NULL last),
    stars ASC (NULL last), node_id ASC. Stars break ties only; not a bonus.
    """
    opp = scored.breakdown.opportunity.value
    exp = scored.breakdown.explosion.value
    stars = data.get("S")
    nid = str(data.get("node_id") or scored.full_name or "")
    return (
        0 if opp is None else 1,
        float(opp or 0.0),
        0 if exp is None else 1,
        float(exp or 0.0),
        -float(stars) if stars is not None else -1e12,
        nid,
    )


def assign_pool_ranks(
    items: Sequence[tuple[ScoredRepo, dict[str, Any]]],
) -> dict[str, int]:
    ordered = sorted(items, key=lambda it: pool_rank_key(it[0], it[1]), reverse=True)
    ranks: dict[str, int] = {}
    for i, (scored, data) in enumerate(ordered, start=1):
        key = str(data.get("node_id") or scored.full_name)
        ranks[key] = i
    return ranks


def pool_rank_key_v2(scored: ScoredRepo, data: dict[str, Any]) -> tuple:
    """Main S1 pool ranks above experimental. Stars still tie-break only."""
    s1 = (scored.evidence or {}).get("s1") or {}
    main = 1 if s1.get("pool") == "main" else 0
    return (main,) + pool_rank_key(scored, data)


def assign_pool_ranks_v2(
    items: Sequence[tuple[ScoredRepo, dict[str, Any]]],
) -> dict[str, int]:
    ordered = sorted(items, key=lambda it: pool_rank_key_v2(it[0], it[1]), reverse=True)
    ranks: dict[str, int] = {}
    for i, (scored, data) in enumerate(ordered, start=1):
        key = str(data.get("node_id") or scored.full_name)
        ranks[key] = i
    return ranks


def rank_delta(v1_rank: int | None, v2_rank: int | None) -> int | None:
    """Positive means the repo moved up under v2 (v1 #34 → v2 #5 is +29)."""
    if v1_rank is None or v2_rank is None:
        return None
    return int(v1_rank) - int(v2_rank)


def identity_key(scored: ScoredRepo, data: dict[str, Any]) -> str:
    return str(data.get("node_id") or scored.full_name)
