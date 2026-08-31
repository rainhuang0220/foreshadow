from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import ScoringSettings
from foreshadow.models import ComponentScore, FeaturesBlob, ScoreBreakdown
from foreshadow.pipeline.direction import load_direction_bags, score_direction
from foreshadow.pipeline.features import (
    SnapshotPoint,
    Windows,
    clip,
    clip01,
    compute_windows,
    readme_install,
)
from foreshadow.pipeline.h_rules import apply_penalties, evaluate_h

COMPONENT_KEYS = (
    "momentum",
    "real_user",
    "gap",
    "contribution_opp",
    "early_entry",
    "direction_fit",
    "maintainer",
)


@dataclass
class ScoredRepo:
    owner: str
    full_name: str
    breakdown: ScoreBreakdown
    evidence: dict[str, Any] = field(default_factory=dict)
    why_now: str | None = None
    contribution_bullets: list[str] | None = None


def mix_opportunity(
    components: Mapping[str, ComponentScore],
    weights: ScoringSettings | Mapping[str, float],
) -> ComponentScore:
    total = 0.0
    missing: list[str] = []
    for key in COMPONENT_KEYS:
        cs = components.get(key)
        if cs is None or cs.value is None:
            missing.append(key)
            continue
        total += (_weight(weights, key) / 100.0) * cs.value
    return ComponentScore(
        value=total,
        confidence="high" if not missing else "medium",
        missing=missing,
    )


def score_repo(
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
    windows: Windows = ctx.windows

    momentum, accel_term, size_term = _momentum(ctx, windows, scoring)
    direction = _direction_fit(ctx, feat, bags)
    real_user = _real_user(ctx, feat)
    gap = _gap(ctx)
    contribution_opp = _contribution_opp(ctx, feat, direction)
    early_entry = _early_entry(ctx, real_user)
    maintainer = _maintainer(ctx, feat)

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

    proxy = None
    if windows.v7 is None:
        proxy = _lifetime_proxy(ctx, windows, size_term)
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

    evidence = {
        "full_name": ctx.full_name,
        "age_days": ctx.age_days,
        "C": ctx.C,
        "C_censored": ctx.C_censored,
        "windows": {
            "v7": windows.v7,
            "v30": windows.v30,
            "v90": windows.v90,
            "v7_source": windows.v7_source,
            "v30_source": windows.v30_source,
        },
        "explosion_lifetime_proxy": proxy,
        "h_fired": list(h.fired),
        "flags": list(breakdown.flags),
    }
    return ScoredRepo(
        owner=ctx.owner,
        full_name=ctx.full_name,
        breakdown=breakdown,
        evidence=evidence,
    )


def late(stars: float, contributors: float) -> bool:
    return (
        (stars >= 5_000 and contributors >= 30) or stars >= 20_000 or contributors >= 80
    )


def _weight(weights: ScoringSettings | Mapping[str, float], key: str) -> float:
    attr = f"{key}_weight"
    if isinstance(weights, Mapping):
        return float(weights[attr])
    return float(getattr(weights, attr))


def _momentum(
    ctx: SimpleNamespace,
    windows: Windows,
    scoring: ScoringSettings,
) -> tuple[ComponentScore, float, float]:
    weight = float(scoring.momentum_weight)
    s_t = ctx.S or 0
    size_term = clip01((math.log10(s_t + 1) - 2) / 3)
    if windows.v7 is None:
        return (
            ComponentScore(
                value=None,
                confidence="low",
                missing=["S(t-7)"],
                weight=weight,
                why="NA (insufficient history)",
            ),
            0.0,
            size_term,
        )
    rel = windows.rel_growth_7d
    g = clip01((rel or 0.0) / 1.0)
    accel_term = 0.0
    if windows.v30 is not None and windows.accel_ratio is not None:
        accel_term = clip01((windows.accel_ratio - 1) / 3)
    else:
        life = windows.lifetime_star_rate or 0.0
        accel_term = 0.4 * clip01(windows.v7 / max(2 * life, 1))
    value = 100.0 * (0.45 * g + 0.40 * accel_term + 0.15 * (1 - size_term))
    conf: str = "high" if windows.v30 is not None else "medium"
    return (
        ComponentScore(
            value=value,
            confidence=conf,
            weight=weight,
            why=(
                f"rel_growth_7d={windows.rel_growth_7d}, "
                f"accel_ratio={windows.accel_ratio}, size_discount s={size_term:.2f}"
            ),
        ),
        accel_term,
        size_term,
    )


def _real_user(ctx: SimpleNamespace, feat: FeaturesBlob) -> ComponentScore:
    weight = 15.0
    has_sample = (
        feat.u_issue is not None
        or feat.u_issue_ext is not None
        or feat.issue_sample_n is not None
    )
    install_known = feat.readme_install is not None or feat.readme_excerpt is not None
    if not has_sample:
        if ctx.has_issues is False and install_known:
            fork_signal = _fork_signal(ctx)
            install = 1 if ctx.readme_install else 0
            i_open = ctx.I_open
            if i_open is None or i_open == 0:
                value = 25 * fork_signal + 15 * install
                return ComponentScore(
                    value=value,
                    confidence="low",
                    weight=weight,
                    why=f"issues disabled; fork_signal={fork_signal}, install={install}",
                )
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["issue_sample"],
            weight=weight,
            why="NA (no Phase B issue sample)",
        )

    u_ext = feat.u_issue_ext or 0
    bug_n = feat.bug_n or 0
    talk_n = feat.talk_n or 0
    usage_closed_n = feat.usage_closed_n or 0
    user_breadth = clip01(u_ext / 15)
    user_depth = clip01((bug_n + talk_n) / 12)
    usage_closed = clip01(usage_closed_n / 6)
    fork_signal = _fork_signal(ctx)
    install = 1 if ctx.readme_install else 0
    value = 100.0 * (
        0.35 * user_breadth
        + 0.30 * user_depth
        + 0.15 * usage_closed
        + 0.10 * fork_signal
        + 0.10 * install
    )
    sample_n = feat.issue_sample_n
    i_open = ctx.I_open
    if ctx.has_issues and (
        (sample_n is not None and sample_n >= 30)
        or (sample_n is not None and i_open is not None and sample_n >= i_open)
    ):
        conf = "high"
    elif ctx.has_issues and sample_n is not None and 10 <= sample_n <= 29:
        conf = "medium"
    else:
        conf = "low"
    return ComponentScore(
        value=value,
        confidence=conf,
        weight=weight,
        why=(
            f"U_issue_ext={feat.u_issue_ext}, bug_n={feat.bug_n}, "
            f"talk_n={feat.talk_n}, fork_star={ctx.fork_star}, install={install}"
        ),
    )


