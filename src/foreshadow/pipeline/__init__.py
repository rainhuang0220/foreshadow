"""Pipeline stages and daily orchestration."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import (
    Settings,
    ensure_default_config,
    load_config,
    user_config_path,
)
from foreshadow.db import connect, migrate
from foreshadow.lock import official_run_lock
from foreshadow.models import ReportJSON
from foreshadow.paths import resolve_data_dir
from foreshadow.pipeline.compare import (
    assign_pool_ranks,
    assign_pool_ranks_v2,
    identity_key,
    rank_delta,
)
from foreshadow.pipeline.discover import (
    discover_hydrate_snapshot,
    is_degraded,
    load_watchlist,
)
from foreshadow.pipeline.obs_events import (
    record_potential_ups_for_today,
    record_today_observation_events,
)
from foreshadow.pipeline.observation import (
    admit_from_scores,
    count_states,
    load_active,
    mark_observed,
    v7_eligible_count,
    yesterday_overlap,
)
from foreshadow.pipeline.report import (
    build_report,
    format_run_summary,
    format_show,
    render_json,
    render_markdown,
    write_reports,
)
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2
from foreshadow.pipeline.select import select_top

__all__ = [
    "FINISHED_RUN_STATUSES",
    "RunResult",
    "discover_hydrate_snapshot",
    "is_degraded",
    "render_json",
    "render_markdown",
    "run_pipeline",
    "show_repo",
]

FINISHED_RUN_STATUSES = frozenset({"complete", "degraded"})


@dataclass
class RunResult:
    status: str
    report_path: Path | None
    top5_count: int
    skipped: bool = False
    discovered: int = 0
    hydrated: int = 0
    scored: int = 0
    snapshot_days: int = 0
    source_health: dict[str, Any] = field(default_factory=dict)
    review_repo: str = "owner/repo"
    summary: str = ""
    report: ReportJSON | None = None
    skip_reason: str | None = None


def run_pipeline(
    *,
    clock: Clock,
    force: bool,
    llm: bool,
    client: Any = None,
    settings: Settings | None = None,
) -> RunResult:
    cfg_path = user_config_path()
    wrote = None
    if not cfg_path.exists():
        ensure_default_config(cfg_path)
        wrote = str(cfg_path)
    else:
        ensure_default_config(cfg_path)
    loaded = settings or load_config()
    if llm:
        loaded = loaded.model_copy(deep=True)
        loaded.llm.enabled = True

    data_dir = resolve_data_dir()
    today = clock.today()
    today_s = today.isoformat()

    with official_run_lock(data_dir, blocking=False) as got_lock:
        if not got_lock:
            return _locked_result(today_s)

        db_path = data_dir / "foreshadow.sqlite3"
        conn = connect(db_path)
        migrate(conn)
        skipped = _skip_finished_run(conn, data_dir, today_s, force=force)
        if skipped is not None:
            return skipped

        created_client = False
        if client is None:
            from foreshadow.github.client import GitHubClient, resolve_token

            client = GitHubClient(
                token=resolve_token(),
                settings=loaded.github,
                clock=clock,
                force=force,
            )
            created_client = True

        try:
            return _run(
                conn,
                client,
                loaded,
                clock=clock,
                force=force,
                data_dir=data_dir,
                wrote_config=wrote,
            )
        except Exception as exc:
            _mark_run_unfinished(conn, clock, today_s, exc, failed=True)
            raise
        except BaseException:
            _mark_run_unfinished(conn, clock, today_s, None, failed=False)
            raise
        finally:
            if created_client and hasattr(client, "close"):
                client.close()


def _locked_result(today_s: str) -> RunResult:
    result = RunResult(
        status="locked",
        report_path=None,
        top5_count=0,
        skipped=True,
        skip_reason="locked",
    )
    result.summary = (
        f"Foreshadow {today_s}\n"
        "daily run already in progress\n"
        "next: foreshadow status\n"
    )
    return result


def _skip_finished_run(
    conn: sqlite3.Connection,
    data_dir: Path,
    today_s: str,
    *,
    force: bool,
) -> RunResult | None:
    """Skip a second Official run on the same UTC date unless --force.

    complete and degraded both count as finished. failed / running retry.
    """
    existing = conn.execute(
        """
        SELECT status, report_path, top5_count, candidate_count, scored_count,
               source_health_json
        FROM daily_runs WHERE run_date=?
        """,
        (today_s,),
    ).fetchone()
    if existing is None:
        return None
    report_file = (
        Path(existing[1]) if existing[1] else data_dir / "reports" / f"{today_s}.md"
    )
    if existing[0] not in FINISHED_RUN_STATUSES or force or not report_file.is_file():
        return None
    health = _as_dict(existing[5])
    snap_days = _snapshot_days(conn)
    result = RunResult(
        status=str(existing[0]),
        report_path=report_file,
        top5_count=int(existing[2] or 0),
        skipped=True,
        skip_reason="same_day",
        discovered=int(existing[3] or 0),
        scored=int(existing[4] or 0),
        snapshot_days=snap_days,
        source_health=health,
    )
    result.summary = format_run_summary(
        date=today_s,
        discovered=result.discovered,
        hydrated=result.discovered,
        scored=result.scored,
        selected=result.top5_count,
        status=result.status,
        health=health,
        snapshot_days=snap_days,
        report_path=result.report_path,
        skipped=True,
    )
    return result


def _mark_run_unfinished(
    conn: sqlite3.Connection,
    clock: Clock,
    today_s: str,
    exc: BaseException | None,
    *,
    failed: bool,
) -> None:
    from foreshadow.github.client import redact

    try:
        if failed:
            detail = redact(str(exc) if exc is not None else "error")[:500]
            conn.execute(
                """
                UPDATE daily_runs
                SET status='failed', error=?, finished_at=?
                WHERE run_date=?
                """,
                (detail, clock.now().isoformat(), today_s),
            )
        else:
            conn.execute(
                """
                UPDATE daily_runs
                SET status='running', finished_at=NULL, report_path=NULL
                WHERE run_date=?
                """,
                (today_s,),
            )
        conn.commit()
    except sqlite3.Error:
        pass


def show_repo(ref: str) -> str | None:
    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    if not db_path.is_file():
        return None
    conn = connect(db_path)
    migrate(conn)
    repo = _resolve_local(conn, ref)
    if repo is None:
        return None
    repo_id, node_id, full_name, html_url = repo
    score = conn.execute(
        """
        SELECT opportunity, explosion, contribution, confidence,
               components_json, evidence_json, flags_json
        FROM scores
        WHERE repo_id=? AND score_version='v1'
        ORDER BY scored_at DESC, id DESC LIMIT 1
        """,
        (repo_id,),
    ).fetchone()
    score_map = None
    if score is not None:
        score_map = {
            "opportunity": score[0],
            "explosion": score[1],
            "contribution": score[2],
            "confidence": score[3],
            "components": score[4],
            "evidence": score[5],
            "flags": score[6],
        }
    snaps = conn.execute(
        """
        SELECT snapshot_date, stars, forks, contributor_count
        FROM snapshots WHERE repo_id=?
        ORDER BY snapshot_date DESC LIMIT 7
        """,
        (repo_id,),
    ).fetchall()
    from foreshadow.auth import ensure_local_user

    op_id = ensure_local_user(conn)
    reviews = conn.execute(
        """
        SELECT created_at, action, note FROM reviews
        WHERE repo_id=? AND (user_id=? OR user_id IS NULL)
        ORDER BY id DESC
        """,
        (repo_id, op_id),
    ).fetchall()
    entry_row = conn.execute(
        """
        SELECT entered_at, stars_at_entry, contributors_at_entry,
               opportunity_at_entry, explosion_at_entry, contribution_at_entry,
               scores_at_entry_json, note
        FROM entries WHERE repo_id=?
        """,
        (repo_id,),
    ).fetchone()
    entry = None
    if entry_row is not None:
        entry = {
            "entered_at": entry_row[0],
            "stars_at_entry": entry_row[1],
            "contributors_at_entry": entry_row[2],
            "opportunity_at_entry": entry_row[3],
            "explosion_at_entry": entry_row[4],
            "contribution_at_entry": entry_row[5],
            "scores_at_entry_json": entry_row[6],
            "note": entry_row[7],
        }
    return format_show(
        full_name=full_name,
        node_id=node_id,
        html_url=html_url,
        score=score_map,
        snapshots=[
            {"date": row[0], "stars": row[1], "forks": row[2], "C": row[3]}
            for row in snaps
        ],
        reviews=[
            {"created_at": row[0], "action": row[1], "note": row[2]} for row in reviews
        ],
        entry=entry,
    )


def _run(
    conn: sqlite3.Connection,
    client: Any,
    settings: Settings,
    *,
    clock: Clock,
    force: bool,
    data_dir: Path,
    wrote_config: str | None,
) -> RunResult:
    print("Discovering and hydrating…", flush=True)
    disc = discover_hydrate_snapshot(conn, client, settings, clock=clock, force=force)
    today = clock.today()
    today_s = today.isoformat()
    health = dict(disc.source_health)
    run_id = disc.run_id
    snap_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT repo_id FROM snapshots WHERE snapshot_date=?", (today_s,)
        )
    ]
    mark_observed(conn, snap_ids, today)
    record_today_observation_events(conn, today)
    conn.execute(
        """
        UPDATE daily_runs
        SET status='running', finished_at=NULL, report_path=NULL
        WHERE id=?
        """,
        (run_id,),
    )
    conn.commit()

    cand_rows = conn.execute(
        """
        SELECT c.repo_id, c.hydrate_status, r.full_name
        FROM candidates c
        JOIN repos r ON r.id = c.repo_id
        WHERE c.run_id=?
        """,
        (run_id,),
    ).fetchall()
    hydrated_n = sum(1 for row in cand_rows if row[1] in {"ok", "incomplete"})
    print(f"Hydrated {hydrated_n}. Scoring…", flush=True)

    bags = None
    scored_rows: list[tuple[int, ScoredRepo, dict[str, Any]]] = []
    scored_v2_rows: list[tuple[int, ScoredRepo, dict[str, Any]]] = []
    blocked = 0
    pool: list[ScoredRepo] = []
    for repo_id, status, _name in cand_rows:
        if status not in {"ok", "incomplete"}:
            continue
        data = load_score_input(conn, repo_id)
        if data is None:
            continue
        if not _has_today_snapshot(data, today_s):
            continue
        scored = score_repo(data, clock=clock, scoring=settings.scoring, bags=bags)
        scored_v2 = score_repo_v2(
            data, clock=clock, scoring=settings.scoring, bags=bags
        )
        scored_rows.append((repo_id, scored, data))
        scored_v2_rows.append((repo_id, scored_v2, data))
        if _review_blocked(conn, repo_id, today, settings.scoring):
            blocked += 1
            continue
        pool.append(scored)

    now_iso = clock.now().isoformat()
    v1_ranks = assign_pool_ranks([(s, d) for _, s, d in scored_rows])
    v2_ranks = assign_pool_ranks_v2([(s, d) for _, s, d in scored_v2_rows])
    for repo_id, scored, data in scored_rows:
        key = identity_key(scored, data)
        _insert_score(
            conn,
            run_id,
            repo_id,
            scored,
            now_iso,
            score_version="v1",
            pool_rank=v1_ranks.get(key),
        )
    for repo_id, scored, data in scored_v2_rows:
        key = identity_key(scored, data)
        _insert_score(
            conn,
            run_id,
            repo_id,
            scored,
            now_iso,
            score_version="v2",
            pool_rank=v2_ranks.get(key),
        )
    _upsert_score_compare(conn, run_id, scored_rows, scored_v2_rows, v1_ranks, v2_ranks)

    selected = select_top(
        pool,
        min_opportunity=settings.scoring.min_opportunity,
        min_explosion=settings.scoring.min_explosion,
        max_per_owner=settings.scoring.max_per_owner,
    )
    from foreshadow.llm import fill_why_now

    fill_why_now(
        selected,
        settings,
        repos={scored.full_name: data for _, scored, data in scored_rows},
    )
    id_by_name = {scored.full_name: repo_id for repo_id, scored, _ in scored_rows}
    for row in selected:
        repo_id = id_by_name.get(row.full_name)
        if repo_id is None:
            continue
        conn.execute(
            """
            UPDATE scores SET selected_rank=?
            WHERE run_id=? AND repo_id=? AND score_version='v1'
            """,
            (row.breakdown.selected_rank, run_id, repo_id),
        )

    _record_project_intelligence(
        conn,
        scored_rows=scored_rows,
        selected=selected,
        today=today,
        clock=clock,
        slack_days=settings.scoring.window_slack_days,
        scored_at=now_iso,
    )

    watch_now = load_watchlist(conn, today, settings.scoring)
    watch_repo_ids = {int(w.repo_id) for w in watch_now}
    selected_ids = {
        id_by_name[row.full_name] for row in selected if row.full_name in id_by_name
    }
    print("Updating observations…", flush=True)
    admit_from_scores(
        conn,
        today=today,
        scored_rows=scored_rows,
        selected_ids=selected_ids,
        watchlist_ids=watch_repo_ids,
        disc=settings.discovery,
    )
    scored_ids = [repo_id for repo_id, _, _ in scored_rows]
    v7_ok = sum(
        1
        for _, scored, _ in scored_rows
        if ((scored.evidence or {}).get("windows") or {}).get("v7") is not None
    )
    v7_base = v7_eligible_count(
        conn, scored_ids, today, settings.scoring.window_slack_days
    )
    retained, _prev_n, overlap = yesterday_overlap(conn, run_id, today)
    system_n, _expired_total = count_states(conn)
    system_ids = {e.repo_id for e in load_active(conn, today)}
    origins = [c.origin for c in disc.capped.candidates]
    health["user_watchlist_count"] = len(watch_now)
    health["system_observed_count"] = system_n
    health["observation_panel_size"] = len(watch_repo_ids | system_ids)
    health["fresh_discovery_count"] = sum(1 for origin in origins if origin == "search")
    health["retained_from_previous_day"] = retained
    health["daily_overlap_rate"] = None if overlap is None else round(overlap, 4)
    health["v7_baseline_eligible_count"] = v7_base
    health["v7_available"] = v7_ok
    health["v7_coverage_rate"] = (
        round(v7_ok / len(scored_rows), 4) if scored_rows else 0.0
    )
    health["observation_expired_count"] = int(
        health.get("observation_expired_count") or 0
    )
    health["explosion_available"] = sum(
        1
        for _, scored, _ in scored_rows
        if scored.breakdown.explosion.value is not None
    )

    snap_days = _snapshot_days(conn)
    status = "degraded" if is_degraded(health) else "complete"
    selected_names = {row.full_name for row in selected}
    watch_items = _watchlist_appendix(
        conn, today, selected_names, settings.scoring, scored_rows
    )
    active_items = _active_items(conn)
    print("Building report…", flush=True)
    report = build_report(
        date=today_s,
        status=status,
        scored_rows=[(s, d) for _, s, d in scored_rows],
        selected=selected,
        candidate_count=disc.candidate_count,
        scored_count=len(scored_rows),
        budget_used=int(
            health.get("budget_used") or getattr(client, "graphql_used", 0) or 0
        ),
        budget_cap=settings.github.budget_graphql_points,
        budget_rest_used=int(
            health.get("rest_used") or getattr(client, "rest_used", 0) or 0
        ),
        snapshot_days=snap_days,
        source_health=health,
        active=active_items,
        watchlist_appendix=watch_items,
        captured_at=now_iso,
        min_opportunity=settings.scoring.min_opportunity,
        min_explosion=settings.scoring.min_explosion,
        review_filter=blocked,
    )
    path = write_reports(data_dir, report)
    conn.execute(
        """
        UPDATE daily_runs SET
          finished_at=?, status=?, source_health_json=?,
          budget_used=?, budget_rest_used=?, candidate_count=?,
          scored_count=?, top5_count=?, report_path=?, error=NULL
        WHERE id=?
        """,
        (
            now_iso,
            status,
            json.dumps(report.source_health, ensure_ascii=False),
            report.budget_used,
            report.budget_rest_used,
            report.candidate_count,
            report.scored_count,
            report.top5_count,
            str(path),
            run_id,
        ),
    )
    conn.commit()
    review_repo = selected[0].full_name if selected else "owner/repo"
    result = RunResult(
        status=status,
        report_path=path,
        top5_count=report.top5_count,
        skipped=False,
        discovered=disc.candidate_count,
        hydrated=hydrated_n,
        scored=len(scored_rows),
        snapshot_days=snap_days,
        source_health=dict(report.source_health),
        review_repo=review_repo,
        report=report,
    )
    result.summary = format_run_summary(
        date=today_s,
        discovered=result.discovered,
        hydrated=result.hydrated,
        scored=result.scored,
        selected=result.top5_count,
        status=status,
        health=health,
        snapshot_days=snap_days,
        report_path=path,
        review_repo=review_repo,
        wrote_config=wrote_config,
    )
    return result


def _has_today_snapshot(data: dict[str, Any], today_s: str) -> bool:
    return any(
        str(snap.get("date") or "")[:10] == today_s
        for snap in data.get("snapshots") or []
    )


def load_score_input(conn: sqlite3.Connection, repo_id: int) -> dict[str, Any] | None:
    repo = conn.execute(
        """
        SELECT node_id, full_name, owner, name, html_url, description,
               language, license_spdx, created_at, has_issues, is_fork,
               is_archived, is_disabled, is_empty
        FROM repos WHERE id=?
        """,
        (repo_id,),
    ).fetchone()
    if repo is None:
        return None
    snaps = conn.execute(
        """
        SELECT snapshot_date, stars, forks, last_pushed_at, open_issues,
               closed_issues, open_prs, contributor_count, contributor_censored,
               unique_committers_30d, topics_json, features_json, captured_at
        FROM snapshots WHERE repo_id=? ORDER BY snapshot_date
        """,
        (repo_id,),
    ).fetchall()
    if not snaps:
        return None
    latest = snaps[-1]
    try:
        features = json.loads(latest[11] or "{}")
    except json.JSONDecodeError:
        features = {}
    try:
        topics = json.loads(latest[10] or "[]")
    except json.JSONDecodeError:
        topics = []
    has_issues = repo[9]
    if has_issues is not None:
        has_issues = bool(has_issues)
    censored = latest[8]
    return {
        "node_id": repo[0],
        "full_name": repo[1],
        "owner": repo[2],
        "name": repo[3],
        "html_url": repo[4],
        "description": repo[5],
        "language": repo[6],
        "license_spdx": repo[7],
        "created_at": repo[8],
        "has_issues": has_issues,
        "is_fork": bool(repo[10]),
        "archived": bool(repo[11]),
        "disabled": bool(repo[12]),
        "is_empty": bool(repo[13]),
        "S": latest[1],
        "F": latest[2],
        "pushed_at": latest[3],
        "I_open": latest[4],
        "I_closed": latest[5],
        "P_open": latest[6],
        "C": latest[7],
        "C_censored": bool(censored) if censored is not None else False,
        "U_commit_30d": latest[9],
        "topics": topics,
        "features": features,
        "captured_at": latest[12],
        "snapshots": [
            {
                "date": row[0],
                "stars": row[1],
                "forks": row[2],
                "pushed_at": row[3],
            }
            for row in snaps
        ],
    }


def _insert_score(
    conn: sqlite3.Connection,
    run_id: int,
    repo_id: int,
    scored: ScoredRepo,
    scored_at: str,
    *,
    score_version: str = "v1",
    pool_rank: int | None = None,
) -> None:
    bd = scored.breakdown
    components = {
        "momentum": bd.momentum.model_dump(),
        "real_user": bd.real_user.model_dump(),
        "gap": bd.gap.model_dump(),
        "contribution_opp": bd.contribution_opp.model_dump(),
        "early_entry": bd.early_entry.model_dump(),
        "direction_fit": bd.direction_fit.model_dump(),
        "maintainer": bd.maintainer.model_dump(),
        "opportunity": bd.opportunity.model_dump(),
        "explosion": bd.explosion.model_dump(),
        "contribution": bd.contribution.model_dump(),
    }
    conn.execute(
        """
        INSERT INTO scores(
          run_id, repo_id, score_version, opportunity, explosion, contribution,
          confidence, components_json, evidence_json, flags_json, vetoed,
          veto_reason, exceptional, selected_rank, pool_rank, scored_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            repo_id,
            score_version,
            bd.opportunity.value,
            bd.explosion.value,
            bd.contribution.value,
            bd.opportunity.confidence,
            json.dumps(components, ensure_ascii=False),
            json.dumps(scored.evidence, ensure_ascii=False),
            json.dumps(list(bd.flags), ensure_ascii=False),
            int(bd.vetoed),
            bd.veto_reason,
            bd.exceptional,
            None if score_version != "v1" else bd.selected_rank,
            pool_rank,
            scored_at,
        ),
    )


