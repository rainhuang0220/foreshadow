"""S2 Community Access. Separate from Contributor Gap. NA is omitted, not 0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.features import clip, clip01

AccessClass = Literal["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"]


@dataclass
class AccessResult:
    score: float | None
    classification: AccessClass | None
    confidence: Literal["low", "medium", "high"]
    merge_rate: float | None
    review_rate: float | None
    external_merged_n: int | None
    merged_sample_n: int | None
    reviewed_n: int | None
    maint_touch: float | None
    maint_hours: float | None
    missing: list[str] = field(default_factory=list)
    why: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "class": self.classification,
            "confidence": self.confidence,
            "merge_rate": self.merge_rate,
            "review_rate": self.review_rate,
            "external_merged_n": self.external_merged_n,
            "merged_sample_n": self.merged_sample_n,
            "reviewed_n": self.reviewed_n,
            "maint_touch": self.maint_touch,
            "maint_hours": self.maint_hours,
            "missing": list(self.missing),
            "why": self.why,
            "note": "Access is not Contributor Gap. UNKNOWN is not 0.",
        }


def classify_access(score: float | None) -> AccessClass | None:
    if score is None:
        return None
    if score < 15:
        return "VERY_LOW"
    if score < 35:
        return "LOW"
    if score < 55:
        return "MEDIUM"
    if score < 75:
        return "HIGH"
    return "VERY_HIGH"


def compute_access(feat: FeaturesBlob | None) -> AccessResult:
    feat = feat or FeaturesBlob()
    missing: list[str] = []
    merge = feat.pr_accept_rate
    n = feat.pr_merged_sample_n
    ext = feat.pr_external_merged_n
    reviewed = feat.pr_reviewed_n
    review_rate = feat.pr_review_rate
    if n is None:
        missing.append("pr_merged_sample")
    if merge is None:
        missing.append("pr_accept_rate")
    if review_rate is None:
        missing.append("pr_review_rate")
    if feat.maint_touch is None:
        missing.append("maint_touch")
    if feat.maint_first_response_hours is None:
        missing.append("maint_hours")

    total = 0.0
    used = 0.0
    if merge is not None:
        total += 30.0 * clip01(float(merge))
        used += 30.0
    if review_rate is not None:
        total += 20.0 * clip01(float(review_rate))
        used += 20.0
    if feat.maint_touch is not None:
        total += 20.0 * clip01(float(feat.maint_touch))
        used += 20.0
    if feat.maint_first_response_hours is not None:
        hours = max(float(feat.maint_first_response_hours), 0.0)
        total += 15.0 * clip01(1.0 - hours / 72.0)
        used += 15.0
    onboard = _onboard01(feat)
    if onboard is not None:
        total += 15.0 * onboard
        used += 15.0
    else:
        missing.append("onboarding")

    if used <= 0:
        return AccessResult(
            score=None,
            classification=None,
            confidence="low",
            merge_rate=merge,
            review_rate=review_rate,
            external_merged_n=ext,
            merged_sample_n=n,
            reviewed_n=reviewed,
            maint_touch=feat.maint_touch,
            maint_hours=feat.maint_first_response_hours,
            missing=missing,
            why="UNKNOWN (no access sample); not 0",
        )
    score = clip(total, 0, 100)
    n_known = 5 - len(
        [m for m in missing if m in {"pr_accept_rate", "pr_review_rate", "maint_touch", "maint_hours", "onboarding"}]
    )
    conf: Literal["low", "medium", "high"]
    if n_known >= 4:
        conf = "high"
    elif n_known >= 2:
        conf = "medium"
    else:
        conf = "low"
    return AccessResult(
        score=round(score, 4),
        classification=classify_access(score),
        confidence=conf,
        merge_rate=merge,
        review_rate=review_rate,
        external_merged_n=ext,
        merged_sample_n=n,
        reviewed_n=reviewed,
        maint_touch=feat.maint_touch,
        maint_hours=feat.maint_first_response_hours,
        missing=missing,
        why=(
            f"access merge={merge} review={review_rate} "
            f"maint_touch={feat.maint_touch} hours={feat.maint_first_response_hours} "
            f"(gap is separate; not 0-fill)"
        ),
    )


def _onboard01(feat: FeaturesBlob) -> float | None:
    bits: list[float] = []
    if feat.gap_docs is not None:
        bits.append(0.0 if feat.gap_docs else 1.0)
    if feat.unassigned_help is not None:
        bits.append(clip01(float(feat.unassigned_help) / 3.0))
    if feat.help_n is not None:
        bits.append(clip01(float(feat.help_n) / 4.0))
    if feat.has_workflows is not None:
        bits.append(1.0 if feat.has_workflows else 0.3)
    if not bits:
        return None
    return sum(bits) / len(bits)
