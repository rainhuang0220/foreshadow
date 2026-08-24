from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from foreshadow.board.schema import BoardCard, BoardDocument, PoolRow
from foreshadow.clock import Clock
from foreshadow.config import BoardSettings, ScoringSettings, Settings, load_config
from foreshadow.db import connect, migrate
from foreshadow.paths import resolve_data_dir
from foreshadow.pipeline import load_score_input
from foreshadow.pipeline.direction import load_direction_bags
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.select import is_official_eligible
from foreshadow.reviews import ACTIONS

_ACTIONS = ACTIONS


def _review_commands(full_name: str) -> dict[str, str]:
    return {
        action: f"uv run foreshadow review {full_name} {action}" for action in _ACTIONS
    }


def _card(
    row: ScoredRepo,
    *,
    html_url: str | None,
    stars: int | None,
    settings: BoardSettings,
    override: ChairOverride | None = None,
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
    elif row.contribution_bullets:
        suggested = row.contribution_bullets[0]
    return BoardCard(
        full_name=row.full_name,
        owner=row.owner,
        html_url=html_url,
        stars=stars,
        official_eligible=is_official_eligible(row),
        lightweight_score=lightweight_score(dims),
        trend=trend,
        community=community,
        contributor=contributor,
        chair=chair,
        final_score=chair.score,
        dimensions=chair.dimensions,
        evidence=evidence,
        why_now=row.why_now,
        suggested_contribution=suggested,
        p0_opportunity=row.breakdown.opportunity.value,
        p0_explosion=row.breakdown.explosion.value,
        p0_contribution=row.breakdown.contribution.value,
        momentum_na=mom_na,
        vetoed=row.breakdown.vetoed,
        veto_reason=row.breakdown.veto_reason,
        review_commands=_review_commands(row.full_name),
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

    ranked = sorted(
        short_cards,
        key=lambda c: (
            -(c.final_score or -1.0),
            -(c.trend.score or -1.0),
            -(c.contributor.score or -1.0),
        ),
    )
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
    for card in deep:
        src = by_full.get(card.full_name)
        if src is None:
            continue
        if not is_official_eligible(
            src,
            min_opportunity=scoring.min_opportunity,
            min_explosion=scoring.min_explosion,
        ):
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
        SELECT c.repo_id, c.hydrate_status, r.full_name, r.html_url, r.node_id
        FROM candidates c
        JOIN repos r ON r.id = c.repo_id
        WHERE c.run_id=?
        """,
        (run_id,),
    ).fetchall()
    bags = load_direction_bags()
    scored: list[ScoredRepo] = []
    extras: dict[str, dict[str, Any]] = {}
    snap_days = 1
    for repo_id, status, full_name, html_url, node_id in rows:
        if status not in {"ok", "incomplete"}:
            continue
        data = load_score_input(conn, repo_id)
        if data is None:
            continue
        row = score_repo(data, clock=clock, scoring=settings.scoring, bags=bags)
        scored.append(row)
        extras[full_name] = {
            "html_url": html_url,
            "stars": data.get("S"),
            "node_id": node_id,
            "hydrate_status": status,
        }
        snap_days = max(snap_days, len(data.get("snapshots") or []))
    return scored, extras, snap_days


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
    scored, extras, snap_days = load_scored_from_db(conn, date, clock, settings)
    board = assemble_board(
        scored,
        date=date,
        preview=preview,
        snapshot_days=snap_days,
        settings=settings.board,
        scoring=settings.scoring,
        extras=extras,
    )
    after = _snapshot_count(conn)
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