def _gap(ctx: SimpleNamespace) -> ComponentScore:
    weight = 15.0
    if ctx.C is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["C"],
            weight=weight,
            why="NA (C unknown)",
        )
    s_t = ctx.S
    if ctx.C_censored or (s_t is not None and s_t > 15_000):
        return ComponentScore(
            value=10.0,
            confidence="high",
            weight=weight,
            why="C_censored or S>15000",
        )
    star_per = (s_t or 0) / max(ctx.C, 1)
    r = clip01((star_per - 10) / 90)
    small_bench = clip01((20 - ctx.C) / 19)
    missing: list[str] = []
    u_issue = ctx.U_issue
    if u_issue is None:
        value = 100.0 * (0.35 * r + 0.30 * small_bench)
        missing.append("U_issue")
        conf = "medium"
        why = f"star_per_contrib={star_per}, C={ctx.C}, d dropped"
    else:
        u30 = ctx.U_commit_30d if ctx.U_commit_30d is not None else 0
        demand = u_issue / max(u30, 1)
        d = clip01((demand - 1) / 4)
        value = 100.0 * (0.35 * r + 0.35 * d + 0.30 * small_bench)
        conf = "high"
        why = (
            f"star_per_contrib={star_per}, demand_ratio={demand}, "
            f"C={ctx.C}, starved={ctx.starved}"
        )
    if ctx.I_open == 0 and ctx.has_issues is False:
        value *= 0.7
        conf = "low"
    if (
        ctx.C == 1
        and ctx.age_days is not None
        and ctx.age_days >= 60
        and s_t is not None
        and s_t >= 150
    ):
        value = clip(value - 10, 0, 100)
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        weight=weight,
        why=why,
    )