def _upsert_score_compare(
    conn: sqlite3.Connection,
    run_id: int,
    v1_rows: Sequence[tuple[int, ScoredRepo, dict[str, Any]]],
    v2_rows: Sequence[tuple[int, ScoredRepo, dict[str, Any]]],
    v1_ranks: dict[str, int],
    v2_ranks: dict[str, int],
) -> None:
    v2_by_id = {repo_id: scored for repo_id, scored, _ in v2_rows}
    v2_data = {repo_id: data for repo_id, _, data in v2_rows}
    for repo_id, scored, data in v1_rows:
        key = identity_key(scored, data)
        other = v2_by_id.get(repo_id)
        other_data = v2_data.get(repo_id, data)
        r1 = v1_ranks.get(key)
        r2 = v2_ranks.get(identity_key(other, other_data) if other else key)
        conn.execute(
            """
            INSERT INTO score_compare(
              run_id, repo_id, v1_rank, v2_rank, rank_delta,
              v1_opportunity, v2_opportunity
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(run_id, repo_id) DO UPDATE SET
              v1_rank=excluded.v1_rank,
              v2_rank=excluded.v2_rank,
              rank_delta=excluded.rank_delta,
              v1_opportunity=excluded.v1_opportunity,
              v2_opportunity=excluded.v2_opportunity
            """,
            (
                run_id,
                repo_id,
                r1,
                r2,
                rank_delta(r1, r2),
                scored.breakdown.opportunity.value,
                other.breakdown.opportunity.value if other else None,
            ),
        )


