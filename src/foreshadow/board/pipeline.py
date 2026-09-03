from __future__ import annotations

import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as date_cls
from pathlib import Path
from typing import Any

from foreshadow.board.chair import ChairOverride, chair_decide, exclusion_reason
from foreshadow.board.dimensions import (
    dimensions_from_breakdown,
    evidence_from_scored,
    growth_signal,
    lightweight_score,
)
from foreshadow.board.html import render_board_html
from foreshadow.board.reviewers import run_three_reviewers
from foreshadow.board.schema import BoardCard, BoardDocument, IntroSource, PoolRow
from foreshadow.clock import Clock
from foreshadow.config import BoardSettings, ScoringSettings, Settings, load_config
from foreshadow.db import connect, migrate
from foreshadow.models import FeaturesBlob
from foreshadow.paths import resolve_data_dir
from foreshadow.pipeline import load_score_input
from foreshadow.pipeline.access import compute_access
from foreshadow.pipeline.activity import compute_activity
from foreshadow.pipeline.direction import load_direction_bags, score_direction
from foreshadow.pipeline.hydrate import parse_dt
from foreshadow.pipeline.observation import load_active
from foreshadow.pipeline.s1 import compute_s1
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.select import is_official_eligible
from foreshadow.pipeline.strategy import recommend_entry
from foreshadow.reviews import ACTIONS

_ACTIONS = ACTIONS


def _review_commands(full_name: str) -> dict[str, str]:
    return {
        action: f"uv run foreshadow review {full_name} {action}" for action in _ACTIONS
    }


def _why_now_text(row: ScoredRepo, extra_meta: dict[str, Any]) -> str | None:
    """Prefer scored why_now; else real strategy reasons. Never invent."""
    if row.why_now:
        return str(row.why_now)
    reasons = extra_meta.get("strategy_why") or []
    bits = [str(item).strip() for item in reasons if str(item).strip()]
    if bits:
        return "；".join(bits)
    headline = extra_meta.get("headline")
    if headline:
        return str(headline)
    return None


_SUMMARY_MISSING = "信息不足，无法写简介。"
_FEATURE_SUMMARY_KEYS = (
    "u_issue",
    "u_issue_ext",
    "issue_sample_n",
    "i_open",
    "bug_n",
    "talk_n",
    "help_n",
    "unassigned_help",
    "pr_merged_sample_n",
    "pr_external_merged_n",
    "pr_accept_rate",
    "pr_review_rate",
    "pr_reviewed_n",
    "maint_touch",
    "maint_first_response_hours",
    "data_completeness",
    "phase",
    "commits_7d",
    "commits_30d",
    "recent_contributors_7d",
    "releases_30d",
    "openness",
    "openness_sample_n",
)