def _contribution_opp(
    ctx: SimpleNamespace,
    feat: FeaturesBlob,
    direction: ComponentScore,
) -> ComponentScore:
    weight = 20.0
    if (
        feat.help_n is None
        or feat.repeat_clusters is None
        or feat.tree_names is None
        or feat.gap_ci is None
        or feat.gap_tests is None
        or feat.gap_docs is None
    ):
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["issue_sample_or_tree"],
            weight=weight,
            why="NA (need Phase B sample and tree)",
        )
    skill = (direction.value or 0.0) / 100.0
    surface = clip01(feat.help_n / 5) * 0.7 + clip01(feat.repeat_clusters / 3) * 0.3
    gaps = (feat.gap_ci + feat.gap_tests + feat.gap_docs) / 3
    touch = feat.maint_touch if feat.maint_touch is not None else 0.0
    receptive = 0.4 + 0.6 * touch
    value = 100.0 * (0.40 * surface + 0.25 * gaps + 0.20 * receptive + 0.15 * skill)
    if ctx.bus:
        value = clip(value + 8, 0, 100)
    if feat.help_n == 0 and feat.repeat_clusters == 0 and gaps < 0.3:
        value = min(value, 40)
    return ComponentScore(
        value=value,
        confidence="high",
        weight=weight,
        why=(
            f"surface={surface:.2f}, gaps={gaps:.2f}, "
            f"receptive={receptive:.2f}, skill={skill:.2f}"
        ),
    )


def _early_entry(ctx: SimpleNamespace, real_user: ComponentScore) -> ComponentScore:
    weight = 15.0
    if ctx.C is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["C"],
            weight=weight,
            why="NA (C unknown)",
        )
    s_t = ctx.S or 0
    if ctx.C_censored:
        late_now = True
    else:
        late_now = late(s_t, ctx.C)
    late_10x = late(s_t * 10, ctx.C * 10)
    if late_now:
        value = 8 + 12 * clip01((25_000 - s_t) / 25_000)
        why = f"late_now=true, S={ctx.S}, C={ctx.C}"
    elif late_10x:
        value = 88.0
        value -= 8 * clip01(ctx.C / 25)
        value -= 8 * clip01((s_t - 200) / 4_000)
        value = clip(value, 70, 95)
        why = f"late_now=false, late_10x=true, S={ctx.S}, C={ctx.C}"
    else:
        value = 62.0
        if real_user.value is not None and real_user.value >= 50:
            value += 10
        if ctx.age_days is not None and ctx.age_days < 21:
            value -= 15
        value = clip(value, 40, 80)
        why = f"micro/early, S={ctx.S}, C={ctx.C}"
    return ComponentScore(
        value=value,
        confidence="high",
        weight=weight,
        why=why,
    )


def _direction_fit(
    ctx: SimpleNamespace,
    feat: FeaturesBlob,
    bags: Sequence | Mapping | None,
) -> ComponentScore:
    weight = 10.0
    headings = feat.readme_headings
    conf: str = "low" if not headings else "high"
    if ctx.direction_fit_override is not None:
        return ComponentScore(
            value=float(ctx.direction_fit_override),
            confidence=conf,
            weight=weight,
            why="fixture input",
        )
    loaded = bags if bags is not None else load_direction_bags()
    value = score_direction(
        ctx.name,
        ctx.description or "",
        ctx.topics,
        headings,
        ctx.language,
        loaded,
    )
    return ComponentScore(
        value=float(value),
        confidence=conf,
        weight=weight,
        why="bag max",
    )


def _maintainer(ctx: SimpleNamespace, feat: FeaturesBlob) -> ComponentScore:
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
    if feat.health_percentage is None:
        health = 0.4
        missing.append("health")
        conf = "medium"
    else:
        health = feat.health_percentage / 100.0
        conf = "high"
    age = ctx.pushed_age_days
    if age <= 14:
        fresh = 1.0
    elif age <= 45:
        fresh = 0.5
    elif age <= 180:
        fresh = 0.1
    else:
        fresh = 0.0
    if feat.maint_touch is None:
        response = 0.4
        missing.append("maint_touch")
        if conf == "high":
            conf = "medium"
    else:
        response = feat.maint_touch
    spdx = ctx.license_spdx
    license_ok = 1.0 if spdx and str(spdx).upper() != "NOASSERTION" else 0.0
    value = 100.0 * (0.30 * health + 0.30 * fresh + 0.25 * response + 0.15 * license_ok)
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        weight=weight,
        why=(f"health={health}, fresh={fresh}, maint_touch={response}, license={spdx}"),
    )