def _review_blocked(
    conn: sqlite3.Connection, repo_id: int, today: date, scoring: Any
) -> bool:
    from foreshadow.reviews import operator_latest_review, stance_blocks_top5

    row = operator_latest_review(conn, repo_id)
    if row is None:
        return False
    action, created = row
    return stance_blocks_top5(action, created, today, scoring)


def _watchlist_appendix(
    conn: sqlite3.Connection,
    today: date,
    selected_names: set[str],
    scoring: Any,
    scored_rows: list[tuple[int, ScoredRepo, dict[str, Any]]],
) -> list[dict[str, Any]]:
    watch = load_watchlist(conn, today, scoring)
    by_name = {s.full_name: s for _, s, _ in scored_rows}
    snap_days = _snapshot_days(conn)
    out: list[dict[str, Any]] = []
    for entry in watch:
        if entry.full_name in selected_names or entry.action == "enter":
            continue
        scored = by_name.get(entry.full_name)
        if scored is not None and scored.breakdown.vetoed:
            continue
        item: dict[str, Any] = {
            "full_name": entry.full_name,
            "action": entry.action,
            "snapshot_days": snap_days,
        }
        if scored is not None:
            item["opportunity"] = scored.breakdown.opportunity.value
            item["momentum"] = scored.breakdown.momentum.value
        out.append(item)
        if len(out) == 10:
            break
    return out