def _creator_blob(feat_map: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(feat_map, dict):
        return None
    for key in ("creator", "owner"):
        raw = feat_map.get(key)
        if isinstance(raw, dict) and raw:
            return raw
    return None


def _creator_stats_from_features(feat_map: dict[str, Any]) -> dict[str, Any] | None:
    past = feat_map.get("creator_repo_n")
    maintained = feat_map.get("creator_success_n")
    longest = feat_map.get("creator_longest_maintained_days")
    if past is None and maintained is None and longest is None:
        return None
    return {
        "login": feat_map.get("owner_login") or feat_map.get("owner"),
        "past_public_repos": past,
        "successful_repos": maintained,
        "maintained_repos": maintained,
        "longest_maintained_days": longest,
        "maintained_label_zh": "持续维护项目",
    }


def _features_summary(feat_map: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _FEATURE_SUMMARY_KEYS:
        if key in feat_map:
            out[key] = feat_map[key]
    for key in ("owner", "creator", "openness_stats", "creator_stats"):
        raw = feat_map.get(key)
        if isinstance(raw, dict) and raw:
            out[key] = raw
    return out


def _clip_summary(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        return text.strip()
    return "\n".join(lines[:4])


def _intel_as_dict(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        data = dump()
        return data if isinstance(data, dict) else {}
    raw = getattr(result, "__dict__", None)
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if not str(k).startswith("_")}
    return {}


def _try_score_intel(extra: dict[str, Any]) -> dict[str, Any]:
    try:
        from foreshadow.pipeline.intel import score_intel
    except ImportError:
        return {}
    snapshot_count = extra.get("snapshot_count")
    features = extra.get("features")
    attempts = (
        lambda: score_intel(extra, snapshot_count=snapshot_count),
        lambda: score_intel(features or extra, snapshot_count=snapshot_count),
        lambda: score_intel(extra),
        lambda: score_intel(features or extra),
    )
    for attempt in attempts:
        try:
            return _intel_as_dict(attempt())
        except TypeError:
            continue
        except (ValueError, AttributeError, KeyError, RuntimeError):
            return {}
    return {}


def _dict_or_none(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict) and raw:
        return raw
    return None


def _thesis_of(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out or None


def _intel_payload(extra: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    features = extra.get("features")
    has_features = isinstance(features, dict) and bool(features)
    stored = extra.get("intel")
    has_stored = isinstance(stored, dict) and (
        stored.get("eev") is not None
        or stored.get("potential") is not None
        or stored.get("entry_fit") is not None
    )
    if not has_stored and (has_features or extra.get("snapshot_count") is not None):
        payload.update(_try_score_intel(extra))
    raw = stored
    if isinstance(raw, dict):
        payload.update(raw)
    if not isinstance(payload.get("creator_stats"), dict):
        creator = extra.get("creator_stats") or extra.get("creator")
        if isinstance(creator, dict):
            payload["creator_stats"] = creator
        elif has_features:
            blob = _creator_blob(features) or _creator_stats_from_features(features)
            if blob:
                payload["creator_stats"] = blob
    if not isinstance(payload.get("openness_stats"), dict):
        stats = extra.get("openness_stats")
        if isinstance(stats, dict):
            payload["openness_stats"] = stats
        elif has_features:
            feat_stats = features.get("openness_stats")
            if isinstance(feat_stats, dict):
                payload["openness_stats"] = feat_stats
    if not isinstance(payload.get("thesis"), dict):
        thesis = extra.get("thesis")
        if isinstance(thesis, dict):
            payload["thesis"] = thesis
    if payload.get("openness_sample_n") is None:
        stats = payload.get("openness_stats")
        if isinstance(stats, dict):
            payload["openness_sample_n"] = stats.get("sample_n") or stats.get("n")
        elif has_features:
            payload["openness_sample_n"] = features.get("openness_sample_n")
    return payload


def _extractive_summary(
    extra: dict[str, Any],
    *,
    description: Any,
    intro_zh: str | None,
) -> tuple[str, str | None] | None:
    try:
        from foreshadow.pipeline.summary import summarize_project
    except ImportError:
        return None
    try:
        result = summarize_project(
            description=_nonempty(description) or _nonempty(intro_zh),
            readme=_nonempty(extra.get("readme_excerpt")),
            topics=_topics_of(extra) or None,
            source_sha=None,
        )
    except TypeError:
        return None
    text = getattr(result, "text", None)
    if not _nonempty(text):
        return None
    source = getattr(result, "source", None)
    if text == _SUMMARY_MISSING:
        return text, None
    return text, str(source) if source else "description"


def _project_summary_fields(
    extra: dict[str, Any],
    *,
    description: Any,
    intro_zh: str | None,
    intel_summary: Any = None,
    intel_source: Any = None,
) -> tuple[str, str | None]:
    feat = extra.get("features") if isinstance(extra.get("features"), dict) else {}
    candidates = (
        (_nonempty(intel_summary), _nonempty(intel_source) or "intel"),
        (
            _nonempty(extra.get("project_summary")),
            _nonempty(extra.get("summary_source")) or "extra",
        ),
        (
            _nonempty(extra.get("summary")),
            _nonempty(extra.get("summary_source")) or "extra",
        ),
        (_nonempty(feat.get("summary")) if feat else None, "features"),
    )
    for text, source in candidates:
        if text:
            return _clip_summary(text), source
    extracted = _extractive_summary(extra, description=description, intro_zh=intro_zh)
    if extracted is not None:
        return extracted
    desc = _nonempty(description) or _nonempty(intro_zh)
    if desc:
        return _clip_summary(desc), "description"
    return _SUMMARY_MISSING, None


def _intel_card_kwargs(extra: dict[str, Any]) -> dict[str, Any]:
    payload = _intel_payload(extra)
    high = payload.get("intel_high_confidence")
    if high is None:
        high = payload.get("high_confidence")
    decision = payload.get("intel_decision")
    if decision is None:
        decision = payload.get("decision")
    sample = payload.get("openness_sample_n")
    return {
        "potential": _float_or_none(payload.get("potential")),
        "creator_prior": _float_or_none(payload.get("creator_prior")),
        "openness": _float_or_none(payload.get("openness")),
        "entry_fit": _float_or_none(payload.get("entry_fit")),
        "eev": _float_or_none(payload.get("eev")),
        "potential_confidence": _conf_or_none(payload.get("potential_confidence")),
        "creator_confidence": _conf_or_none(
            payload.get("creator_confidence") or payload.get("creator_prior_confidence")
        ),
        "openness_confidence": _conf_or_none(payload.get("openness_confidence")),
        "entry_fit_confidence": _conf_or_none(payload.get("entry_fit_confidence")),
        "eev_confidence": _conf_or_none(payload.get("eev_confidence")),
        "openness_sample_n": _int_or_none(sample),
        "intel_decision": _nonempty(decision),
        "intel_high_confidence": bool(high),
        "project_summary": _nonempty(payload.get("project_summary")),
        "summary_source": _nonempty(payload.get("summary_source")),
        "creator_stats": _dict_or_none(payload.get("creator_stats")),
        "openness_stats": _dict_or_none(payload.get("openness_stats")),
        "thesis": _thesis_of(payload.get("thesis")),
    }


def _eev_rank_key(card: BoardCard) -> tuple:
    """Homepage order: EEV present first, then value, then chair score."""
    return (
        card.eev is None,
        -(card.eev if card.eev is not None else 0.0),
        -(card.final_score or -1.0),
        -(card.trend.score or -1.0),
        -(card.contributor.score or -1.0),
        card.full_name,
    )


def _load_observation_events(
    conn: sqlite3.Connection, repo_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    if not repo_ids:
        return {}
    unique = list(dict.fromkeys(int(rid) for rid in repo_ids))
    placeholders = ",".join("?" * len(unique))
    try:
        rows = conn.execute(
            f"""
            SELECT repo_id, occurred_on, kind, payload_json
            FROM observation_events
            WHERE repo_id IN ({placeholders})
            ORDER BY occurred_on ASC, kind ASC
            """,
            unique,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[int, list[dict[str, Any]]] = {}
    for repo_id, occurred_on, kind, payload_json in rows:
        payload: Any = {}
        if payload_json:
            try:
                parsed = json.loads(payload_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = {}
            if isinstance(parsed, dict):
                payload = parsed
        out.setdefault(int(repo_id), []).append(
            {
                "occurred_on": occurred_on,
                "kind": kind,
                "payload": payload,
            }
        )
    return out


def _card(
    row: ScoredRepo,
    *,
    html_url: str | None,
    stars: int | None,
    settings: BoardSettings,
    override: ChairOverride | None = None,
    extra: dict[str, Any] | None = None,
) -> BoardCard:
    dims = dimensions_from_breakdown(row.breakdown)
    evidence = evidence_from_scored(row)
    trend, community, contributor = run_three_reviewers(dims, evidence, settings)
    chair = chair_decide(
        trend,
        community,
        contributor,
        settings,
        override=override,
        veto_reason=row.breakdown.veto_reason if row.breakdown.vetoed else None,
    )
    mom_na = row.breakdown.momentum.value is None
    suggested = None
    titles = (row.evidence or {}).get("help_issue_titles") or []
    if isinstance(titles, list) and titles:
        suggested = str(titles[0])
    elif extra and extra.get("strategy_why"):
        why0 = extra.get("strategy_why")
        if isinstance(why0, list) and why0:
            suggested = str(why0[0])
    elif row.contribution_bullets:
        suggested = row.contribution_bullets[0]
    extra_meta = extra or {}
    description = extra_meta.get("description")
    intro_zh, intro_source = _intro_fields(
        description, extra_meta.get("readme_excerpt")
    )
    match_score, match_reasons = _direction_match(
        description=description,
        language=extra_meta.get("language"),
        topics=_topics_of(extra_meta),
    )
    intel_kw = _intel_card_kwargs(extra_meta)
    summary, summary_source = _project_summary_fields(
        extra_meta,
        description=description,
        intro_zh=intro_zh,
        intel_summary=intel_kw.get("project_summary"),
        intel_source=intel_kw.get("summary_source"),
    )
    intel_kw["project_summary"] = summary
    intel_kw["summary_source"] = summary_source
    return BoardCard(
        full_name=row.full_name,
        owner=row.owner,
        html_url=html_url or extra_meta.get("html_url"),
        stars=stars if stars is not None else extra_meta.get("stars"),
        forks=extra_meta.get("forks"),
        contributors=extra_meta.get("contributors"),
        open_issues=extra_meta.get("open_issues"),
        last_pushed_at=extra_meta.get("last_pushed_at"),
        last_release=extra_meta.get("last_release"),
        first_seen_at=extra_meta.get("first_seen_at"),
        description=description,
        intro_zh=intro_zh,
        intro_source=intro_source,
        match_score=match_score,
        match_reasons=match_reasons,
        language=extra_meta.get("language"),
        official_eligible=is_official_eligible(row),
        lightweight_score=lightweight_score(dims),
        trend=trend,
        community=community,
        contributor=contributor,
        chair=chair,
        final_score=chair.score,
        dimensions=chair.dimensions,
        evidence=evidence,
        why_now=_why_now_text(row, extra_meta),
        suggested_contribution=suggested,
        observation_age_days=_int_or_none(extra_meta.get("observation_age_days")),
        observation_reason=(
            str(extra_meta["observation_reason"])
            if extra_meta.get("observation_reason")
            else None
        ),
        p0_opportunity=row.breakdown.opportunity.value,
        p0_explosion=row.breakdown.explosion.value,
        p0_contribution=row.breakdown.contribution.value,
        p0_confidence=row.breakdown.opportunity.confidence,
        data_completeness=_completeness_of(extra_meta),
        activity_momentum=_float_or_none(extra_meta.get("activity_momentum")),
        activity_class=(
            str(extra_meta["activity_class"])
            if extra_meta.get("activity_class")
            else None
        ),
        activity_confidence=_conf_or_none(extra_meta.get("activity_confidence")),
        activity_concentration=_float_or_none(extra_meta.get("activity_concentration")),
        commits_7d=_int_or_none(extra_meta.get("commits_7d")),
        commits_30d=_int_or_none(extra_meta.get("commits_30d")),
        releases_30d=_int_or_none(extra_meta.get("releases_30d")),
        recent_contributors_7d=_int_or_none(extra_meta.get("recent_contributors_7d")),
        s1_stage=extra_meta.get("s1_stage"),
        s1_earlyness=_float_or_none(extra_meta.get("s1_earlyness")),
        s1_evidence=_float_or_none(extra_meta.get("s1_evidence")),
        s1_window=_float_or_none(extra_meta.get("s1_window")),
        s1_pool=extra_meta.get("s1_pool"),
        s1_quadrant=extra_meta.get("s1_quadrant"),
        s1_earlyness_plus=list(extra_meta.get("s1_earlyness_plus") or []),
        s1_earlyness_minus=list(extra_meta.get("s1_earlyness_minus") or []),
        s1_evidence_plus=list(extra_meta.get("s1_evidence_plus") or []),
        s1_evidence_minus=list(extra_meta.get("s1_evidence_minus") or []),
        access_score=_float_or_none(extra_meta.get("access_score")),
        access_class=extra_meta.get("access_class"),
        access_merge_rate=_float_or_none(extra_meta.get("access_merge_rate")),
        access_review_rate=_float_or_none(extra_meta.get("access_review_rate")),
        strategy_path=extra_meta.get("strategy_path"),
        strategy_summary_zh=extra_meta.get("strategy_summary_zh"),
        strategy_steps_zh=list(extra_meta.get("strategy_steps_zh") or []),
        strategy_difficulty=extra_meta.get("strategy_difficulty"),
        strategy_effort=extra_meta.get("strategy_effort"),
        strategy_long_term=extra_meta.get("strategy_long_term")
        if isinstance(extra_meta.get("strategy_long_term"), dict)
        else None,
        strategy_why=list(extra_meta.get("strategy_why") or []),
        momentum_na=mom_na,
        vetoed=row.breakdown.vetoed,
        veto_reason=row.breakdown.veto_reason,
        review_commands=_review_commands(row.full_name),
        **intel_kw,
    )


def assemble_board(
    scored: list[ScoredRepo],
    *,
    date: str,
    preview: bool,
    snapshot_days: int,
    meta: dict[str, Any] | None = None,
    settings: BoardSettings | None = None,
    scoring: ScoringSettings | None = None,
    extras: dict[str, dict[str, Any]] | None = None,
    chair_overrides: dict[str, ChairOverride] | None = None,
) -> BoardDocument:
    settings = settings or BoardSettings()
    scoring = scoring or ScoringSettings()
    extras = extras or {}
    chair_overrides = chair_overrides or {}
    meta = meta or {}

    pool: list[PoolRow] = []
    shortlist_src: list[ScoredRepo] = []
    for row in scored:
        if not row.breakdown.vetoed:
            shortlist_src.append(row)

    def _lw(row: ScoredRepo) -> float:
        dims = dimensions_from_breakdown(row.breakdown)
        return lightweight_score(dims) or -1.0

    shortlist_src.sort(key=_lw, reverse=True)
    shortlist_src = shortlist_src[: settings.shortlist_n]
    short_names = {r.full_name for r in shortlist_src}

    # Review shortlist in parallel (each call already parallelizes the 3 reviewers).
    short_cards: list[BoardCard] = []
    with ThreadPoolExecutor(max_workers=8) as pool_ex:
        futs = {
            pool_ex.submit(
                _card,
                row,
                html_url=(extras.get(row.full_name) or {}).get("html_url"),
                stars=(extras.get(row.full_name) or {}).get("stars"),
                settings=settings,
                override=chair_overrides.get(row.full_name),
                extra=extras.get(row.full_name) or {},
            ): row.full_name
            for row in shortlist_src
        }
        by_name: dict[str, BoardCard] = {}
        for fut in as_completed(futs):
            card = fut.result()
            by_name[card.full_name] = card
    short_cards = [
        by_name[r.full_name] for r in shortlist_src if r.full_name in by_name
    ]

    ranked = sorted(short_cards, key=_eev_rank_key)
    for i, card in enumerate(ranked, start=1):
        card.list_rank = i
    deep = ranked[: settings.deep_review_n]
    deep_scores = [c.final_score for c in deep if c.final_score is not None]
    fifth = None
    if len(deep_scores) >= settings.final_n:
        fifth = sorted(deep_scores, reverse=True)[settings.final_n - 1]

    for card in ranked:
        card.chair.exclusion_reason = None
        card.chair.why_selected = None

    provisional = deep[: settings.final_n]
    for card in provisional:
        card.chair.why_selected = (
            card.chair.justification
            or "Chair ranking after three independent reviewers."
        )
    official: list[BoardCard] = []
    by_full = {r.full_name: r for r in scored}
    owners: dict[str, int] = {}
    card_by_name = {c.full_name: c for c in ranked}
    v1_pool = [
        row
        for row in scored
        if is_official_eligible(
            row,
            min_opportunity=scoring.min_opportunity,
            min_explosion=scoring.min_explosion,
        )
    ]
    v1_pool.sort(
        key=lambda row: (
            -(row.breakdown.opportunity.value or 0.0),
            -(row.breakdown.explosion.value or 0.0),
            -(row.breakdown.contribution.value or 0.0),
        )
    )
    for src in v1_pool:
        card = card_by_name.get(src.full_name)
        if card is None:
            continue
        if owners.get(card.owner, 0) >= scoring.max_per_owner:
            continue
        official.append(card)
        owners[card.owner] = owners.get(card.owner, 0) + 1
        if len(official) >= settings.final_n:
            break

    official_names = {c.full_name for c in official}
    provisional_names = {c.full_name for c in provisional}
    for card in deep:
        if card.full_name in official_names or card.full_name in provisional_names:
            continue
        src = by_full.get(card.full_name)
        card.chair.exclusion_reason = exclusion_reason(
            card.dimensions,
            veto_reason=card.veto_reason,
            momentum_na=card.momentum_na,
            final_score=card.final_score,
            fifth_score=fifth,
        )

    any_v7 = any(not c.momentum_na for c in short_cards)
    if preview or not any_v7 or not official:
        mode = "provisional"
        if not any_v7:
            mode_reason = "insufficient v7 history"
        elif preview:
            mode_reason = "preview flag; official gate unchanged"
        else:
            mode_reason = "no repo passed the official v7 + threshold gate"
    else:
        mode = "official"
        mode_reason = "v7 available for official ranking"

    # Pool rows (all discovered)
    scored_sorted = sorted(scored, key=_lw, reverse=True)
    for i, row in enumerate(scored_sorted, start=1):
        extra = extras.get(row.full_name) or {}
        if row.breakdown.vetoed:
            status = "rejected"
            reason = row.breakdown.veto_reason
        elif row.full_name in short_names:
            status = "shortlisted"
            reason = None
        else:
            status = "screened_out"
            reason = "Below shortlist cut (lightweight score)."
        pool.append(
            PoolRow(
                rank=i,
                full_name=row.full_name,
                node_id=extra.get("node_id"),
                stars=extra.get("stars"),
                growth_signal=growth_signal(row),
                status=status,
                vetoed=row.breakdown.vetoed,
                lightweight_score=lightweight_score(
                    dimensions_from_breakdown(row.breakdown)
                ),
                reason=reason,
            )
        )

    return BoardDocument(
        date=date,
        mode=mode,  # type: ignore[arg-type]
        mode_reason=mode_reason,
        discovered=len(scored),
        shortlisted=len(short_cards),
        deep_reviewed=len(deep),
        official_top5=len(official),
        provisional_count=len(provisional),
        pool=pool,
        shortlist=short_cards,
        deep=deep,
        official=official,
        provisional=provisional,
        generated_from="real_snapshots",
        snapshot_days=snapshot_days,
        extra=meta,
    )


def _snapshot_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()
    return int(row[0]) if row else 0


def _observation_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM observations").fetchone()
    return int(row[0]) if row else 0


def _run_meta(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    any_n = int(conn.execute("SELECT COUNT(*) FROM daily_runs").fetchone()[0] or 0)
    row = conn.execute(
        """
        SELECT status, source_health_json, finished_at
        FROM daily_runs
        WHERE run_date=?
        ORDER BY id DESC LIMIT 1
        """,
        (date,),
    ).fetchone()
    health: dict[str, Any] = {}
    status = None
    finished = None
    if row is not None:
        status = str(row[0]) if row[0] is not None else None
        finished = row[2]
        raw = row[1]
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                health = parsed
    return {
        "any_run": any_n > 0,
        "status": status,
        "finished_at": finished,
        "health": health,
    }


def load_scored_from_db(
    conn: sqlite3.Connection,
    date: str,
    clock: Clock,
    settings: Settings,
) -> tuple[list[ScoredRepo], dict[str, dict[str, Any]], int]:
    run = conn.execute(
        """
        SELECT id FROM daily_runs
        WHERE run_date=? AND status IN ('complete','degraded','running')
        ORDER BY id DESC LIMIT 1
        """,
        (date,),
    ).fetchone()
    if run is None:
        return [], {}, 0
    run_id = int(run[0])
    rows = conn.execute(
        """
        SELECT c.repo_id, c.hydrate_status, r.full_name, r.html_url, r.node_id,
               r.first_seen_at, r.description, r.language
        FROM candidates c
        JOIN repos r ON r.id = c.repo_id
        WHERE c.run_id=?
        """,
        (run_id,),
    ).fetchall()
    bags = load_direction_bags()
    scored: list[ScoredRepo] = []
    extras: dict[str, dict[str, Any]] = {}
    extras_by_id: dict[int, str] = {}
    snap_days = 1
    for (
        repo_id,
        status,
        full_name,
        html_url,
        node_id,
        first_seen,
        description,
        language,
    ) in rows:
        if status not in {"ok", "incomplete"}:
            continue
        data = load_score_input(conn, repo_id)
        if data is None:
            continue
        row = score_repo(data, clock=clock, scoring=settings.scoring, bags=bags)
        scored.append(row)
        features = data.get("features") or {}
        feat_map = features if isinstance(features, dict) else {}
        act = compute_activity(feat_map, settings.scoring)
        blob = FeaturesBlob.model_validate(feat_map) if feat_map else FeaturesBlob()
        acc = compute_access(blob)
        now_d = clock.today()
        age_days = data.get("age_days")
        if age_days is None:
            created = parse_dt(data.get("created_at"))
            if created is not None:
                age_days = max((now_d - created.date()).days, 1)
        pushed_age_days = data.get("pushed_age_days")
        if pushed_age_days is None:
            pushed = parse_dt(data.get("pushed_at"))
            if pushed is not None:
                pushed_age_days = max((now_d - pushed.date()).days, 0)
        s1 = compute_s1(
            age_days=age_days,
            contributors=data.get("C"),
            stars=data.get("S"),
            pushed_age_days=pushed_age_days,
            unique_issue_authors=data.get("U_issue") or feat_map.get("u_issue"),
            feat=blob,
            activity=act,
        )
        strat = recommend_entry(
            blob,
            s1=s1,
            access=acc,
            language=language,
            full_name=full_name,
            blurb=description,
        )
        extras[full_name] = {
            "html_url": html_url or data.get("html_url"),
            "stars": data.get("S"),
            "forks": data.get("F"),
            "contributors": data.get("C"),
            "open_issues": data.get("I_open"),
            "last_pushed_at": data.get("pushed_at"),
            "last_release": _last_release(features),
            "first_seen_at": first_seen,
            "description": description,
            "language": language,
            "topics": list(data.get("topics") or []),
            "readme_excerpt": blob.readme_excerpt,
            "node_id": node_id,
            "hydrate_status": status,
            "data_completeness": (
                features.get("data_completeness")
                if isinstance(features, dict)
                else None
            ),
            "activity_momentum": act.momentum,
            "activity_class": act.classification,
            "activity_confidence": act.confidence,
            "activity_concentration": act.concentration,
            "commits_7d": act.commits_7d,
            "commits_30d": act.commits_30d,
            "releases_30d": act.releases_30d,
            "recent_contributors_7d": act.recent_contributors_7d,
            "s1_stage": s1.stage,
            "s1_earlyness": s1.earlyness,
            "s1_evidence": s1.evidence,
            "s1_window": s1.window,
            "s1_pool": s1.pool,
            "s1_quadrant": s1.quadrant,
            "s1_earlyness_plus": s1.earlyness_plus,
            "s1_earlyness_minus": s1.earlyness_minus,
            "s1_evidence_plus": s1.evidence_plus,
            "s1_evidence_minus": s1.evidence_minus,
            "access_score": acc.score,
            "access_class": acc.classification,
            "access_merge_rate": acc.merge_rate,
            "access_review_rate": acc.review_rate,
            "strategy_path": strat.path,
            "strategy_summary_zh": strat.summary_zh,
            "strategy_steps_zh": strat.steps_zh,
            "strategy_difficulty": strat.difficulty,
            "strategy_effort": strat.effort,
            "strategy_long_term": strat.long_term,
            "strategy_why": list(strat.why),
            "features": feat_map,
            "features_summary": _features_summary(feat_map),
            "snapshot_count": len(data.get("snapshots") or []),
            "owner_login": data.get("owner"),
            "creator": _creator_blob(feat_map),
        }
        extras_by_id[int(repo_id)] = full_name
        snap_days = max(snap_days, len(data.get("snapshots") or []))
    try:
        day = date_cls.fromisoformat(date)
    except ValueError:
        day = clock.today()
    for entry in load_active(conn, day):
        extra = extras.get(entry.full_name)
        if extra is None:
            continue
        extra["observation_age_days"] = (
            day - date_cls.fromisoformat(entry.added_on)
        ).days + 1
        extra["observation_reason"] = entry.reason
    events_by_repo = _load_observation_events(conn, list(extras_by_id))
    for repo_id, events in events_by_repo.items():
        name = extras_by_id.get(repo_id)
        extra = extras.get(name) if name else None
        if extra is None:
            continue
        extra["observation_events"] = events
    _attach_intel_scores(conn, date, extras, extras_by_id)
    return scored, extras, snap_days


def _attach_intel_scores(
    conn: sqlite3.Connection,
    date: str,
    extras: dict[str, dict[str, Any]],
    extras_by_id: dict[int, str],
) -> None:
    """Homepage chips and EEV sort must match the daily formula row."""
    if not extras_by_id:
        return
    try:
        rows = conn.execute(
            """
            SELECT s.repo_id, s.score, s.components_json
            FROM intel_scores s
            JOIN model_runs m ON m.id = s.model_run_id
            WHERE s.as_of_date=? AND m.name='formula-v1'
            """,
            (date,),
        ).fetchall()
    except sqlite3.OperationalError:
        return
    for repo_id, score, components_json in rows:
        name = extras_by_id.get(int(repo_id))
        extra = extras.get(name) if name else None
        if extra is None:
            continue
        try:
            data = json.loads(components_json) if components_json else {}
        except (TypeError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        intel = dict(data)
        if intel.get("eev") is None and score is not None:
            intel["eev"] = score
        if intel.get("openness_sample_n") is None and intel.get("sample") is not None:
            intel["openness_sample_n"] = intel.get("sample")
        if intel.get("eev_confidence") is None:
            intel["eev_confidence"] = "high" if intel.get("high_confidence") else "low"
        extra["intel"] = intel


_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG = re.compile(r"</?[^>]+>")


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _topics_of(extra: dict[str, Any]) -> list[str]:
    raw = extra.get("topics")
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, list | tuple):
        return [str(item) for item in raw if item]
    return []


def _intro_fields(
    description: Any, readme_excerpt: Any
) -> tuple[str | None, IntroSource]:
    desc = _nonempty(description)
    if desc:
        return desc, "github"
    para = _first_readme_paragraph(readme_excerpt)
    if para:
        return para, "readme"
    return None, "limited"


def _first_readme_paragraph(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    in_fence = False
    buf: list[str] = []
    paragraphs: list[str] = []

    def flush() -> None:
        if buf:
            paragraphs.append(" ".join(buf))
            buf.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            continue
        if stripped in {"---", "***", "___"}:
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("|"):
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ").strip()
            if not stripped:
                continue
        no_img = _MD_IMAGE.sub("", stripped)
        no_html = _HTML_TAG.sub("", no_img).strip()
        if not no_html:
            continue
        cleaned = _strip_md_line(stripped)
        if not cleaned:
            continue
        buf.append(cleaned)
    flush()
    for para in paragraphs:
        cleaned = " ".join(para.split())
        if _meaningful_intro(cleaned):
            return cleaned
    return None


def _strip_md_line(line: str) -> str:
    text = _MD_IMAGE.sub("", line)
    text = _MD_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = text.replace("**", "").replace("__", "")
    return " ".join(text.split()).strip()


def _meaningful_intro(text: str) -> bool:
    if len(text) < 20:
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    return letters >= 12


def _direction_match(
    *,
    description: Any,
    language: Any,
    topics: list[str] | None,
) -> tuple[int | None, list[str]]:
    desc = _nonempty(description) or ""
    lang = _nonempty(language)
    topic_list = [item for item in (topics or []) if item]
    if not desc and not lang and not topic_list:
        return None, []
    bags = load_direction_bags()
    if not bags:
        return None, []
    score = score_direction(
        name="",
        description=desc,
        topics=topic_list,
        headings=[],
        language=lang,
        bags=bags,
    )
    reasons: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        key = item.strip()
        if not key:
            return
        fold = key.lower()
        if fold in seen:
            return
        seen.add(fold)
        reasons.append(key)

    hay = " ".join([desc, " ".join(topic_list), lang or ""]).lower()
    for bag in bags:
        repo_topics = {t.lower() for t in topic_list}
        bag_topics = {t.lower() for t in bag.topics if t}
        hits: list[str] = sorted(repo_topics & bag_topics)
        for needle in (*bag.topics, *bag.keywords):
            n = (needle or "").strip()
            if n and n.lower() in hay:
                hits.append(needle)
        if lang and any(lang.lower() == item.lower() for item in bag.languages):
            hits.append(lang)
        if hits:
            add(bag.name)
            for hit in hits:
                add(hit)
    return score, reasons


def _completeness_of(extra: dict[str, Any]) -> str | None:
    raw = extra.get("data_completeness")
    if raw in {"high", "medium", "low"}:
        return raw
    return None


def _conf_or_none(raw: Any) -> str | None:
    if raw in {"low", "medium", "high"}:
        return raw
    return None


def _float_or_none(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int_or_none(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _last_release(features: Any) -> str | None:
    if not isinstance(features, dict):
        return None
    for key in ("latest_release", "last_release", "released_at"):
        value = features.get(key)
        if value:
            return str(value)
    return None


def build_board_from_db(
    *,
    date: str,
    preview: bool,
    clock: Clock | None = None,
    settings: Settings | None = None,
) -> tuple[BoardDocument, int, int]:
    """Returns (board, snapshots_before, snapshots_after). After must equal before."""
    clock = clock or Clock()
    settings = settings or load_config()
    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    conn = connect(db_path)
    migrate(conn)
    before = _snapshot_count(conn)
    obs_before = _observation_count(conn)
    scored, extras, snap_days = load_scored_from_db(conn, date, clock, settings)
    board = assemble_board(
        scored,
        date=date,
        preview=preview,
        snapshot_days=snap_days,
        meta={"run": _run_meta(conn, date)},
        settings=settings.board,
        scoring=settings.scoring,
        extras=extras,
    )
    after = _snapshot_count(conn)
    obs_after = _observation_count(conn)
    if obs_before != obs_after:
        raise RuntimeError("board run mutated observations")
    return board, before, after


def write_board(board: BoardDocument, *, preview: bool) -> tuple[Path, Path]:
    root = resolve_data_dir()
    folder = root / ("preview" if preview else "reports")
    if preview:
        folder = folder / board.date
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / ("board.json" if preview else f"{board.date}.board.json")
    html_path = folder / ("board.html" if preview else f"{board.date}.html")
    payload = board.model_dump()
    json_path.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    html_path.write_text(render_board_html(board), encoding="utf-8")
    return json_path, html_path
