"""S1 Preview: Earlyness × Evidence × Opportunity Window.

v2 only. Stars are a weak observation, never a band, bonus, or veto.
Activity Momentum is not star growth. UNKNOWN is omitted, not 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.activity import ActivityResult, compute_activity
from foreshadow.pipeline.features import clip, clip01

Stage = Literal[
    "EXPERIMENTAL",
    "VALIDATED_EARLY",
    "EMERGING",
    "BREAKOUT",
    "SCALING",
    "MATURE",
    "ESTABLISHED",
    "STAGNANT",
]
Pool = Literal["main", "experimental"]
Quadrant = Literal["gold", "too_early", "mature_success", "weak"]

EXPERIMENTAL_EVIDENCE_FLOOR = 24.0
EXPERIMENTAL_WINDOW_CAP = 32.0
STAGNANT_WINDOW_CAP = 22.0


@dataclass
class S1Result:
    earlyness: float | None
    evidence: float | None
    window: float | None
    stage: Stage
    pool: Pool
    quadrant: Quadrant
    confidence: Literal["low", "medium", "high"]
    earlyness_plus: list[str] = field(default_factory=list)
    earlyness_minus: list[str] = field(default_factory=list)
    evidence_plus: list[str] = field(default_factory=list)
    evidence_minus: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    why: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "earlyness": self.earlyness,
            "evidence": self.evidence,
            "opportunity_window": self.window,
            "stage": self.stage,
            "pool": self.pool,
            "quadrant": self.quadrant,
            "confidence": self.confidence,
            "earlyness_plus": list(self.earlyness_plus),
            "earlyness_minus": list(self.earlyness_minus),
            "evidence_plus": list(self.evidence_plus),
            "evidence_minus": list(self.evidence_minus),
            "missing": list(self.missing),
            "why": self.why,
            "note": "Stars are a scale proxy, not a band and not a veto.",
        }


def compute_s1(
    *,
    age_days: float | None,
    contributors: int | None,
    stars: float | None,
    pushed_age_days: int | None,
    unique_issue_authors: int | None,
    feat: FeaturesBlob | None,
    activity: ActivityResult | None = None,
) -> S1Result:
    feat = feat or FeaturesBlob()
    activity = activity or compute_activity(feat)
    missing: list[str] = []
    e_plus: list[str] = []
    e_minus: list[str] = []
    v_plus: list[str] = []
    v_minus: list[str] = []

    earlyness, em = _earlyness(
        age_days,
        contributors,
        pushed_age_days,
        feat,
        activity,
        e_plus,
        e_minus,
        missing,
    )
    evidence, vm = _evidence(
        stars,
        contributors,
        unique_issue_authors,
        feat,
        activity,
        v_plus,
        v_minus,
        missing,
    )
    missing = list(dict.fromkeys(missing + em + vm))
    access01 = _access01(feat, contributors)
    window = _window(earlyness, evidence, access01)
    pool, stage, quadrant = _classify(
        earlyness,
        evidence,
        activity,
        age_days,
        pushed_age_days,
        contributors,
        window,
    )
    if pool == "experimental" and window is not None:
        window = min(window, EXPERIMENTAL_WINDOW_CAP)
    if stage == "STAGNANT" and window is not None:
        window = min(window, STAGNANT_WINDOW_CAP)
    n_known = sum(x is not None for x in (earlyness, evidence, window, activity.momentum))
    if n_known >= 3:
        conf: Literal["low", "medium", "high"] = "high"
    elif n_known >= 1:
        conf = "medium"
    else:
        conf = "low"
    why = (
        f"s1 opportunity_window stage={stage} pool={pool} quadrant={quadrant} "
        f"earlyness={earlyness} evidence={evidence} window={window} "
        f"(stars are not a band; replaces entry_window)"
    )
    return S1Result(
        earlyness=None if earlyness is None else round(earlyness, 4),
        evidence=None if evidence is None else round(evidence, 4),
        window=None if window is None else round(window, 4),
        stage=stage,
        pool=pool,
        quadrant=quadrant,
        confidence=conf,
        earlyness_plus=e_plus,
        earlyness_minus=e_minus,
        evidence_plus=v_plus,
        evidence_minus=v_minus,
        missing=missing,
        why=why,
    )


def _pts(weight: float, unit: float) -> float:
    return float(weight) * clip01(unit)


def _earlyness(
    age_days: float | None,
    c: int | None,
    pushed_age: int | None,
    feat: FeaturesBlob,
    activity: ActivityResult,
    plus: list[str],
    minus: list[str],
    missing: list[str],
) -> tuple[float | None, list[str]]:
    total = 0.0
    used = 0.0
    if age_days is None:
        missing.append("age_days")
    else:
        # 45d ≈ 1.0; ~2y ≈ 0. Youth is calendar age, not stars.
        youth = 1.0 - clip01((float(age_days) - 45.0) / 700.0)
        total += _pts(30, youth)
        used += 30
        if youth >= 0.7:
            plus.append(f"仓库仍年轻（{int(age_days)} 天）")
        elif youth <= 0.25:
            minus.append(f"仓库已较老（{int(age_days)} 天）")
    if c is None:
        missing.append("C")
    else:
        room = clip01((30.0 - float(c)) / 30.0)
        total += _pts(30, room)
        used += 30
        if room >= 0.55:
            plus.append(f"贡献者尚未拥挤（C={c}）")
        elif room <= 0.2:
            minus.append(f"贡献者已较多（C={c}）")
    acc = _access01(feat, c)
    if acc is None:
        missing.append("access")
    else:
        total += _pts(20, acc)
        used += 20
        if acc >= 0.5:
            plus.append("外部贡献仍相对可进入")
        elif acc <= 0.15:
            minus.append("外部贡献进入较难")
    living, live_note = _living01(activity, pushed_age)
    if living is None:
        missing.append("activity_or_push")
    else:
        total += _pts(20, living)
        used += 20
        plus.append(live_note) if living >= 0.5 else minus.append(live_note)
    if used <= 0:
        return None, missing
    return clip(total, 0, 100), missing


def _living01(
    activity: ActivityResult, pushed_age: int | None
) -> tuple[float | None, str]:
    if activity.momentum is not None:
        unit = clip01(activity.momentum / 100.0)
        label = f"近期持续活跃度 {activity.classification or 'NA'}"
        return unit, label
    if pushed_age is None:
        return None, "活跃度未知"
    if pushed_age <= 14:
        return 0.35, "仅有最近 push，缺少持续活跃证据"
    if pushed_age > 90:
        return 0.05, "长期缺少 push"
    return 0.15, "push 较旧且无 Activity 样本"


def _access01(feat: FeaturesBlob, c: int | None) -> float | None:
    bits: list[float] = []
    if feat.pr_accept_rate is not None:
        bits.append(clip01(float(feat.pr_accept_rate)))
    if feat.unassigned_help is not None:
        bits.append(clip01(float(feat.unassigned_help) / 4.0))
    if feat.maint_touch is not None:
        bits.append(clip01(float(feat.maint_touch)))
    if not bits and c is not None:
        bits.append(clip01((40.0 - float(c)) / 40.0))
    if not bits:
        return None
    return sum(bits) / len(bits)


def _evidence(
    stars: float | None,
    c: int | None,
    u_issue: int | None,
    feat: FeaturesBlob,
    activity: ActivityResult,
    plus: list[str],
    minus: list[str],
    missing: list[str],
) -> tuple[float | None, list[str]]:
    total = 0.0
    used = 0.0
    # Stars are a WEAK usage proxy (4 pts max). Never renormalized to 100.
    if stars is None:
        missing.append("S")
    else:
        star_u = clip01((_log10(float(stars) + 1.0)) / 4.0)
        total += _pts(4, star_u)
        used += 4
        if stars >= 200:
            plus.append(f"已有一定关注（{int(stars)}★，弱证据）")
    if c is None:
        missing.append("C")
    else:
        total += _pts(18, clip01(float(c) / 12.0))
        used += 18
        if c >= 4:
            plus.append(f"多名贡献者（C={c}）")
        elif c <= 1:
            minus.append("贡献者很少")
    issues = u_issue
    if issues is None and feat.issue_sample_n is not None:
        issues = feat.issue_sample_n
    if issues is None:
        missing.append("issues")
    else:
        total += _pts(16, clip01(float(issues) / 8.0))
        used += 16
        if issues >= 3:
            plus.append(f"有真实 issue 信号（{issues}）")
        else:
            minus.append("issue 证据弱")
    if activity.momentum is None:
        missing.append("activity_momentum")
    else:
        total += _pts(18, clip01(activity.momentum / 100.0))
        used += 18
        if activity.momentum >= 55:
            plus.append(f"Activity Momentum {activity.classification}")
        elif activity.momentum < 20:
            minus.append("Activity Momentum 很低（不是 Star 增长）")
    if feat.releases_30d is None:
        missing.append("releases_30d")
    else:
        total += _pts(12, clip01(float(feat.releases_30d) / 2.0))
        used += 12
        if feat.releases_30d >= 1:
            plus.append(f"近 30 天有 Release（{feat.releases_30d}）")
    if activity.recent_contributors_7d is None:
        missing.append("recent_contributors_7d")
    else:
        total += _pts(12, clip01(float(activity.recent_contributors_7d) / 4.0))
        used += 12
        if activity.recent_contributors_7d >= 3:
            plus.append("近 7 天贡献者多样")
        elif activity.recent_contributors_7d <= 1:
            minus.append("近 7 天几乎只有单一作者")
    if feat.maint_touch is None:
        missing.append("maint_touch")
    else:
        total += _pts(12, clip01(float(feat.maint_touch)))
        used += 12
        if feat.maint_touch >= 0.4:
            plus.append("维护者有响应")
        elif feat.maint_touch <= 0.05:
            minus.append("维护者响应弱")
    if feat.pr_accept_rate is None:
        missing.append("pr_accept_rate")
    else:
        total += _pts(8, clip01(float(feat.pr_accept_rate)))
        used += 8
        if feat.pr_accept_rate > 0:
            plus.append("观察到外部 PR 被接受")
    if used <= 0:
        return None, missing
    return clip(total, 0, 100), missing


def _window(
    earlyness: float | None,
    evidence: float | None,
    access01: float | None,
) -> float | None:
    if earlyness is None and evidence is None:
        return None
    if earlyness is None or evidence is None:
        known = earlyness if earlyness is not None else evidence
        base = 0.45 * (known / 100.0)
    else:
        # Gold needs BOTH. Product, not a star band.
        base = 0.75 * sqrt((earlyness / 100.0) * (evidence / 100.0))
    acc = 0.25 * access01 if access01 is not None else 0.0
    return clip(100.0 * (base + acc), 0, 100)


def _classify(
    earlyness: float | None,
    evidence: float | None,
    activity: ActivityResult,
    age_days: float | None,
    pushed_age: int | None,
    c: int | None,
    window: float | None,
) -> tuple[Pool, Stage, Quadrant]:
    ev = evidence
    er = earlyness
    am = activity.classification
    stale_push = pushed_age is not None and pushed_age > 90
    old = age_days is not None and age_days >= 400
    low_am = am in {"VERY_LOW", "LOW"}
    if old and (low_am or (activity.momentum is None and stale_push)):
        quad: Quadrant = "weak"
        return "main", "STAGNANT", quad
    validated = ev is not None and ev >= EXPERIMENTAL_EVIDENCE_FLOOR
    young_thin = (
        age_days is not None
        and age_days <= 21
        and (ev is None or ev < EXPERIMENTAL_EVIDENCE_FLOOR)
        and (activity.momentum is None or activity.momentum < 40)
    )
    toy = (
        ev is not None
        and ev < 18
        and (activity.momentum is None or activity.momentum < 25)
        and (c is None or c <= 2)
        and (age_days is None or age_days <= 90)
    )
    experimental = (not validated) and (young_thin or toy)
    if experimental:
        quad = "too_early" if (er or 0) >= 50 else "weak"
        return "experimental", "EXPERIMENTAL", quad
    high_e = er is not None and er >= 50
    high_v = ev is not None and ev >= 40
    if high_e and high_v:
        quad = "gold"
    elif high_e:
        quad = "too_early"
    elif high_v:
        quad = "mature_success"
    else:
        quad = "weak"
    am_hot = am in {"HIGH", "VERY_HIGH"}
    if high_v and high_e and am_hot:
        return "main", "BREAKOUT", quad
    if high_e and validated:
        return "main", "VALIDATED_EARLY", quad
    if (ev or 0) >= 40 and (er or 0) >= 40:
        return "main", "EMERGING", quad
    if (ev or 0) >= 50 and er is not None and 25 <= er < 50:
        return "main", "SCALING", quad
    if er is not None and er < 30:
        if c is not None and c >= 40:
            return "main", "ESTABLISHED", quad
        if (ev or 0) >= 20:
            return "main", "MATURE", quad
    if validated and high_e:
        return "main", "VALIDATED_EARLY", quad
    if validated:
        return "main", "EMERGING", quad
    if (er or 0) >= 50:
        return "main", "EXPERIMENTAL", "too_early"
    return "main", "EMERGING", quad


def _log10(x: float) -> float:
    from math import log10

    return log10(max(x, 1e-9))