def _active_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    from foreshadow.reviews import _latest_join

    join_sql, join_params = _latest_join(conn, None)
    rows = conn.execute(
        f"""
        SELECT r.full_name, v.action, v.created_at,
               e.stars_at_entry, e.entered_at
        FROM reviews v
        {join_sql}
        JOIN repos r ON r.id = v.repo_id
        LEFT JOIN entries e ON e.repo_id = r.id
        WHERE v.action IN ('enter', 'investigate')
        ORDER BY v.created_at DESC
        """,
        join_params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for full_name, action, created, stars_e, entered in rows:
        stars_now = conn.execute(
            """
            SELECT s.stars FROM snapshots s
            JOIN repos r ON r.id = s.repo_id
            WHERE r.full_name=?
            ORDER BY s.snapshot_date DESC LIMIT 1
            """,
            (full_name,),
        ).fetchone()
        out.append(
            {
                "full_name": full_name,
                "action": action,
                "created_at": created,
                "entered_at": entered or created,
                "stars_at_entry": stars_e,
                "stars_now": stars_now[0] if stars_now else None,
            }
        )
    return out


def _snapshot_days(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(DISTINCT snapshot_date) FROM snapshots").fetchone()
    return int(row[0] or 0) if row else 0


def _resolve_local(
    conn: sqlite3.Connection, ref: str
) -> tuple[int, str, str, str | None] | None:
    row = conn.execute(
        "SELECT id, node_id, full_name, html_url FROM repos WHERE full_name=?",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2]), row[3]
    row = conn.execute(
        "SELECT id, node_id, full_name, html_url FROM repos WHERE lower(full_name)=lower(?)",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2]), row[3]
    row = conn.execute(
        "SELECT id, node_id, full_name, html_url FROM repos WHERE node_id=?",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2]), row[3]
    row = conn.execute(
        """
        SELECT r.id, r.node_id, r.full_name, r.html_url
        FROM repos r
        JOIN repo_aliases a ON a.repo_id = r.id
        WHERE a.full_name=? OR lower(a.full_name)=lower(?)
        """,
        (ref, ref),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2]), row[3]
    return None


