from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from foreshadow.models import ReportJSON, ScoreBreakdown
from foreshadow.pipeline.score import ScoredRepo

FORBIDDEN_PHRASES = ("will explode", "next LangChain", "guaranteed")
_LANG_TOPICS = {
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "c++",
    "java",
    "ruby",
}
_EXCEPTIONAL = frozenset(
    {
        "off_direction_but_strong",
        "exceptional_override",
        "exceptional_override_weak_fit",
    }
)
H_KEYS = tuple(f"H{i}" for i in range(1, 11))
REJECTED_KEYS = H_KEYS + (
    "fake_spike",
    "below_threshold",
    "momentum_low",
    "direction",
    "review_filter",
    "incomplete_tree",
)
CARD_KEYS = (
    "rank",
    "node_id",
    "full_name",
    "html_url",
    "opportunity",
    "explosion",
    "contribution",
    "confidence",
    "momentum",
    "real_user",
    "gap",
    "contribution_opp",
    "early_entry",
    "direction_fit",
    "maintainer",
    "flags",
    "exceptional",
    "vetoed",
    "veto_reason",
    "why_now",
    "windows",
    "components",
    "evidence_ref",
)


def render_json(report: ReportJSON) -> str:
    return (
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    )


def render_markdown(report: ReportJSON) -> str:
    lines = [f"# Foreshadow — {report.date}", "", history_line(report.snapshot_days)]
    cards = list(report.cards or [])[:5]
    empty = report.top5_count == 0 or not cards
    if not empty:
        lines.append(
            "Explosion is a rule on relative growth, not a forecast "
            "that a project will “make it.”"
        )
    lines.append("")
    if empty:
        if report.status != "complete":
            lines.append(_run_line(report))
            lines.append("")
        reason = report.reason or "no_eligible_opportunities"
        lines.append(f"**Top 5: 0** — `{reason}`")
        lines.append("")
        lines.append("This is a successful run. Prefer zero over padding.")
        lines.append("")
        lines.append(f"Rejected: {_rejected_summary(report)}")
        if report.watchlist_appendix:
            names = ", ".join(
                f"`{item.get('full_name')}`" for item in report.watchlist_appendix[:10]
            )
            lines.append(f"Watchlist (not Top 5): {names}")
        lines.append("")
        lines.extend(_source_health_lines(report))
        return _join(lines)

    lines.append(_run_line(report))
    top_n = min(len(cards), 5)
    lines.append(
        f"Candidates: {report.candidate_count} → scored {report.scored_count} "
        f"→ **Top 5: {top_n}**"
    )
    lines.append(
        f"Budget: {report.budget_used} / {report.budget_cap} GraphQL points, "
        f"{report.budget_rest_used} REST"
    )
    lines.append("")
    lines.append(f"## Top {top_n}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")
    for card in cards:
        lines.extend(_render_card(card))
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("")
    if report.active:
        lines.append("## Active (entered / investigate)")
        for item in report.active:
            lines.append(_active_line(item))
        lines.append("")
    if report.watchlist_appendix:
        lines.append("## Watchlist (not Top 5)")
        for item in report.watchlist_appendix[:10]:
            lines.append(_watch_line(item))
        lines.append("")
    if report.below_bar:
        lines.append("## Below bar (max 3)")
        for item in report.below_bar[:3]:
            lines.append(_below_line(item))
        lines.append("")
    lines.extend(_source_health_lines(report))
    return _join(lines)


def history_line(snapshot_days: int) -> str:
    days = int(snapshot_days or 0)
    if days < 7:
        unit = "snapshot-day" if days == 1 else "snapshot-days"
        return f"Explosion caveat: {days} {unit} of history (v7 undefined; Top 5 empty)"
    if days < 30:
        return f"Snapshot history: {days} days (v7 defined; v30 may still be undefined)"
    return f"Snapshot history: {days} days (v7 and v30 defined for tracked repos)"


