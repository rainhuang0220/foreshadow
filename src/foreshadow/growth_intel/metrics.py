"""Calendar windows. Sample count is not elapsed time. Missing stays missing."""

from __future__ import annotations

import math
from datetime import date


def log_growth(before: int | None, after: int | None) -> float | None:
    if before is None or after is None:
        return None
    if type(before) is not int or type(after) is not int:
        raise ValueError("star counts must be integers or null")
    if before < 0 or after < 0:
        raise ValueError("negative star count")
    return math.log1p(after) - math.log1p(before)


def star_window(points: list[dict], *, as_of: date) -> dict:
    parsed = []
    for item in points:
        on = date.fromisoformat(item["date"])
        if on > as_of:
            raise ValueError("future observation")
        stars = item.get("stars")
        if stars is not None and type(stars) is not int:
            raise ValueError("star counts must be integers or null")
        parsed.append((on, stars))
    parsed.sort()
    dates = [on for on, _ in parsed]
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate observation date")
    numeric = [(on, stars) for on, stars in parsed if stars is not None]
    if len(numeric) >= 2:
        elapsed = (numeric[-1][0] - numeric[0][0]).days
        delta = numeric[-1][1] - numeric[0][1]
        growth = log_growth(numeric[0][1], numeric[-1][1])
    else:
        elapsed = (parsed[-1][0] - parsed[0][0]).days if len(parsed) >= 2 else 0
        delta = None
        growth = None
    per_day = None if delta is None or elapsed <= 0 else delta / elapsed
    return {
        "points": len(parsed),
        "numeric_points": len(numeric),
        "elapsed_days": elapsed,
        "delta": delta,
        "per_day": per_day,
        "log_growth": growth,
    }