def _as_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _record_project_intelligence(
    conn: sqlite3.Connection,
    *,
    scored_rows: Sequence[tuple[int, ScoredRepo, dict[str, Any]]],
    selected: Sequence[ScoredRepo],
    today: date,
    clock: Clock,
    slack_days: int,
    scored_at: str,
) -> None:
    """Write formula intel_scores and labels. Never touches Official selected_rank."""
    try:
        _write_intel_scores(
            conn,
            scored_rows=scored_rows,
            selected=selected,
            today=today,
            clock=clock,
            slack_days=slack_days,
            scored_at=scored_at,
        )
        _resolve_outcome_labels(conn, today, slack_days=slack_days)
    except sqlite3.OperationalError:
        return


def _write_intel_scores(
    conn: sqlite3.Connection,
    *,
    scored_rows: Sequence[tuple[int, ScoredRepo, dict[str, Any]]],
    selected: Sequence[ScoredRepo],
    today: date,
    clock: Clock,
    slack_days: int,
    scored_at: str,
) -> None:
    score_intel = _load_score_intel()
    if score_intel is None:
        return
    model_run_id = _formula_model_run_id(conn)
    if model_run_id is None:
        return
    policy = _shadow_policy(scored_rows, selected)
    today_s = today.isoformat()
    if scored_rows:
        print("Scoring intelligence…", flush=True)
    for repo_id, scored, data in scored_rows:
        intel = _call_score_intel(
            score_intel,
            scored=scored,
            data=data,
            clock=clock,
            slack_days=slack_days,
        )
        if intel is None:
            continue
        components = _intel_components(intel, data=data, policy=policy)
        eev = components.get("eev")
        try:
            conn.execute(
                """
                INSERT INTO intel_scores(
                  repo_id, as_of_date, model_run_id, score,
                  components_json, scored_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(repo_id, as_of_date, model_run_id) DO UPDATE SET
                  score=excluded.score,
                  components_json=excluded.components_json,
                  scored_at=excluded.scored_at
                """,
                (
                    repo_id,
                    today_s,
                    model_run_id,
                    eev,
                    json.dumps(components, ensure_ascii=False),
                    scored_at,
                ),
            )
        except sqlite3.OperationalError:
            return
        except sqlite3.Error:
            continue
    try:
        record_potential_ups_for_today(conn, today)
    except sqlite3.Error:
        return


