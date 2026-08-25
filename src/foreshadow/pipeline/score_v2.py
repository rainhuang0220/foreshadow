"""Preview Opportunity Engine v2. Official scoring remains score.score_repo (v1).

Does not write activity into windows.v7. Star growth stays UNKNOWN without
local snapshots. NA is omitted from the mix, never filled as 0.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import ScoringSettings
from foreshadow.models import ComponentScore, FeaturesBlob, ScoreBreakdown
from foreshadow.pipeline.features import clip, clip01
from foreshadow.pipeline.h_rules import apply_penalties, evaluate_h
from foreshadow.pipeline.score import (
    ScoredRepo,
    _as_dict,
    _context,
    _direction_fit,
    _exceptional_flag,
    _explosion,
    _features,
    _momentum,
    _opportunity_confidence,
    _real_user,
    mix_opportunity,
)

SCORE_VERSION = "v2"


def score_repo_v2(
    repo: object,
    *,
    clock: Clock | None = None,
    scoring: ScoringSettings | None = None,
    bags: Sequence | Mapping | None = None,
) -> ScoredRepo:
    clock = clock or Clock()
    scoring = scoring or ScoringSettings()
    data = _as_dict(repo)
    feat = _features(data)
    ctx = _context(data, feat, clock, scoring)
    windows = ctx.windows

    momentum, accel_term, size_term = _momentum(ctx, windows, scoring)
    direction = _direction_fit(ctx, feat, bags)
    real_user = _real_user(ctx, feat)
    gap = _gap_access(ctx, feat)
    contribution_opp = _contribution_ixnfa(ctx, feat, direction)
    early_entry = _entry_window(ctx, real_user)
    maintainer = _maintainer_v2(ctx, feat)

    components = {
        "momentum": momentum,
        "real_user": real_user,
        "gap": gap,
        "contribution_opp": contribution_opp,
        "early_entry": early_entry,
        "direction_fit": direction,
        "maintainer": maintainer,
    }
    opportunity = mix_opportunity(components, scoring)
    explosion = _explosion(windows, accel_term, size_term)
    contribution = ComponentScore(
        value=contribution_opp.value,
        confidence=contribution_opp.confidence,
        missing=list(contribution_opp.missing),
        weight=contribution_opp.weight,
        why=contribution_opp.why,
    )

    h = evaluate_h(ctx)
    flags = list(h.fired)
    if windows.is_accelerating:
        flags.append("is_accelerating")
    if ctx.starved:
        flags.append("contributor_starved")
    if ctx.bus:
        flags.append("bus_factor")
    if h.tree_missing:
        flags.append("tree_missing")

    breakdown = ScoreBreakdown(
        opportunity=opportunity,
        explosion=explosion,
        contribution=contribution,
        momentum=momentum,
        real_user=real_user,
        gap=gap,
        contribution_opp=contribution_opp,
        early_entry=early_entry,
        direction_fit=direction,
        maintainer=maintainer,
        flags=flags,
        vetoed=h.vetoed,
        veto_reason=h.veto_reason,
    )
    breakdown = apply_penalties(breakdown, ctx)

    if windows.v7 is None:
        breakdown.explosion = ComponentScore(
            value=None,
            confidence="low",
            missing=["v7"],
            why="NA (insufficient history)",
        )
    elif h.vetoed:
        breakdown.explosion = breakdown.explosion.model_copy(
            update={"value": None, "missing": ["h_veto"]}
        )

    opp_conf = _opportunity_confidence(
        v7=windows.v7,
        tree_missing=h.tree_missing,
        parts=(
            breakdown.momentum,
            breakdown.real_user,
            breakdown.gap,
            breakdown.contribution_opp,
            breakdown.early_entry,
            breakdown.direction_fit,
            breakdown.maintainer,
        ),
    )
    breakdown.opportunity = breakdown.opportunity.model_copy(
        update={"confidence": opp_conf}
    )
    breakdown.exceptional = _exceptional_flag(breakdown)
    extra_flags = [flag for flag in flags if flag not in breakdown.flags]
    if extra_flags:
        breakdown.flags = list(breakdown.flags) + extra_flags

    unknown = _unknown_fields(breakdown, windows, feat, ctx)
    evidence = {
        "full_name": ctx.full_name,
        "score_version": SCORE_VERSION,
        "age_days": ctx.age_days,
        "C": ctx.C,
        "C_censored": ctx.C_censored,
        "S": ctx.S,
        "windows": {
            "v7": windows.v7,
            "v30": windows.v30,
            "v90": windows.v90,
            "v7_source": windows.v7_source,
            "v30_source": windows.v30_source,
        },
        "star_growth": None,
        "star_growth_status": "UNKNOWN",
        "activity": {
            "source": "last_pushed_at",
            "pushed_age_days": ctx.pushed_age_days,
            "note": "pushed_at is activity, not star growth",
        },
        "unknown_fields": unknown,
        "h_fired": list(h.fired),
        "flags": list(breakdown.flags),
        "known_bias": {"discovery_recency_bias": True},
    }
    return ScoredRepo(
        owner=ctx.owner,
        full_name=ctx.full_name,
        breakdown=breakdown,
        evidence=evidence,
    )


def _entry_window(ctx: Any, real_user: ComponentScore) -> ComponentScore:
    """Continuous Early Window. Soft maturity. No star<X bonus. Stale is not early."""
    weight = 15.0
    if ctx.C is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["C"],
            weight=weight,
            why="NA (C unknown)",
        )
    c = float(ctx.C)
    openness = clip01((40.0 - c) / 40.0)
    if ctx.pushed_age_days is None:
        fresh = None
        missing_fresh = True
    else:
        age_p = int(ctx.pushed_age_days)
        if age_p <= 7:
            fresh = 1.0
        elif age_p <= 30:
            fresh = 0.55
        elif age_p <= 90:
            fresh = 0.2
        else:
            fresh = 0.0
        missing_fresh = False
    if ctx.age_days is None:
        youth = None
        missing_youth = True
    else:
        # 30d ≈ 1.0; 2y ≈ 0.49; 3y ≈ 0.36. Soft, never a hard reject.
        youth = 1.0 - 0.7 * clip01((float(ctx.age_days) - 30.0) / 1000.0)
        missing_youth = False

    parts: list[tuple[float, float]] = [(0.40, openness)]
    missing: list[str] = []
    if fresh is None:
        missing.append("pushed_at")
    else:
        parts.append((0.35, fresh))
    if youth is None:
        missing.append("age_days")
    else:
        parts.append((0.25, youth))
    wsum = sum(w for w, _ in parts)
    value = 100.0 * sum(w * x for w, x in parts) / max(wsum, 1e-9)
    if fresh is not None and fresh <= 0.0:
        value = min(value, 22.0)
    if (
        real_user.value is not None
        and real_user.value >= 50
        and fresh is not None
        and fresh >= 0.55
    ):
        value = clip(value + 8, 0, 100)
    why = (
        f"entry_window openness={openness:.2f} fresh={fresh} youth={youth} "
        f"C={ctx.C} age_days={ctx.age_days} pushed_age_days={ctx.pushed_age_days}"
    )
    conf = "low" if missing_fresh or missing_youth else "high"
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        weight=weight,
        why=why,
    )


def _gap_access(ctx: Any, feat: FeaturesBlob) -> ComponentScore:
    """Need × access. S/C is not Opportunity. High gap × low access stays low."""
    weight = 15.0
    if ctx.C is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["C"],
            weight=weight,
            why="NA (C unknown)",
        )
    if ctx.C_censored or (ctx.S is not None and ctx.S > 15_000):
        return ComponentScore(
            value=10.0,
            confidence="high",
            weight=weight,
            why="C_censored or S>15000; access not inferred from fame",
        )
    missing: list[str] = []
    room = clip01((20.0 - float(ctx.C)) / 19.0)
    u_issue = ctx.U_issue
    if u_issue is None:
        demand = None
        missing.append("U_issue")
    else:
        u30 = ctx.U_commit_30d if ctx.U_commit_30d is not None else 0
        demand = clip01((u_issue / max(u30, 1) - 1) / 4)
    if feat.maint_touch is None and feat.unassigned_help is None:
        access = None
        missing.append("access")
    else:
        touch = feat.maint_touch
        help_u = feat.unassigned_help
        bits: list[float] = []
        if touch is not None:
            bits.append(float(touch))
        if help_u is not None:
            bits.append(clip01(help_u / 4))
        access = sum(bits) / len(bits) if bits else None
    # Do not use S/C. Famous-and-thin is not an entry invitation.
    terms: list[tuple[float, float]] = [(0.25, room)]
    if demand is not None:
        terms.append((0.40, demand))
    else:
        missing.append("demand")
    if access is not None:
        terms.append((0.35, access))
    wsum = sum(w for w, _ in terms)
    value = 100.0 * sum(w * x for w, x in terms) / max(wsum, 1e-9)
    if access is not None and access < 0.15 and demand is not None and demand >= 0.7:
        value = min(value, 28.0)
    conf = "high" if not missing else "medium"
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        weight=weight,
        why=(
            f"gap_access room={room:.2f} demand={demand} access={access} "
            f"C={ctx.C} (S/C not used)"
        ),
    )


def _contribution_ixnfa(
    ctx: Any,
    feat: FeaturesBlob,
    direction: ComponentScore,
) -> ComponentScore:
    """Impact × Need × Feasibility × Acceptance. GFI is capped. Missing files ≠ need."""
    weight = 20.0
    if feat.tree_names is None or feat.repeat_clusters is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["issue_sample_or_tree"],
            weight=weight,
            why="NA (need Phase B sample and tree)",
        )
    missing: list[str] = []
    impact = (direction.value or 0.0) / 100.0
    if direction.value is None:
        missing.append("direction")
        impact = 0.5
    clusters = feat.repeat_clusters or 0
    help_n = feat.help_n if feat.help_n is not None else 0
    need = 0.70 * clip01(clusters / 3) + 0.30 * clip01(help_n / 8)
    feas = 1.0
    if feat.screenshot_only:
        feas *= 0.5
    if feat.gap_docs:
        feas *= 0.9
    if feat.gap_tests:
        feas *= 0.95
    if feat.maint_touch is None:
        accept = None
        missing.append("acceptance")
    else:
        accept = float(feat.maint_touch)
    terms: list[tuple[float, float]] = [
        (0.30, impact),
        (0.30, need),
        (0.20, feas),
    ]
    if accept is not None:
        terms.append((0.20, accept))
    wsum = sum(w for w, _ in terms)
    value = 100.0 * sum(w * x for w, x in terms) / max(wsum, 1e-9)
    if accept is not None and accept < 0.1:
        value = min(value, 35.0)
    return ComponentScore(
        value=clip(value, 0, 100),
        confidence="high" if not missing else "medium",
        missing=missing,
        weight=weight,
        why=(
            f"I×N×F×A impact={impact:.2f} need={need:.2f} feas={feas:.2f} "
            f"accept={accept} (GFI capped; no missing-file bonus)"
        ),
    )


def _maintainer_v2(ctx: Any, feat: FeaturesBlob) -> ComponentScore:
    """No 0.4 NA-fill. Freshness is activity, not star growth."""
    weight = 5.0
    if ctx.pushed_age_days is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["pushed_at"],
            weight=weight,
            why="NA (no pushed_at)",
        )
    missing: list[str] = []
    terms: list[tuple[float, float]] = []
    age = ctx.pushed_age_days
    if age <= 14:
        fresh = 1.0
    elif age <= 45:
        fresh = 0.5
    elif age <= 180:
        fresh = 0.1
    else:
        fresh = 0.0
    terms.append((0.35, fresh))
    if feat.health_percentage is None:
        missing.append("health")
    else:
        terms.append((0.30, feat.health_percentage / 100.0))
    if feat.maint_touch is None:
        missing.append("maint_touch")
    else:
        terms.append((0.25, float(feat.maint_touch)))
    spdx = ctx.license_spdx
    license_ok = 1.0 if spdx and str(spdx).upper() != "NOASSERTION" else 0.0
    terms.append((0.10, license_ok))
    wsum = sum(w for w, _ in terms)
    value = 100.0 * sum(w * x for w, x in terms) / max(wsum, 1e-9)
    conf = "high" if not missing else "medium"
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        weight=weight,
        why=(
            f"maintainer_v2 fresh={fresh} health={feat.health_percentage} "
            f"maint_touch={feat.maint_touch} (no NA-fill 0.4)"
        ),
    )


def _unknown_fields(
    bd: ScoreBreakdown, windows: Any, feat: FeaturesBlob, ctx: Any
) -> list[str]:
    out: list[str] = []
    if windows.v7 is None:
        out.append("star_growth_7d")
        out.append("v7")
    if feat.maint_touch is None:
        out.append("maintainer_ttr")
        out.append("maint_touch")
    if ctx.U_commit_30d is None:
        out.append("unique_committers_30d")
    for name, part in (
        ("momentum", bd.momentum),
        ("real_user", bd.real_user),
        ("gap", bd.gap),
        ("contribution_opp", bd.contribution_opp),
        ("early_entry", bd.early_entry),
        ("maintainer", bd.maintainer),
    ):
        out.extend(f"{name}.{m}" for m in part.missing)
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq
