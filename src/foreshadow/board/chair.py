from __future__ import annotations

import statistics
from dataclasses import dataclass

from foreshadow.board.reviewers import reviewer_score
from foreshadow.board.schema import (
    DIM_KEYS,
    ChairResult,
    Consensus,
    Disagreement,
    ReviewerResult,
)
from foreshadow.config import BoardSettings

_EXCLUSION = {
    "momentum": "Growth is not accelerating (or v7 history is missing).",
    "real_users": "Real-user evidence is too thin.",
    "contributor_gap": "The contributor bench is already dense / the gap is not real.",
    "contribution_opportunity": "No clear, solvable problem the user can finish.",
    "early_entry": "The project is already too mature for identity-building.",
}


@dataclass(frozen=True)
class ChairOverride:
    score: float
    justification: str


def _spread(scores: list[float]) -> float:
    return max(scores) - min(scores) if scores else 0.0


def _stdev(scores: list[float]) -> float:
    if len(scores) < 2:
        return 0.0
    return float(statistics.pstdev(scores))


def consensus_labels(
    scores: list[float],
) -> tuple[Consensus, Disagreement, float, float]:
    spread = _spread(scores)
    stdev = _stdev(scores)
    if spread >= 20 or stdev >= 10:
        return "LOW CONSENSUS", "HIGH", spread, stdev
    if spread >= 10 or stdev >= 5:
        return "MEDIUM CONSENSUS", "MEDIUM", spread, stdev
    return "HIGH CONSENSUS", "LOW", spread, stdev


def _median_dims(
    reviews: tuple[ReviewerResult, ReviewerResult, ReviewerResult],
) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for key in DIM_KEYS:
        vals = [r.dimensions.get(key) for r in reviews]
        present = [v for v in vals if v is not None]
        out[key] = round(statistics.median(present)) if present else None
    return out


def _auto_justification(
    trend: ReviewerResult,
    community: ReviewerResult,
    contributor: ReviewerResult,
    disagreement: Disagreement,
    dims: dict[str, int | None],
) -> tuple[bool, str]:
    t, c, k = trend.score, community.score, contributor.score
    if None in (t, c, k):
        return False, "At least one reviewer could not score; Chair does not override."
    assert t is not None and c is not None and k is not None
    if dims.get("momentum") is None:
        return (
            False,
            (
                "Momentum is N/A. Chair will not treat ranking as official. "
                "Trend is discounted more than the others because its weight on Momentum is 35%."
            ),
        )
    if disagreement == "HIGH" and t >= 80 and c <= 60:
        return (
            True,
            (
                "HIGH disagreement: Trend sees breakout signal but Community does not "
                "see users. Chair down-weights unconfirmed acceleration."
            ),
        )
    if disagreement == "HIGH" and k >= 80 and t <= 60:
        return (
            True,
            (
                "HIGH disagreement: Contributor surface is strong while Trend is weak. "
                "Chair treats this as a skill-building entry, not an explosion bet."
            ),
        )
    if disagreement == "HIGH":
        return (
            False,
            (
                f"HIGH disagreement (Trend {t:.0f}, Community {c:.0f}, Contributor {k:.0f}). "
                "Chair uses the 40/20/20/20 blend and records the spread instead of averaging it away."
            ),
        )
    return (
        False,
        "Reviewers roughly agree. Chair uses the configured blend, not a silent average.",
    )


def exclusion_reason(
    dims: dict[str, int | None],
    *,
    veto_reason: str | None,
    momentum_na: bool,
    final_score: float | None,
    fifth_score: float | None,
) -> str:
    if veto_reason:
        return f"Hard reject ({veto_reason})."
    if momentum_na:
        return "Insufficient v7 history — official Top 5 is unavailable for this repo."
    filled = {k: v for k, v in dims.items() if v is not None}
    if filled:
        weakest = min(filled, key=lambda k: filled[k])
        if filled[weakest] <= 12:
            return _EXCLUSION[weakest]
    if fifth_score is not None and final_score is not None:
        gap = fifth_score - final_score
        if gap > 0:
            return f"Out-ranked: {gap:.1f} points behind the last official/provisional seat."
    return "Below the Chair cut after evidence review — not a missing score, a weaker case."


def chair_decide(
    trend: ReviewerResult,
    community: ReviewerResult,
    contributor: ReviewerResult,
    settings: BoardSettings,
    *,
    override: ChairOverride | None = None,
    veto_reason: str | None = None,
) -> ChairResult:
    scores = [
        s for s in (trend.score, community.score, contributor.score) if s is not None
    ]
    consensus, disagreement, spread, stdev = consensus_labels(scores)
    dims = _median_dims((trend, community, contributor))
    equal = {k: 20 for k in DIM_KEYS}
    chair_raw = reviewer_score(dims, equal)
    blend = None
    if (
        chair_raw is not None
        and trend.score is not None
        and community.score is not None
        and contributor.score is not None
    ):
        blend = (
            settings.chair_blend * chair_raw
            + settings.trend_blend * trend.score
            + settings.community_blend * community.score
            + settings.contributor_blend * contributor.score
        )
    used_override = False
    justification: str
    score: float | None
    if override is not None:
        used_override = True
        score = override.score
        justification = override.justification
    elif veto_reason:
        used_override = True
        score = 0.0
        justification = f"Chair override: H-rules veto ({veto_reason})."
    else:
        auto, justification = _auto_justification(
            trend, community, contributor, disagreement, dims
        )
        if auto and blend is not None and chair_raw is not None:
            used_override = True
            # Pull toward Chair's own median-dimension score.
            score = 0.7 * chair_raw + 0.3 * blend
            justification = (
                justification + f" Final pulled toward Chair median ({chair_raw:.1f})."
            )
        else:
            score = blend if blend is not None else chair_raw
    weakest = None
    filled = {k: v for k, v in dims.items() if v is not None}
    if filled:
        weakest = min(filled, key=lambda k: filled[k])
    main_risk = _EXCLUSION.get(weakest or "", "Evidence still incomplete.")
    return ChairResult(
        score=score,
        blend_score=blend,
        override=used_override,
        justification=justification,
        dimensions=dims,
        consensus=consensus,
        disagreement=disagreement,
        spread=spread,
        stdev=stdev,
        main_risk=main_risk,
    )
