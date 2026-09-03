"""Shadow ε-greedy exploration log. Does not change Official or EEV ranking."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any


def shadow_explore(
    candidates: Sequence[str],
    ranked: Sequence[str],
    *,
    epsilon: float = 0.1,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Log a Phase-B exploration pick. Leaves ``candidates`` and ``ranked`` unchanged."""
    rng = rng or random.Random()
    top = {str(name) for name in list(ranked)[:5]}
    pool = [str(name) for name in candidates if str(name) not in top]
    explored: str | None = None
    if pool and rng.random() < float(epsilon):
        explored = rng.choice(pool)
    return {
        "policy": "shadow_eps_greedy",
        "epsilon": float(epsilon),
        "explored": explored,
        "mode": "shadow",
    }
