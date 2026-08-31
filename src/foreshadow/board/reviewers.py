from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from foreshadow.board.schema import (
    DIM_KEYS,
    EvidenceItem,
    Recommendation,
    ReviewerResult,
)
from foreshadow.config import BoardSettings, ReviewerWeightSettings

ReviewerName = Literal["trend", "community", "contributor"]

_FOCUS = {
    "trend": (
        "Early signal that this could become important infrastructure.",
        "Momentum/acceleration and early-entry room.",
    ),
    "community": (
        "Real users exist and the contributor bench is thin.",
        "User evidence, issue conversation, maintainer health.",
    ),
    "contributor": (
        "A concrete, feasible problem is sitting unsolved.",
        "Contribution surface, skill fit, unsolved issues.",
    ),
}


def reviewer_score(
    dimensions: dict[str, int | None],
    weights: dict[str, int],
) -> float | None:
    total = 0.0
    present = False
    for key in DIM_KEYS:
        d = dimensions.get(key)
        if d is None:
            continue
        present = True
        total += (weights[key] / 20.0) * d
    return total if present else None


def _confidence(dimensions: dict[str, int | None]) -> str:
    if dimensions.get("momentum") is None:
        return "low"
    missing = sum(1 for k in DIM_KEYS if dimensions.get(k) is None)
    if missing:
        return "medium"
    return "high"


def _recommendation(
    score: float | None, dimensions: dict[str, int | None]
) -> Recommendation:
    if score is None:
        return "pass"
    if dimensions.get("momentum") is None and score >= 80:
        return "candidate"
    if score >= 80:
        return "strong_candidate"
    if score >= 60:
        return "candidate"
    if score >= 40:
        return "watch"
    return "pass"


def _strengths_weaknesses(
    name: ReviewerName,
    dimensions: dict[str, int | None],
    evidence: list[EvidenceItem],
) -> tuple[list[str], list[str], list[str]]:
    strengths: list[str] = []
    weaknesses: list[str] = []
    for key in DIM_KEYS:
        d = dimensions.get(key)
        if d is None:
            if key == "momentum":
                weaknesses.append("Momentum is N/A (insufficient snapshot history).")
            else:
                weaknesses.append(f"{key} is N/A.")
            continue
        if d >= 14:
            strengths.append(f"{key} {d}/20")
        elif d <= 8:
            weaknesses.append(f"{key} {d}/20")
    risks = [item.detail for item in evidence if item.polarity == "-"][:4]
    if not strengths:
        strengths.append(_FOCUS[name][1] + " — no strong dimension yet.")
    if not weaknesses:
        weaknesses.append("No dominant weakness on filled dimensions.")
    if not risks:
        risks.append("History still thin; treat as provisional if v7 is missing.")
    return strengths, weaknesses, risks


def run_one_reviewer(
    name: ReviewerName,
    dimensions: dict[str, int | None],
    weights: ReviewerWeightSettings,
    evidence: list[EvidenceItem],
) -> ReviewerResult:
    w = weights.as_dict()
    score = reviewer_score(dimensions, w)
    strengths, weaknesses, risks = _strengths_weaknesses(name, dimensions, evidence)
    return ReviewerResult(
        reviewer=name,
        score=score,
        dimensions=dict(dimensions),
        confidence=_confidence(dimensions),
        evidence=list(evidence),
        strengths=strengths,
        weaknesses=weaknesses,
        risks=risks,
        recommendation=_recommendation(score, dimensions),
        weights=w,
    )


def run_three_reviewers(
    dimensions: dict[str, int | None],
    evidence: list[EvidenceItem],
    settings: BoardSettings,
) -> tuple[ReviewerResult, ReviewerResult, ReviewerResult]:
    """Independent reviewers; executed in parallel threads."""

    def _trend() -> ReviewerResult:
        return run_one_reviewer("trend", dimensions, settings.trend, evidence)

    def _community() -> ReviewerResult:
        return run_one_reviewer("community", dimensions, settings.community, evidence)

    def _contributor() -> ReviewerResult:
        return run_one_reviewer(
            "contributor", dimensions, settings.contributor, evidence
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_t = pool.submit(_trend)
        f_c = pool.submit(_community)
        f_k = pool.submit(_contributor)
        return f_t.result(), f_c.result(), f_k.result()
