"""Project intelligence scores. Independent of v1 Official Top 5 mix."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from foreshadow.models import ComponentScore, FeaturesBlob
from foreshadow.pipeline.creator import compute_creator_prior
from foreshadow.pipeline.features import clip01
from foreshadow.pipeline.openness import compute_openness
from foreshadow.pipeline.star_trust import star_trust as star_trust_of

FORMULA_VERSION = "intel-v1.1"
EPS = 1e-6
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
# Ranking-only stand-in when Openness is NA. Displayed Openness stays NA.
# 22 < 25 so missing cannot beat a known-low 25 on the same Potential/Entry Fit;
# 22 > 5 so missing is not treated as catastrophic.
OPEN_UNKNOWN_RANK = 22.0


@dataclass
class IntelScores:
    potential: ComponentScore
    creator_prior: ComponentScore
    openness: ComponentScore
    entry_fit: ComponentScore
    eev: ComponentScore
    snapshot_count: int
    prior_weight: float
    decision: str
    high_confidence: bool
    formula_version: str = FORMULA_VERSION
    eev_coverage: str | None = None
    openness_unknown: bool = False
    openness_sample_n: int | None = None
    openness_stats: dict[str, Any] = field(default_factory=dict)
    creator_stats: dict[str, Any] = field(default_factory=dict)
    why: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "potential": self.potential.value,
            "creator_prior": self.creator_prior.value,
            "openness": self.openness.value,
            "entry_fit": self.entry_fit.value,
            "eev": self.eev.value,
            "potential_confidence": self.potential.confidence,
            "creator_confidence": self.creator_prior.confidence,
            "openness_confidence": self.openness.confidence,
            "entry_fit_confidence": self.entry_fit.confidence,
            "eev_confidence": self.eev.confidence,
            "openness_sample_n": self.openness_sample_n,
            "snapshot_count": self.snapshot_count,
            "prior_weight": self.prior_weight,
            "decision": self.decision,
            "intel_decision": self.decision,
            "high_confidence": self.high_confidence,
            "intel_high_confidence": self.high_confidence,
            "formula_version": self.formula_version,
            "eev_coverage": self.eev_coverage,
            "openness_unknown": self.openness_unknown,
            "openness_stats": self.openness_stats,
            "creator_stats": self.creator_stats,
            "why": self.why,
        }

    def model_dump(self) -> dict[str, Any]:
        return self.as_dict()


def geomean(values: Sequence[float | None]) -> float | None:
    known = [max(float(v), EPS) for v in values if v is not None]
    if not known:
        return None
    return math.exp(sum(math.log(v) for v in known) / len(known))


def score_intel(
    feat: FeaturesBlob | Mapping[str, Any] | None = None,
    snapshot_count: int | None = None,
    *,
    windows_v7: float | None = None,
    rel_growth_7d: float | None = None,
    stars: int | None = None,
    forks: int | None = None,
    open_issues: int | None = None,
    contributors: int | None = None,
    pushed_age_days: int | None = None,
    direction_fit: float | None = None,
    contribution_opp: float | None = None,
    strategy_path: str | None = None,
    h_flags: Sequence[str] | None = None,
    owner_payload: Mapping[str, Any] | None = None,
    current_full_name: str = "",
    now=None,
    **_kwargs: Any,
) -> IntelScores:
    extra: dict[str, Any] = {}
    payload = feat
    if isinstance(payload, Mapping):
        extra = dict(payload)
        nested = extra.get("features")
        if isinstance(nested, Mapping):
            feat = nested
        if snapshot_count is None:
            snapshot_count = _int(extra.get("snapshot_count"))
        stars = _first(stars, extra.get("stars"), extra.get("S"))
        forks = _first(forks, extra.get("forks"), extra.get("F"))
        open_issues = _first(open_issues, extra.get("open_issues"), extra.get("I_open"))
        contributors = _first(contributors, extra.get("contributors"), extra.get("C"))
        pushed_age_days = _first(pushed_age_days, extra.get("pushed_age_days"))
        direction_fit = _first(direction_fit, extra.get("direction_fit"))
        contribution_opp = _first(contribution_opp, extra.get("contribution_opp"))
        strategy_path = strategy_path or extra.get("strategy_path")
        windows = (
            extra.get("windows") if isinstance(extra.get("windows"), Mapping) else {}
        )
        windows_v7 = _first(windows_v7, extra.get("v7"), windows.get("v7"))
        rel_growth_7d = _first(
            rel_growth_7d, extra.get("rel_growth_7d"), windows.get("rel_growth_7d")
        )
        if owner_payload is None and isinstance(extra.get("owner"), Mapping):
            owner_payload = extra.get("owner")
        if owner_payload is None and isinstance(extra.get("owner_payload"), Mapping):
            owner_payload = extra.get("owner_payload")
        current_full_name = current_full_name or str(extra.get("full_name") or "")
        if h_flags is None:
            raw_flags = extra.get("h_flags") or extra.get("flags")
            if isinstance(raw_flags, list):
                h_flags = [str(x) for x in raw_flags]

    n_snap = int(snapshot_count or 0)
    w = 1.0 / (1.0 + max(n_snap, 0))
    blob = _as_feat(feat)
    feat_obj: FeaturesBlob | Mapping[str, Any] | None = (
        blob if blob is not None else feat if isinstance(feat, Mapping) else None
    )

    openness = compute_openness(feat_obj)
    creator = compute_creator_prior(
        owner_payload,
        current_full_name=current_full_name,
        now=_now(now),
        feat=feat_obj,
    )
    potential, pot_conf, pot_missing, pot_why = _potential(
        feat=feat_obj,
        extra=extra,
        windows_v7=windows_v7,
        rel_growth_7d=rel_growth_7d,
        stars=stars,
        forks=forks,
        open_issues=open_issues,
        contributors=contributors,
        pushed_age_days=pushed_age_days,
        h_flags=h_flags,
    )
    entry, entry_conf, entry_missing, entry_why = _entry_fit(
        direction_fit=direction_fit,
        contribution_opp=contribution_opp,
        strategy_path=strategy_path,
        extra=extra,
    )
    eev, eev_conf, eev_missing, eev_why = _eev(
        potential=potential,
        openness=openness.score,
        entry_fit=entry,
        creator=creator.score,
        prior_weight=w,
        pot_conf=pot_conf,
        open_conf=openness.confidence if openness.score is not None else None,
        entry_conf=entry_conf,
    )
    open_known = openness.score is not None
    high = (
        eev is not None
        and eev_conf == "high"
        and open_known
        and potential is not None
        and entry is not None
    )
    decision = _decision(eev, eev_conf)
    pot_cs = _component(potential, pot_conf, pot_missing, pot_why)
    open_cs = _component(
        openness.score,
        openness.confidence if openness.score is not None else "low",
        [] if openness.score is not None else ["pr_external_closed_n"],
        openness.why,
    )
    entry_cs = _component(entry, entry_conf, entry_missing, entry_why)
    creator_cs = _component(
        creator.score,
        creator.confidence if creator.score is not None else "low",
        [] if creator.score is not None else ["owner_repos"],
        creator.why,
        weight=w,
    )
    eev_cs = _component(eev, eev_conf, eev_missing, eev_why)
    return IntelScores(
        potential=pot_cs,
        creator_prior=creator_cs,
        openness=open_cs,
        entry_fit=entry_cs,
        eev=eev_cs,
        snapshot_count=n_snap,
        prior_weight=w,
        decision=decision,
        high_confidence=high,
        eev_coverage=_coverage(potential, entry, openness.score),
        openness_unknown=openness.score is None,
        openness_sample_n=openness.sample_n if openness.sample_n else None,
        openness_stats=dict(openness.stats),
        creator_stats=dict(creator.stats),
        why={
            "potential": pot_why,
            "openness": openness.why,
            "creator": creator.why,
            "entry_fit": entry_why,
            "eev": eev_why,
        },
    )


def _potential(
    *,
    feat: FeaturesBlob | Mapping[str, Any] | None,
    extra: Mapping[str, Any],
    windows_v7: float | None,
    rel_growth_7d: float | None,
    stars: int | None,
    forks: int | None,
    open_issues: int | None,
    contributors: int | None,
    pushed_age_days: int | None,
    h_flags: Sequence[str] | None,
) -> tuple[float | None, str, list[str], str]:
    get = _getter(feat)
    missing: list[str] = []
    commits_30 = _first(_int(get("commits_30d")), _int(extra.get("commits_30d")))
    contrib7 = _first(
        _int(get("recent_contributors_7d")), _int(extra.get("recent_contributors_7d"))
    )
    rel30 = _first(_int(get("releases_30d")), _int(extra.get("releases_30d")))
    activity_bits: list[float] = []
    if commits_30 is None:
        missing.append("commits_30d")
    else:
        activity_bits.append(clip01(commits_30 / 30.0))
    if contrib7 is None:
        missing.append("recent_contributors_7d")
    else:
        activity_bits.append(clip01(contrib7 / 4.0))
    if rel30 is None:
        missing.append("releases_30d")
    else:
        activity_bits.append(clip01(rel30 / 2.0))
    activity_01 = geomean(activity_bits) if activity_bits else None

    trust = star_trust_of(
        stars,
        forks=forks,
        open_issues=open_issues,
        contributors=contributors,
        v7=windows_v7,
        v30=_float(extra.get("v30")) if extra else None,
        h_flags=h_flags,
    )
    growth_01 = None
    if rel_growth_7d is not None:
        growth_01 = clip01(rel_growth_7d) * trust
    else:
        missing.append("rel_growth_7d")

    pushed = pushed_age_days
    if pushed is None:
        pushed = _int(extra.get("pushed_age_days"))
    maint_01 = None
    if pushed is None:
        missing.append("pushed_age_days")
    elif pushed <= 14:
        maint_01 = 1.0
    elif pushed <= 45:
        maint_01 = 0.6
    elif pushed <= 120:
        maint_01 = 0.2
    else:
        maint_01 = 0.05

    gm = geomean([activity_01, growth_01, maint_01])
    if gm is None:
        return None, "low", missing, "NA (no activity/growth/maintenance evidence)"
    n_known = sum(v is not None for v in (activity_01, growth_01, maint_01))
    if n_known >= 3:
        conf = "high"
    elif n_known == 2:
        conf = "medium"
    else:
        conf = "low"
    return (
        100.0 * gm,
        conf,
        missing,
        "geomean of activity, damped growth, maintenance",
    )


def _entry_fit(
    *,
    direction_fit: float | None,
    contribution_opp: float | None,
    strategy_path: str | None,
    extra: Mapping[str, Any],
) -> tuple[float | None, str, list[str], str]:
    missing: list[str] = []
    direction_01 = None
    if direction_fit is None:
        missing.append("direction_fit")
    else:
        direction_01 = clip01(float(direction_fit) / 100.0)
    contrib_01 = None
    if contribution_opp is None:
        missing.append("contribution_opp")
    else:
        contrib_01 = clip01(float(contribution_opp) / 100.0)
    path = (strategy_path or "") or str(extra.get("strategy_path") or "")
    path_01 = _path_01(path)
    if path_01 is None:
        missing.append("strategy_path")
    gm = geomean([direction_01, contrib_01, path_01])
    if gm is None:
        return None, "low", missing, "NA (no direction/contribution/path)"
    known = sum(v is not None for v in (direction_01, contrib_01, path_01))
    conf = "high" if known >= 2 else "medium"
    return 100.0 * gm, conf, missing, "geomean of direction, contribution, path"


def _path_01(strategy_path: str) -> float | None:
    if not strategy_path or not str(strategy_path).strip():
        return None
    raw = str(strategy_path).strip().lower().replace("_", "-").replace(" ", "-")
    if raw in {"issue", "discussion", "repro", "reproduction"}:
        return 0.8
    if raw.startswith(("issue", "discussion", "repro")):
        return 0.8
    if raw in {"pr", "pr-first", "prfirst"} or "pr-first" in raw:
        return 0.4
    return None


def _eev(
    *,
    potential: float | None,
    openness: float | None,
    entry_fit: float | None,
    creator: float | None,
    prior_weight: float,
    pot_conf: str | None,
    open_conf: str | None,
    entry_conf: str | None,
) -> tuple[float | None, str, list[str], str]:
    """Expected Entry Value for display and homepage rank.

    Mandatory axes: Potential and Entry Fit. Either missing → EEV NA.
    Openness is an evidence modifier. Known Openness enters the geomean.
    Unknown Openness does **not** drop out (that rewarded missingness).
    It is replaced for ranking only by OPEN_UNKNOWN_RANK. Displayed
    Openness stays NA. Unknown is worse than a known 25 and better than
    a known 5 on otherwise identical cores.
    Creator prior is optional and omitted when unknown.
    """
    missing: list[str] = []
    if potential is None:
        missing.append("potential")
    if entry_fit is None:
        missing.append("entry_fit")
    if missing:
        if openness is None:
            missing.append("openness")
        return (
            None,
            "low",
            missing,
            "EEV NA (Potential and Entry Fit are mandatory)",
        )
    factors = [clip01(potential / 100.0), clip01(entry_fit / 100.0)]
    confs: list[str | None] = [pot_conf, entry_conf]
    if openness is not None:
        factors.append(clip01(openness / 100.0))
        confs.append(open_conf)
        why_open = f"openness={openness:.1f}"
    else:
        factors.append(clip01(OPEN_UNKNOWN_RANK / 100.0))
        confs.append("low")
        why_open = f"openness=NA rank_as={OPEN_UNKNOWN_RANK:.0f}"
        missing.append("openness")
    core_gm = geomean(factors)
    if core_gm is None:
        return None, "low", missing, "EEV NA"
    w = min(float(prior_weight), 0.5)
    if creator is not None and w > EPS:
        mixed = math.exp(
            (1.0 - w) * math.log(max(core_gm, EPS))
            + w * math.log(max(clip01(creator / 100.0), EPS))
        )
        why = f"EEV core={core_gm:.4f} {why_open} prior w={w:.4f}"
    else:
        mixed = core_gm
        why = f"EEV core={core_gm:.4f} {why_open} prior omitted"
    if openness is None:
        conf = "low"
    else:
        ranks = [CONF_RANK.get(c or "low", 0) for c in confs]
        floor = min(ranks) if ranks else 0
        if floor >= 2:
            conf = "high"
        elif floor >= 1:
            conf = "medium"
        else:
            conf = "low"
    return 100.0 * mixed, conf, missing, why


def _coverage(
    potential: float | None, entry_fit: float | None, openness: float | None
) -> str:
    known = sum(v is not None for v in (potential, entry_fit, openness))
    return f"{known}/3"


def _decision(eev: float | None, conf: str | None) -> str:
    if eev is None:
        return "数据不足"
    if eev >= 70 and (conf or "low") in {"medium", "high"}:
        return "值得进入"
    if eev >= 40:
        return "继续观察"
    return "暂不进入"


def _component(
    value: float | None,
    confidence: str | None,
    missing: list[str],
    why: str,
    *,
    weight: float | None = None,
) -> ComponentScore:
    conf = confidence if confidence in {"low", "medium", "high"} else "low"
    if not isinstance(why, str):
        why = (
            "; ".join(str(x) for x in why) if isinstance(why, list) else str(why or "")
        )
    if not isinstance(missing, list):
        missing = []
    return ComponentScore(
        value=None if value is None else round(float(value), 4),
        confidence=conf,
        missing=list(missing),
        why=why,
        weight=weight,
    )


def _as_feat(feat: FeaturesBlob | Mapping[str, Any] | None) -> FeaturesBlob | None:
    if feat is None:
        return None
    if isinstance(feat, FeaturesBlob):
        return feat
    try:
        return FeaturesBlob.model_validate(feat)
    except (TypeError, ValueError):
        return None


def _getter(feat: FeaturesBlob | Mapping[str, Any] | None):
    if feat is None:
        return lambda k, d=None: d
    if isinstance(feat, Mapping):
        return lambda k, d=None: feat.get(k, d)
    return lambda k, d=None: getattr(feat, k, d)


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    now_fn = getattr(value, "now", None)
    if callable(now_fn):
        stamp = now_fn()
        if isinstance(stamp, datetime):
            return _now(stamp)
    return datetime.now(UTC)
