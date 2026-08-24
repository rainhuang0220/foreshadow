from __future__ import annotations

from collections.abc import Sequence

from foreshadow.pipeline.score import ScoredRepo

_EXCEPTIONAL = frozenset(
    {
        "off_direction_but_strong",
        "exceptional_override",
        "exceptional_override_weak_fit",
    }
)


def select_top(
    rows: Sequence[ScoredRepo],
    *,
    min_opportunity: float = 55,
    min_explosion: float = 35,
    max_per_owner: int = 2,
) -> list[ScoredRepo]:
    pool = [row for row in rows if _eligible(row, min_opportunity, min_explosion)]
    pool.sort(
        key=lambda row: (
            -(row.breakdown.opportunity.value or 0.0),
            -(row.breakdown.explosion.value or 0.0),
            -(row.breakdown.contribution.value or 0.0),
        )
    )
    selected: list[ScoredRepo] = []
    for row in pool:
        n_owner = sum(1 for item in selected if item.owner == row.owner)
        if n_owner >= max_per_owner:
            continue
        row.breakdown.selected_rank = len(selected) + 1
        selected.append(row)
        if len(selected) == 5:
            break
    return selected


def _eligible(
    row: ScoredRepo,
    min_opportunity: float,
    min_explosion: float,
) -> bool:
    bd = row.breakdown
    if bd.vetoed:
        return False
    if "tree_missing" in bd.flags:
        return False
    mom = bd.momentum
    if mom.value is None or mom.confidence not in {"medium", "high"}:
        return False
    if bd.explosion.value is None:
        return False
    if bd.opportunity.value is None or bd.opportunity.value < min_opportunity:
        return False
    if bd.explosion.value < min_explosion:
        return False
    df = bd.direction_fit.value
    if df is None:
        return False
    if df >= 70:
        return True
    return bd.exceptional in _EXCEPTIONAL
