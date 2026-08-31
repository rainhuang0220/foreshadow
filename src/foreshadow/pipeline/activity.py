"""Activity Momentum for v2 Preview. Not star growth. Not windows.v7.

High score = recent density + 30d persistence + contributor diversity + releases.
A single same-day push is not high activity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from foreshadow.config import ScoringSettings
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.features import clip01

ActivityClass = Literal["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
ActivityConfidence = Literal["low", "medium", "high"]

ACTIVITY_NOTE = "Activity reflects development and community work, not star growth."


@dataclass(frozen=True)
class ActivityResult:
    momentum: float | None
    classification: ActivityClass | None
    concentration: float | None
    confidence: ActivityConfidence
    commits_7d: int | None
    commits_30d: int | None
    releases_30d: int | None
    recent_contributors_7d: int | None
    missing: list[str]
    why: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "momentum": self.momentum,
            "class": self.classification,
            "concentration": self.concentration,
            "confidence": self.confidence,
            "commits_7d": self.commits_7d,
            "commits_30d": self.commits_30d,
            "releases_30d": self.releases_30d,
            "recent_contributors_7d": self.recent_contributors_7d,
            "missing": list(self.missing),
            "note": ACTIVITY_NOTE,
            "why": self.why,
        }


def activity_concentration(
    commits_7d: int | None, commits_30d: int | None
) -> float | None:
    """Share of 30d commits that landed in 7d. Not acceleration. Not star growth."""
    if commits_7d is None or commits_30d is None:
        return None
    return float(commits_7d) / float(max(commits_30d, 1))


def classify_activity(momentum: float | None) -> ActivityClass | None:
    if momentum is None:
        return None
    if momentum < 15:
        return "VERY_LOW"
    if momentum < 35:
        return "LOW"
    if momentum < 55:
        return "MEDIUM"
    if momentum < 75:
        return "HIGH"
    return "VERY_HIGH"


def compute_activity(
    feat: FeaturesBlob | Mapping | None,
    scoring: ScoringSettings | None = None,
) -> ActivityResult:
    scoring = scoring or ScoringSettings()
    c7, c30, rel, contrib = _read_counts(feat)
    missing: list[str] = []
    if c7 is None:
        missing.append("commits_7d")
    if c30 is None:
        missing.append("commits_30d")
    if contrib is None:
        missing.append("recent_contributors_7d")
    if rel is None:
        missing.append("releases_30d")
    conc = activity_concentration(c7, c30)

    if c30 is None:
        return ActivityResult(
            momentum=None,
            classification=None,
            concentration=conc,
            confidence="low",
            commits_7d=c7,
            commits_30d=c30,
            releases_30d=rel,
            recent_contributors_7d=contrib,
            missing=missing,
            why="UNKNOWN (commits_30d missing); not 0",
        )

    terms: list[tuple[float, float, str]] = []
    w7 = float(scoring.activity_commit_7d_weight)
    w30 = float(scoring.activity_commit_30d_weight)
    wc = float(scoring.activity_contributor_weight)
    wr = float(scoring.activity_release_weight)
    if c7 is not None:
        terms.append(
            (w7, clip01(c7 / max(float(scoring.activity_sat_commits_7d), 1.0)), "7d")
        )
    if c30 is not None:
        terms.append(
            (
                w30,
                clip01(c30 / max(float(scoring.activity_sat_commits_30d), 1.0)),
                "30d",
            )
        )
    if contrib is not None:
        terms.append(
            (
                wc,
                clip01(contrib / max(float(scoring.activity_sat_contributors_7d), 1.0)),
                "contrib",
            )
        )
    if rel is not None:
        terms.append(
            (
                wr,
                clip01(rel / max(float(scoring.activity_sat_releases_30d), 1.0)),
                "rel",
            )
        )
    wsum = sum(w for w, _, _ in terms)
    if wsum <= 0:
        return ActivityResult(
            momentum=None,
            classification=None,
            concentration=conc,
            confidence="low",
            commits_7d=c7,
            commits_30d=c30,
            releases_30d=rel,
            recent_contributors_7d=contrib,
            missing=missing,
            why="UNKNOWN (no activity terms); not 0",
        )
    value = 100.0 * sum(w * x for w, x, _ in terms) / wsum
    n_known = 4 - len(missing)
    if n_known >= 4:
        conf: ActivityConfidence = "high"
    elif n_known >= 2:
        conf = "medium"
    else:
        conf = "low"
    why = (
        f"activity_momentum intensity7={c7} persist30={c30} "
        f"contrib7={contrib} releases30={rel} concentration={conc} "
        f"(not star growth)"
    )
    return ActivityResult(
        momentum=round(value, 4),
        classification=classify_activity(value),
        concentration=conc,
        confidence=conf,
        commits_7d=c7,
        commits_30d=c30,
        releases_30d=rel,
        recent_contributors_7d=contrib,
        missing=missing,
        why=why,
    )


def _read_counts(
    feat: FeaturesBlob | Mapping | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    if feat is None:
        return None, None, None, None
    if isinstance(feat, FeaturesBlob):
        return (
            feat.commits_7d,
            feat.commits_30d,
            feat.releases_30d,
            feat.recent_contributors_7d,
        )
    if isinstance(feat, Mapping):
        return (
            _as_int(feat.get("commits_7d")),
            _as_int(feat.get("commits_30d")),
            _as_int(feat.get("releases_30d")),
            _as_int(feat.get("recent_contributors_7d")),
        )
    return None, None, None, None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
