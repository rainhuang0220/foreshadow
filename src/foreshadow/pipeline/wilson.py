"""Wilson score interval. NA when n is 0; never a 0-fill."""

from __future__ import annotations

import math


def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float | None:
    """Lower bound of the Wilson interval for a binomial proportion, in [0, 1]."""
    if n <= 0:
        return None
    successes = min(max(successes, 0), n)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    inner = (p * (1.0 - p) + z2 / (4.0 * n)) / n
    margin = z * math.sqrt(max(inner, 0.0))
    lo = (centre - margin) / denom
    return max(0.0, min(1.0, lo))
