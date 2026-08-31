from __future__ import annotations

from foreshadow.board.schema import DIM_KEYS, DimensionView, EvidenceItem
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.score import ScoredRepo

_P0_TO_DIM = {
    "momentum": "momentum",
    "real_user": "real_users",
    "gap": "contributor_gap",
    "contribution_opp": "contribution_opportunity",
    "early_entry": "early_entry",
}


def to_dim20(value: float | None) -> int | None:
    if value is None:
        return None
    n = round(value / 5.0)
    return max(0, min(20, n))


def dimensions_from_breakdown(bd: ScoreBreakdown) -> dict[str, int | None]:
    mapping = {
        "momentum": bd.momentum,
        "real_users": bd.real_user,
        "contributor_gap": bd.gap,
        "contribution_opportunity": bd.contribution_opp,
        "early_entry": bd.early_entry,
    }
    return {key: to_dim20(cs.value) for key, cs in mapping.items()}


def dimension_views(bd: ScoreBreakdown) -> list[DimensionView]:
    out: list[DimensionView] = []
    pairs = (
        ("momentum", bd.momentum),
        ("real_users", bd.real_user),
        ("contributor_gap", bd.gap),
        ("contribution_opportunity", bd.contribution_opp),
        ("early_entry", bd.early_entry),
    )
    for key, cs in pairs:
        na = cs.value is None
        hist = key == "momentum" and (
            na or "v7" in cs.missing or "S(t-7)" in cs.missing
        )
        out.append(
            DimensionView(
                key=key,
                value=to_dim20(cs.value),
                insufficient_history=hist,
                why=cs.why or ("INSUFFICIENT HISTORY" if hist else ""),
            )
        )
    return out


def evidence_from_scored(row: ScoredRepo) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    bd = row.breakdown
    attr = {
        "momentum": bd.momentum,
        "real_user": bd.real_user,
        "gap": bd.gap,
        "contribution_opp": bd.contribution_opp,
        "early_entry": bd.early_entry,
    }
    for p0_key, dim_key in _P0_TO_DIM.items():
        cs: ComponentScore = attr[p0_key]
        polarity: str = "-" if cs.value is None or cs.value < 50 else "+"
        items.append(
            EvidenceItem(
                metric=dim_key,
                detail=cs.why or ("N/A" if cs.value is None else ""),
                source="p0_component",
                window="7d/30d snapshots" if dim_key == "momentum" else None,
                observed=None if cs.value is None else f"{cs.value:.1f}/100",
                polarity=polarity,  # type: ignore[arg-type]
            )
        )
    windows = (row.evidence or {}).get("windows") or {}
    if windows:
        items.append(
            EvidenceItem(
                metric="windows",
                detail=(
                    f"v7={windows.get('v7')} v30={windows.get('v30')} "
                    f"source={windows.get('v7_source')}"
                ),
                source="snapshots",
                window="v7",
                observed=None if windows.get("v7") is None else str(windows.get("v7")),
                polarity="+" if windows.get("v7") is not None else "-",
            )
        )
    if bd.vetoed:
        items.append(
            EvidenceItem(
                metric="h_rules",
                detail=bd.veto_reason or "vetoed",
                source="h_rules",
                polarity="-",
            )
        )
    return items


def growth_signal(row: ScoredRepo) -> str:
    mom = row.breakdown.momentum
    if mom.value is None:
        return "N/A (no v7)"
    windows = (row.evidence or {}).get("windows") or {}
    rel = windows.get("rel_growth_7d")
    if rel is None:
        return f"momentum {mom.value:.0f}/100"
    return f"7d rel {rel:.2f}"


def lightweight_score(dims: dict[str, int | None]) -> float | None:
    """Equal 20% per dimension; drop NA; do not fill 0 or renormalize."""
    total = 0.0
    present = False
    for key in DIM_KEYS:
        d = dims.get(key)
        if d is None:
            continue
        present = True
        total += 0.20 * (d / 20.0) * 100.0
    return total if present else None