def build_card(
    scored: ScoredRepo,
    *,
    rank: int,
    repo: Mapping[str, Any] | None = None,
    captured_at: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    repo = dict(repo or {})
    bd = scored.breakdown
    today = date or _card_date(repo, captured_at)
    windows = dict((scored.evidence or {}).get("windows") or {})
    components = _components(bd)
    feat = repo.get("features") or {}
    if isinstance(feat, Mapping):
        feat_map = dict(feat)
    else:
        feat_map = {}
    html = repo.get("html_url") or (
        f"https://github.com/{scored.full_name}" if scored.full_name else ""
    )
    node_id = str(repo.get("node_id") or (scored.evidence or {}).get("node_id") or "")
    spdx = repo.get("license_spdx")
    snap_dates = _snapshot_dates(repo, today)
    return {
        "rank": rank,
        "node_id": node_id,
        "full_name": scored.full_name,
        "html_url": html,
        "opportunity": bd.opportunity.value,
        "explosion": bd.explosion.value,
        "contribution": bd.contribution.value,
        "confidence": bd.opportunity.confidence,
        "momentum": bd.momentum.value,
        "real_user": bd.real_user.value,
        "gap": bd.gap.value,
        "contribution_opp": bd.contribution_opp.value,
        "early_entry": bd.early_entry.value,
        "direction_fit": bd.direction_fit.value,
        "maintainer": bd.maintainer.value,
        "flags": list(bd.flags),
        "exceptional": bd.exceptional,
        "vetoed": bd.vetoed,
        "veto_reason": bd.veto_reason,
        "why_now": scored.why_now or build_why_now(scored, repo),
        "windows": windows,
        "components": components,
        "evidence_ref": {
            "snapshot_dates": snap_dates,
            "captured_at": captured_at
            or (scored.evidence or {}).get("captured_at")
            or "",
            "license_spdx": spdx,
        },
        "best_contribution": (
            list(scored.contribution_bullets)[:3]
            if scored.contribution_bullets
            else _help_bullets(feat_map)
        ),
        "risk": build_risk(scored, repo),
        "direction_topics": _topic_label(repo.get("topics") or []),
    }


def build_report(
    *,
    date: str,
    status: str,
    scored_rows: Sequence[tuple[ScoredRepo, Mapping[str, Any]]],
    selected: Sequence[ScoredRepo],
    candidate_count: int,
    scored_count: int,
    budget_used: int,
    budget_cap: int,
    budget_rest_used: int,
    snapshot_days: int,
    source_health: Mapping[str, Any],
    active: Sequence[Mapping[str, Any]] | None = None,
    watchlist_appendix: Sequence[Mapping[str, Any]] | None = None,
    captured_at: str | None = None,
    min_opportunity: float = 55,
    min_explosion: float = 35,
    review_filter: int = 0,
) -> ReportJSON:
    selected_names = {row.full_name for row in selected}
    by_name = {row.full_name: repo for row, repo in scored_rows}
    cards = [
        build_card(
            row,
            rank=i,
            repo=by_name.get(row.full_name, {}),
            captured_at=captured_at,
            date=date,
        )
        for i, row in enumerate(selected, 1)
    ]
    scored = [row for row, _ in scored_rows]
    health = dict(source_health)
    health["v7_na"] = sum(
        1
        for row in scored
        if ((row.evidence or {}).get("windows") or {}).get("v7") is None
    )
    reason = "no_eligible_opportunities" if not cards else None
    return ReportJSON(
        date=date,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        top5_count=len(cards),
        candidate_count=candidate_count,
        scored_count=scored_count,
        budget_used=budget_used,
        budget_cap=budget_cap,
        budget_rest_used=budget_rest_used,
        snapshot_days=snapshot_days,
        cards=cards,
        active=[dict(item) for item in (active or [])],
        watchlist_appendix=[dict(item) for item in (watchlist_appendix or [])],
        below_bar=below_bar_items(scored_rows, selected_names),
        rejected_counts=rejected_counts(
            scored,
            min_opportunity=min_opportunity,
            min_explosion=min_explosion,
            review_filter=review_filter,
        ),
        source_health=health,
    )


def rejected_counts(
    scored: Sequence[ScoredRepo],
    *,
    min_opportunity: float = 55,
    min_explosion: float = 35,
    review_filter: int = 0,
) -> dict[str, int]:
    counts = {key: 0 for key in REJECTED_KEYS}
    counts["review_filter"] = int(review_filter)
    for row in scored:
        bd = row.breakdown
        flags = set(bd.flags)
        for key in H_KEYS:
            if key in flags:
                counts[key] += 1
        if flags & {"H5", "H6", "H7"}:
            counts["fake_spike"] += 1
        if bd.opportunity.value is not None and bd.opportunity.value < min_opportunity:
            counts["below_threshold"] += 1
        mom = bd.momentum
        exp = bd.explosion.value
        if (
            mom.value is None
            or mom.confidence not in {"medium", "high"}
            or exp is None
            or exp < min_explosion
        ):
            counts["momentum_low"] += 1
        df = bd.direction_fit.value
        if df is not None and df < 70 and bd.exceptional not in _EXCEPTIONAL:
            counts["direction"] += 1
        if "tree_missing" in flags:
            counts["incomplete_tree"] += 1
    return counts


def below_bar_items(
    scored_rows: Sequence[tuple[ScoredRepo, Mapping[str, Any]]],
    selected_names: set[str],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scored, _repo in scored_rows:
        if scored.full_name in selected_names:
            continue
        bd = scored.breakdown
        if bd.vetoed:
            out.append(
                {
                    "full_name": scored.full_name,
                    "kind": "veto",
                    "veto_reason": bd.veto_reason or "H",
                    "reason": f"veto {bd.veto_reason}",
                }
            )
        elif bd.opportunity.value is not None and bd.opportunity.value < 55:
            pts = round(bd.opportunity.value)
            out.append(
                {
                    "full_name": scored.full_name,
                    "kind": "below",
                    "reason": f"Opportunity {pts} < 55",
                }
            )
        if len(out) >= limit:
            break
    return out


def build_why_now(scored: ScoredRepo, repo: Mapping[str, Any]) -> str:
    parts: list[str] = []
    snaps = list(repo.get("snapshots") or [])
    today_stars = repo.get("S")
    base_stars = None
    if snaps:
        ordered = sorted(snaps, key=lambda item: str(item.get("date") or ""))
        last = ordered[-1]
        if today_stars is None:
            today_stars = last.get("stars")
        day = _as_date(last.get("date"))
        if day is not None:
            want = (day - timedelta(days=7)).isoformat()
            for item in snaps:
                if str(item.get("date") or "")[:10] == want:
                    base_stars = item.get("stars")
                    break
    if today_stars is not None and base_stars is not None:
        parts.append(
            f"{int(today_stars) - int(base_stars)} net stars in 7 days "
            f"on a {int(base_stars)}-star base"
        )
    feat = repo.get("features") or {}
    u_ext = feat.get("u_issue_ext") if isinstance(feat, Mapping) else None
    if u_ext:
        parts.append(f"{u_ext} unique external issue authors")
    contrib = repo.get("C")
    if contrib is not None:
        parts.append(f"{contrib} contributors")
        if today_stars is not None and _late(
            float(today_stars) * 10, float(contrib) * 10
        ):
            parts.append(f"10× would crowd identity (`C→{int(contrib) * 10}`)")
    windows = (scored.evidence or {}).get("windows") or {}
    if windows.get("v7") is None:
        parts.append("v7 is undefined until ~7 snapshot-days of history")
    if not parts:
        return (
            "Insufficient evidence for a Why-now narrative. "
            "Explosion is a rule on relative growth, not a forecast."
        )
    return "; ".join(parts) + "."


def build_risk(scored: ScoredRepo, repo: Mapping[str, Any]) -> str:
    bits: list[str] = []
    contrib = repo.get("C")
    if contrib is not None and contrib < 15:
        bits.append(f"Maintainer concentration ({contrib} contributors)")
    if "is_accelerating" in scored.breakdown.flags:
        bits.append("growth could be a single viral post")
    if scored.breakdown.vetoed:
        bits.append(f"H-rules fired ({scored.breakdown.veto_reason})")
    else:
        bits.append("H-rules passed")
    return "; ".join(bits) + "."


def format_run_summary(
    *,
    date: str,
    discovered: int,
    hydrated: int,
    scored: int,
    selected: int,
    status: str,
    health: Mapping[str, Any],
    snapshot_days: int,
    report_path: Path | str | None,
    review_repo: str = "owner/repo",
    skipped: bool = False,
    wrote_config: str | None = None,
) -> str:
    lines: list[str] = []
    if wrote_config:
        lines.append(f"wrote config: {wrote_config}")
    lines.append(f"Foreshadow {date}")
    if skipped:
        lines.append("already complete (use --force to re-run)")
        if report_path:
            lines.append(f"report: {report_path}")
        return _join(lines)
    extra = _health_reasons(health)
    counts = (
        f"discovered {discovered}  hydrated {hydrated}  "
        f"scored {scored}  selected {selected}"
    )
    if status == "degraded" and extra:
        counts += f"  (degraded: {extra})"
    lines.append(counts)
    hist = f"snapshots: {snapshot_days} days of history"
    if snapshot_days < 7:
        hist += "  (Explosion still weak until ~7)"
    lines.append(hist)
    v7_ok = int(health.get("v7_available") or 0)
    v7_cov = health.get("v7_coverage_rate")
    panel = health.get("observation_panel_size")
    if panel is not None:
        cov = f"{v7_cov:.0%}" if isinstance(v7_cov, float) else "n/a"
        lines.append(
            "observation: "
            f"panel={panel} watch={int(health.get('user_watchlist_count') or 0)} "
            f"system={int(health.get('system_observed_count') or 0)} "
            f"fresh={int(health.get('fresh_discovery_count') or 0)} "
            f"retained={int(health.get('retained_from_previous_day') or 0)} "
            f"v7={v7_ok}/{scored} ({cov})"
        )
    if report_path:
        lines.append(f"report: {report_path}")
    lines.append(f"review: foreshadow review {review_repo} interested")
    return _join(lines)


def format_show(
    *,
    full_name: str,
    node_id: str,
    html_url: str | None,
    score: Mapping[str, Any] | None,
    snapshots: Sequence[Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
    entry: Mapping[str, Any] | None,
) -> str:
    lines = [f"{full_name}  node_id={node_id}"]
    if html_url:
        lines.append(html_url)
    lines.append("")
    if score:
        lines.append(
            f"Opportunity: {_show_num(score.get('opportunity'))}  "
            f"({score.get('confidence') or 'low'})"
        )
        lines.append(f"Explosion: {_show_num(score.get('explosion'))}")
        lines.append(f"Contribution: {_show_num(score.get('contribution'))}")
        flags = score.get("flags") or []
        if isinstance(flags, str):
            try:
                flags = json.loads(flags)
            except json.JSONDecodeError:
                flags = [flags]
        lines.append(f"Flags: {', '.join(str(f) for f in flags) or '(none)'}")
        lines.append("")
        lines.append("Components:")
        lines.append(_pretty(score.get("components")))
        lines.append("")
        lines.append("Evidence:")
        lines.append(_pretty(score.get("evidence")))
        lines.append("")
    else:
        lines.append("No score for this repo.")
        lines.append("")
    lines.append("Snapshots (last 7):")
    if snapshots:
        for snap in snapshots[:7]:
            lines.append(
                f"  {snap.get('date')}  stars={snap.get('stars')}  "
                f"forks={snap.get('forks')}  C={snap.get('C')}"
            )
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Reviews:")
    if reviews:
        for rev in reviews:
            note = f"  {rev.get('note')}" if rev.get("note") else ""
            lines.append(f"  {rev.get('created_at')}  {rev.get('action')}{note}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Entry:")
    if entry:
        lines.append(_pretty(dict(entry)))
    else:
        lines.append("  (none)")
    return _join(lines)


def write_reports(data_dir: Path, report: ReportJSON) -> Path:
    folder = Path(data_dir) / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    md_path = folder / f"{report.date}.md"
    js_path = folder / f"{report.date}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    js_path.write_text(render_json(report), encoding="utf-8")
    return md_path


def _join(lines: list[str]) -> str:
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _run_line(report: ReportJSON) -> str:
    extra = _health_reasons(report.source_health or {})
    if extra:
        return f"Run: **{report.status}** ({extra})"
    return f"Run: **{report.status}**"


def _health_reasons(health: Mapping[str, Any]) -> str:
    bits: list[str] = []
    if health.get("search_truncated"):
        bits.append("search truncated")
    failed = int(health.get("hydrate_failed") or 0)
    if failed:
        bits.append(f"{failed} hydrate failure" + ("s" if failed != 1 else ""))
    if health.get("budget_abort"):
        bits.append("budget abort")
    if health.get("watchlist_truncated"):
        bits.append("watchlist truncated")
    return "; ".join(bits)


def _rejected_summary(report: ReportJSON) -> str:
    rc = report.rejected_counts or {}
    h_rules = sum(int(rc.get(key, 0) or 0) for key in H_KEYS)
    return (
        f"H-rules={h_rules}, "
        f"below_threshold={int(rc.get('below_threshold', 0) or 0)}, "
        f"momentum_low={int(rc.get('momentum_low', 0) or 0)}, "
        f"direction={int(rc.get('direction', 0) or 0)}"
    )


def _render_card(card: Mapping[str, Any]) -> list[str]:
    comps = card.get("components") or {}
    flags = card.get("flags") or []
    opp = _pts(card.get("opportunity"))
    exp = _pts(card.get("explosion"))
    con = _pts(card.get("contribution"))
    oconf = card.get("confidence") or _comp_conf(comps, "opportunity")
    econf = _comp_conf(comps, "explosion")
    cconf = _comp_conf(comps, "contribution")
    exp_note = (
        "  — potential, not a promise"
        if card.get("explosion") is not None
        else "  — insufficient history"
    )
    lines = [
        f"### #{card.get('rank')} `{card.get('full_name')}`",
        "",
        f"Opportunity: **{opp}**/100  (confidence: {oconf})",
        f"Explosion: **{exp}**/100  (confidence: {econf}){exp_note}",
        f"Contribution: **{con}**/100  (confidence: {cconf})",
        "",
        "Why now:",
        str(card.get("why_now") or ""),
        "",
        "Five-point analysis:",
        (
            f"① Acceleration: {_comp_why(comps, 'momentum')}. "
            f"is_accelerating={'yes' if 'is_accelerating' in flags else 'no'}."
        ),
        (
            f"② Real users: {_comp_why(comps, 'real_user')}. "
            "Stars are not users; this is issue evidence."
        ),
        f"③ Contributor gap: {_comp_why(comps, 'gap')}.",
        f"④ Contribution opportunity: {_comp_why(comps, 'contribution_opp')}.",
        f"⑤ One-year entry: {_comp_why(comps, 'early_entry')}.",
        "",
        (
            f"Direction Fit: {_pts(card.get('direction_fit'))}%  "
            f"({card.get('direction_topics') or 'unclassified'})"
        ),
        f"Exceptional: {card.get('exceptional') or 'no'}",
        "",
        "Best contribution:",
    ]
    bullets = list(card.get("best_contribution") or [])
    if bullets:
        for i, bullet in enumerate(bullets[:3], 1):
            lines.append(f"{i}. {bullet}")
    else:
        lines.append("No specific help-wanted issues captured this run.")
    lines.append("")
    lines.append("Risk:")
    lines.append(str(card.get("risk") or "H-rules passed."))
    lines.append("")
    eref = card.get("evidence_ref") or {}
    dates = eref.get("snapshot_dates") or {}
    snap = "/".join(k for k in ("t", "t-7", "t-30") if k in dates) or "t"
    spdx = eref.get("license_spdx") or "none"
    captured = eref.get("captured_at") or ""
    lines.append(
        f"Evidence: node_id=`{card.get('node_id')}`; snapshots {snap}; "
        f"SPDX={spdx}; captured_at={captured}"
    )
    lines.append("")
    name = card.get("full_name")
    lines.append("```")
    lines.append(f"foreshadow review {name} interested")
    lines.append(f'foreshadow review {name} enter -m "memory evals"')
    lines.append("```")
    lines.append("")
    return lines


def _active_line(item: Mapping[str, Any]) -> str:
    action = item.get("action") or "enter"
    when = item.get("entered_at") or item.get("created_at") or ""
    when = str(when)[:10]
    stars_e = item.get("stars_at_entry")
    stars_n = item.get("stars_now")
    extra = ""
    if stars_e is not None:
        extra = f" — stars_at_entry={stars_e}"
        if stars_n is not None:
            extra += f", now={stars_n}"
    ranked = " — not ranked" if action == "enter" else ""
    return f"- `{item.get('full_name')}` — **{action}** ({when}){extra}{ranked}"


def _watch_line(item: Mapping[str, Any]) -> str:
    opp = item.get("opportunity")
    mom = item.get("momentum")
    opp_s = f"Opportunity {_pts(opp)}" if opp is not None else "Opportunity NA"
    mom_s = "Momentum **NA**" if mom is None else f"Momentum {_pts(mom)}"
    days = item.get("snapshot_days")
    day_s = f" ({days} snapshot-days)" if days is not None else ""
    action = item.get("action") or "watch"
    return f"- `{item.get('full_name')}` {opp_s}, {mom_s}{day_s} — labeled {action}, not a bet"


def _below_line(item: Mapping[str, Any]) -> str:
    name = item.get("full_name")
    if item.get("kind") == "veto" or item.get("veto_reason"):
        return f"- `{name}` **veto {item.get('veto_reason')}**"
    return f"- `{name}` {item.get('reason')}"


def _source_health_lines(report: ReportJSON) -> list[str]:
    health = report.source_health or {}
    gql = str(health.get("graphql") or "ok")
    if health.get("search_truncated"):
        gql += ", truncated"
    failed = int(health.get("hydrate_failed") or 0)
    v7_na = int(health.get("v7_na") or 0)
    lines = [
        "## Source health",
        f"- graphql search: {gql}",
        f"- hydrate: {failed} failed",
        f"- missing windows: {v7_na}/{report.scored_count} repos have v7=NA",
    ]
    if health.get("observation_panel_size") is not None:
        cov = health.get("v7_coverage_rate")
        cov_s = f"{cov:.1%}" if isinstance(cov, float) else "n/a"
        panel_n = int(health.get("observation_panel_size") or 0)
        watch_n = int(health.get("user_watchlist_count") or 0)
        sys_n = int(health.get("system_observed_count") or 0)
        retained = int(health.get("retained_from_previous_day") or 0)
        v7_n = int(health.get("v7_available") or 0)
        base_n = int(health.get("v7_baseline_eligible_count") or 0)
        expired = int(health.get("observation_expired_count") or 0)
        lines.append(
            f"- observation panel: {panel_n} (watch {watch_n}, system {sys_n})"
        )
        lines.append(
            f"- fresh discovery: {int(health.get('fresh_discovery_count') or 0)}"
        )
        ov = health.get("daily_overlap_rate")
        ov_s = f"{ov}" if ov is not None else "n/a"
        lines.append(f"- retained from previous day: {retained} (overlap {ov_s})")
        lines.append(
            f"- v7 coverage: {v7_n}/{report.scored_count} ({cov_s}); "
            f"t-7 baseline eligible {base_n}"
        )
        lines.append(
            f"- explosion available: {int(health.get('explosion_available') or 0)}"
        )
        lines.append(f"- observation expired (this run): {expired}")
    lines.append("")
    return lines


def _components(bd: ScoreBreakdown) -> dict[str, Any]:
    keys = (
        "momentum",
        "real_user",
        "gap",
        "contribution_opp",
        "early_entry",
        "direction_fit",
        "maintainer",
        "opportunity",
        "explosion",
        "contribution",
    )
    return {key: getattr(bd, key).model_dump() for key in keys}


def _help_bullets(feat: Mapping[str, Any]) -> list[str]:
    from foreshadow.models import FeaturesBlob
    from foreshadow.pipeline.strategy import recommend_entry

    bullets: list[str] = []
    for title in feat.get("help_issue_titles") or []:
        raw = str(title)
        lower = raw.lower()
        kind = ""
        if "doc" in lower:
            kind = " — docs, medium impact"
        elif "test" in lower or "overflow" in lower:
            kind = " — tests"
        bullets.append(f"{raw}{kind}")
    if feat.get("gap_docs") or feat.get("gap_tests") or feat.get("gap_ci"):
        try:
            blob = FeaturesBlob.model_validate(dict(feat))
        except (TypeError, ValueError):
            blob = FeaturesBlob()
        strat = recommend_entry(blob)
        bullets.append(strat.summary_zh)
    return bullets[:3]


def _topic_label(topics: Sequence[Any]) -> str:
    kept = [str(t) for t in topics if str(t).lower() not in _LANG_TOPICS]
    return " / ".join(kept[:3])


def _snapshot_dates(repo: Mapping[str, Any], today: str) -> dict[str, str]:
    have = {str(item.get("date") or "")[:10] for item in repo.get("snapshots") or []}
    have.discard("")
    out: dict[str, str] = {}
    if today in have:
        out["t"] = today
    try:
        day = date.fromisoformat(today)
    except ValueError:
        return out
    t7 = (day - timedelta(days=7)).isoformat()
    t30 = (day - timedelta(days=30)).isoformat()
    if t7 in have:
        out["t-7"] = t7
    if t30 in have:
        out["t-30"] = t30
    return out


def _card_date(repo: Mapping[str, Any], captured_at: str | None) -> str:
    if captured_at:
        return str(captured_at)[:10]
    snaps = list(repo.get("snapshots") or [])
    if snaps:
        ordered = sorted(snaps, key=lambda item: str(item.get("date") or ""))
        return str(ordered[-1].get("date") or "")[:10]
    return datetime.now(UTC).date().isoformat()


def _pts(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return str(round(float(value)))
    except (TypeError, ValueError):
        return "NA"


def _comp_why(comps: Mapping[str, Any], key: str) -> str:
    body = comps.get(key) or {}
    if isinstance(body, Mapping):
        return str(body.get("why") or "NA")
    return "NA"


def _comp_conf(comps: Mapping[str, Any], key: str) -> str:
    body = comps.get(key) or {}
    if isinstance(body, Mapping) and body.get("confidence"):
        return str(body["confidence"])
    return "low"


def _late(stars: float, contributors: float) -> bool:
    return (
        (stars >= 5_000 and contributors >= 30) or stars >= 20_000 or contributors >= 80
    )


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _show_num(value: Any) -> str:
    if value is None:
        return "NA"
    return str(value)


def _pretty(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)