def _explosion(
    windows: Windows,
    accel_term: float,
    size_term: float,
) -> ComponentScore:
    missing: list[str] = []
    rel = windows.rel_growth_7d
    if rel is None:
        rel_term = 0.0
        missing.append("rel_growth_7d")
    else:
        rel_term = clip01(rel / 1.0)
    value = 100.0 * (0.50 * rel_term + 0.30 * accel_term + 0.20 * (1 - size_term))
    if windows.v7 is None:
        return ComponentScore(
            value=None,
            confidence="low",
            missing=["v7"],
            why="NA (insufficient history)",
        )
    conf: str = "high" if windows.v30 is not None else "medium"
    return ComponentScore(
        value=value,
        confidence=conf,
        missing=missing,
        why=f"rel_growth_7d={windows.rel_growth_7d}, a={accel_term}, s={size_term:.2f}",
    )


def _lifetime_proxy(
    ctx: SimpleNamespace,
    windows: Windows,
    size_term: float,
) -> float | None:
    life = windows.lifetime_star_rate
    if life is None:
        return None
    return min(
        40.0,
        100.0 * clip01(math.log10(life + 1) / 2) * (1 - size_term),
    )


def _opportunity_confidence(
    *,
    v7: float | None,
    tree_missing: bool,
    parts: Sequence[ComponentScore],
) -> str:
    if v7 is None or tree_missing:
        return "low"
    n_med = sum(1 for c in parts if c.confidence in {"medium", "high"})
    if n_med >= 5:
        return "high"
    return "medium"


def _exceptional_flag(bd: ScoreBreakdown) -> str | None:
    df = bd.direction_fit.value
    if df is None or df >= 70:
        return None
    opp = bd.opportunity.value
    vals = [
        c.value
        for c in (
            bd.momentum,
            bd.real_user,
            bd.gap,
            bd.contribution_opp,
            bd.early_entry,
        )
        if c.value is not None
    ]
    five = sum(vals) / len(vals) if vals else None
    five_min = min(vals) if vals else None
    if df >= 60 and opp is not None and opp >= 75:
        return "off_direction_but_strong"
    if df >= 60 and five is not None and five >= 80:
        return "exceptional_override"
    if (
        df >= 40
        and five is not None
        and five >= 85
        and five_min is not None
        and five_min >= 75
    ):
        return "exceptional_override_weak_fit"
    return None


def _fork_signal(ctx: SimpleNamespace) -> float:
    s_t = ctx.S
    if s_t is None or s_t < 50:
        return 0.0
    fs = ctx.fork_star
    if fs is None:
        return 0.15
    if 0.06 <= fs <= 0.35:
        return 1.0
    if 0.03 <= fs < 0.06:
        return 0.5
    return 0.15


def _features(data: dict) -> FeaturesBlob:
    raw = data.get("features") or {}
    if isinstance(raw, FeaturesBlob):
        return raw
    if isinstance(raw, dict):
        return FeaturesBlob.model_validate(raw)
    return FeaturesBlob()


def _as_dict(repo: object) -> dict:
    if isinstance(repo, dict):
        return dict(repo)
    if hasattr(repo, "model_dump"):
        return repo.model_dump()
    return dict(vars(repo))