def _resolve_outcome_labels(
    conn: sqlite3.Connection, today: date, *, slack_days: int = 1
) -> None:
    try:
        from foreshadow.pipeline.labels import resolve_labels
    except ImportError:
        return
    try:
        resolve_labels(conn, today, slack_days=slack_days)
    except sqlite3.Error:
        return
    except (TypeError, ValueError, AttributeError):
        return


def _load_score_intel() -> Any | None:
    try:
        from foreshadow.pipeline.intel import score_intel
    except ImportError:
        return None
    return score_intel


def _formula_model_run_id(conn: sqlite3.Connection) -> int | None:
    try:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='intel_scores'"
        ).fetchone()
        if present is None:
            return None
        row = conn.execute(
            """
            SELECT id FROM model_runs
            WHERE name='formula-v1'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is not None:
        return int(row[0])
    return 1


def _shadow_policy(
    scored_rows: Sequence[tuple[int, ScoredRepo, dict[str, Any]]],
    selected: Sequence[ScoredRepo],
) -> dict[str, Any] | None:
    try:
        from foreshadow.pipeline.bandit import shadow_explore
    except ImportError:
        return None
    phase_b = [
        scored.full_name
        for _, scored, data in scored_rows
        if _feature_phase(data) == "B"
    ]
    ranked = [row.full_name for row in selected]
    try:
        policy = shadow_explore(phase_b, ranked)
    except (TypeError, ValueError, AttributeError):
        return None
    return policy if isinstance(policy, dict) else None


def _feature_phase(data: dict[str, Any]) -> str | None:
    feat = data.get("features") or {}
    if isinstance(feat, dict):
        phase = feat.get("phase")
    else:
        phase = getattr(feat, "phase", None)
    return str(phase) if phase else None


def _call_score_intel(
    score_intel: Any,
    *,
    scored: ScoredRepo,
    data: dict[str, Any],
    clock: Clock,
    slack_days: int,
) -> Any | None:
    import inspect

    try:
        kwargs = _intel_kwargs(
            scored=scored, data=data, clock=clock, slack_days=slack_days
        )
        params = inspect.signature(score_intel).parameters
        if params and not any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        ):
            kwargs = {key: value for key, value in kwargs.items() if key in params}
        return score_intel(**kwargs)
    except (TypeError, ValueError, AttributeError, KeyError):
        return None


def _intel_kwargs(
    *,
    scored: ScoredRepo,
    data: dict[str, Any],
    clock: Clock,
    slack_days: int,
) -> dict[str, Any]:
    from foreshadow.pipeline.features import compute_windows
    from foreshadow.pipeline.score import _features, _parse_datetime, _snapshots

    feat = _features(data)
    windows = None
    try:
        windows = compute_windows(
            _snapshots(data), clock, data.get("created_at"), slack_days
        )
    except (TypeError, ValueError, AttributeError, KeyError):
        windows = None
    ev_windows = (scored.evidence or {}).get("windows") or {}
    v7 = ev_windows.get("v7")
    if v7 is None and windows is not None:
        v7 = windows.v7
    rel = windows.rel_growth_7d if windows is not None else None
    today = clock.today()
    pushed_age = data.get("pushed_age_days")
    if pushed_age is None:
        pushed_at = _parse_datetime(data.get("pushed_at"))
        if pushed_at is not None:
            pushed_age = max((today - pushed_at.date()).days, 0)
    bd = scored.breakdown
    return {
        "feat": feat,
        "windows_v7": v7,
        "rel_growth_7d": rel,
        "stars": data.get("S"),
        "forks": data.get("F"),
        "open_issues": data.get("I_open"),
        "contributors": data.get("C"),
        "pushed_age_days": pushed_age,
        "direction_fit": bd.direction_fit.value,
        "contribution_opp": bd.contribution_opp.value,
        "strategy_path": _strategy_path(feat),
        "snapshot_count": len(data.get("snapshots") or []),
        "h_flags": list(bd.flags),
        "current_full_name": scored.full_name,
        "now": clock.now(),
    }


def _strategy_path(feat: Any) -> str | None:
    try:
        from foreshadow.pipeline.strategy import recommend_entry
    except ImportError:
        return None
    try:
        rec = recommend_entry(feat)
    except (TypeError, ValueError, AttributeError):
        return None
    path = getattr(rec, "path", None)
    return str(path) if path else None


def _intel_components(
    intel: Any, *, data: dict[str, Any], policy: dict[str, Any] | None
) -> dict[str, Any]:
    if isinstance(intel, dict):
        potential = intel.get("potential")
        creator_prior = intel.get("creator_prior")
        openness = intel.get("openness")
        entry_fit = intel.get("entry_fit")
        eev = intel.get("eev")
        decision = intel.get("decision")
        sample = intel.get("sample", intel.get("sample_n"))
        if sample is None:
            sample = intel.get("openness_sample_n")
        snapshot_count = intel.get("snapshot_count")
        formula_version = intel.get("formula_version") or "intel-v1"
        high_confidence = intel.get("high_confidence")
    else:
        potential = getattr(intel, "potential", None)
        creator_prior = getattr(intel, "creator_prior", None)
        openness = getattr(intel, "openness", None)
        entry_fit = getattr(intel, "entry_fit", None)
        eev = getattr(intel, "eev", None)
        decision = getattr(intel, "decision", None)
        sample = getattr(intel, "openness_sample_n", None)
        if sample is None:
            sample = getattr(intel, "sample_n", None)
        if sample is None:
            sample = getattr(intel, "sample", None)
        snapshot_count = getattr(intel, "snapshot_count", None)
        formula_version = getattr(intel, "formula_version", None) or "intel-v1.1"
        high_confidence = getattr(intel, "high_confidence", None)
    feat = data.get("features") or {}
    if sample is None:
        if isinstance(feat, dict):
            sample = feat.get("pr_external_closed_n")
        else:
            sample = getattr(feat, "pr_external_closed_n", None)
    if snapshot_count is None:
        snapshot_count = len(data.get("snapshots") or [])
    components = {
        "potential": _cs_value(potential),
        "creator_prior": _cs_value(creator_prior),
        "openness": _cs_value(openness),
        "entry_fit": _cs_value(entry_fit),
        "eev": _cs_value(eev),
        "decision": decision,
        "sample": sample,
        "snapshot_count": snapshot_count,
        "formula_version": formula_version,
        "high_confidence": bool(high_confidence),
    }
    if policy is not None:
        components["policy"] = policy
    return components


def _cs_value(part: Any) -> Any:
    if part is None:
        return None
    if isinstance(part, dict):
        return part.get("value")
    return getattr(part, "value", part)