def _context(
    data: dict,
    feat: FeaturesBlob,
    clock: Clock,
    scoring: ScoringSettings,
) -> SimpleNamespace:
    today = clock.today()
    snaps = _snapshots(data)
    created = _parse_date(data.get("created_at"))
    age_days = data.get("age_days")
    if age_days is None and created is not None:
        age_days = max((today - created).days, 1)
    if created is None and age_days is not None:
        created = today - timedelta(days=int(age_days))

    windows = compute_windows(snaps, clock, created, scoring.window_slack_days)
    today_snap = next((s for s in snaps if s.date == today), None)
    s_t = _first(data.get("S"), today_snap.stars if today_snap else None)
    f_t = _first(data.get("F"), today_snap.forks if today_snap else None)
    pushed_age = data.get("pushed_age_days")
    if pushed_age is None:
        pushed_at = _parse_datetime(data.get("pushed_at"))
        if pushed_at is not None:
            pushed_age = max((today - pushed_at.date()).days, 0)

    c = data.get("C")
    censored = bool(data.get("C_censored") or False)
    u30 = data.get("U_commit_30d")
    i_open = _first(data.get("I_open"), feat.i_open)
    u_issue = _first(data.get("U_issue"), feat.u_issue)
    fork_star = data.get("fork_star")
    if fork_star is None and s_t is not None and f_t is not None:
        fork_star = f_t / max(s_t, 1)

    install = feat.readme_install
    if install is None and feat.readme_excerpt:
        install = bool(readme_install(feat.readme_excerpt))
    install_flag = 1 if install else 0

    tree_names = feat.tree_names
    starved = _starved(
        s_t=s_t,
        c=c,
        censored=censored,
        age_days=age_days,
        u_issue=u_issue,
        u30=u30,
        i_open=i_open,
    )
    bus = False
    if u30 is not None and i_open is not None:
        bus = u30 <= 2 and i_open >= 8

    full_name = data.get("full_name") or ""
    owner = data.get("owner") or (full_name.split("/")[0] if full_name else "")
    name = data.get("name") or (full_name.split("/")[-1] if full_name else "")
    if not full_name and owner and name:
        full_name = f"{owner}/{name}"

    yesterday = today - timedelta(days=1)
    y_snap = next((s for s in snaps if s.date == yesterday), None)
    s_prev = _first(data.get("S_prev"), data.get("S_t_minus_1"))
    if s_prev is None and y_snap is not None:
        s_prev = y_snap.stars

    has_issues = data.get("has_issues")
    if has_issues is None:
        has_issues = data.get("hasIssuesEnabled")

    return SimpleNamespace(
        owner=owner,
        name=name,
        full_name=full_name,
        description=data.get("description") or "",
        language=data.get("language"),
        topics=list(data.get("topics") or []),
        license_spdx=data.get("license_spdx"),
        S=s_t,
        F=f_t,
        C=c,
        C_censored=censored,
        U_commit_30d=u30,
        U_issue=u_issue,
        I_open=i_open,
        I_closed=data.get("I_closed"),
        has_issues=has_issues,
        fork_star=fork_star,
        age_days=age_days,
        pushed_age_days=pushed_age,
        readme_install=install_flag,
        readme_excerpt=feat.readme_excerpt,
        screenshot_only=feat.screenshot_only,
        has_workflows=feat.has_workflows,
        gap_tests=feat.gap_tests,
        tree_names=tree_names,
        root_names=tree_names,
        features=feat,
        is_fork=bool(data.get("is_fork") or data.get("isFork") or False),
        archived=bool(data.get("archived") or data.get("is_archived") or False),
        disabled=bool(data.get("disabled") or data.get("is_disabled") or False),
        is_empty=bool(data.get("is_empty") or data.get("isEmpty") or False),
        direction_fit_override=data.get("direction_fit"),
        windows=windows,
        starved=starved,
        bus=bus,
        S_prev=s_prev,
    )


def _starved(
    *,
    s_t: float | None,
    c: float | None,
    censored: bool,
    age_days: float | None,
    u_issue: float | None,
    u30: float | None,
    i_open: float | None,
) -> bool:
    if censored or s_t is None or c is None or age_days is None:
        return False
    if not (100 <= s_t <= 8_000 and 1 <= c <= 25 and age_days >= 21):
        return False
    star_per = s_t / max(c, 1)
    if star_per >= 40:
        return True
    if u_issue is not None:
        demand = u_issue / max(u30 if u30 is not None else 0, 1)
        if demand >= 3.0 and u_issue >= 8:
            return True
    if i_open is not None and u30 is not None:
        issue_per = i_open / max(c, 1)
        if i_open >= 15 and issue_per >= 4 and u30 <= 3:
            return True
    return False


def _snapshots(data: dict) -> list[SnapshotPoint]:
    out: list[SnapshotPoint] = []
    for item in data.get("snapshots") or []:
        if isinstance(item, SnapshotPoint):
            out.append(item)
            continue
        raw_date = item.get("date")
        day = _parse_date(raw_date)
        if day is None:
            continue
        out.append(
            SnapshotPoint(
                date=day,
                stars=item.get("stars"),
                forks=item.get("forks"),
                pushed_at=_parse_datetime(item.get("pushed_at")),
            )
        )
    return out


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            day = _parse_date(value)
            if day is None:
                return None
            return datetime(day.year, day.month, day.day, tzinfo=UTC)
    return None


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
