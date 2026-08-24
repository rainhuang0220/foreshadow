"""Pipeline stages and daily orchestration."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
from foreshadow.models import ReportJSON
from foreshadow.paths import resolve_data_dir
from foreshadow.pipeline.discover import (
    discover_hydrate_snapshot,
    is_degraded,
    load_watchlist,
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
from foreshadow.pipeline.select import select_top

__all__ = [
    "RunResult",
    "discover_hydrate_snapshot",
    "is_degraded",
    "render_json",
    "render_markdown",
    "run_pipeline",
    "show_repo",
]


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
    db_path = data_dir / "foreshadow.sqlite3"
    conn = connect(db_path)
    migrate(conn)
    today = clock.today()
    today_s = today.isoformat()

    existing = conn.execute(
        """
        SELECT status, report_path, top5_count, candidate_count, scored_count,
               source_health_json
        FROM daily_runs WHERE run_date=?
        """,
        (today_s,),
    ).fetchone()
    report_file = (
        Path(existing[1])
        if existing and existing[1]
        else data_dir / "reports" / f"{today_s}.md"
    )
    if existing and existing[0] == "complete" and not force and report_file.is_file():
        path = report_file
        health = _as_dict(existing[5])
        snap_days = _snapshot_days(conn)
        result = RunResult(
            status="complete",
            report_path=path,
            top5_count=int(existing[2] or 0),
            skipped=True,
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
            status="complete",
            health=health,
            snapshot_days=snap_days,
            report_path=result.report_path,
            skipped=True,
        )
        return result

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
        FROM scores WHERE repo_id=? ORDER BY scored_at DESC, id DESC LIMIT 1
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
    reviews = conn.execute(
        """
        SELECT created_at, action, note FROM reviews
        WHERE repo_id=? ORDER BY id DESC
        """,
        (repo_id,),
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
    disc = discover_hydrate_snapshot(conn, client, settings, clock=clock, force=force)
    today = clock.today()
    today_s = today.isoformat()
    health = dict(disc.source_health)
    run_id = disc.run_id
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

    bags = None
    scored_rows: list[tuple[int, ScoredRepo, dict[str, Any]]] = []
    blocked = 0
    pool: list[ScoredRepo] = []
    for repo_id, _status, _name in cand_rows:
        data = load_score_input(conn, repo_id)
        if data is None:
            continue
        scored = score_repo(data, clock=clock, scoring=settings.scoring, bags=bags)
        scored_rows.append((repo_id, scored, data))
        if _review_blocked(conn, repo_id, today, settings.scoring):
            blocked += 1
            continue
        pool.append(scored)

    now_iso = clock.now().isoformat()
    for repo_id, scored, _data in scored_rows:
        _insert_score(conn, run_id, repo_id, scored, now_iso)

    selected = select_top(
        pool,
        min_opportunity=settings.scoring.min_opportunity,
        min_explosion=settings.scoring.min_explosion,
        max_per_owner=settings.scoring.max_per_owner,
    )
    id_by_name = {scored.full_name: repo_id for repo_id, scored, _ in scored_rows}
    for row in selected:
        repo_id = id_by_name.get(row.full_name)
        if repo_id is None:
            continue
        conn.execute(
            "UPDATE scores SET selected_rank=? WHERE run_id=? AND repo_id=?",
            (row.breakdown.selected_rank, run_id, repo_id),
        )

    snap_days = _snapshot_days(conn)
    status = "degraded" if is_degraded(health) else "complete"
    selected_names = {row.full_name for row in selected}
    watch_items = _watchlist_appendix(
        conn, today, selected_names, settings.scoring, scored_rows
    )
    active_items = _active_items(conn)
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
          run_id, repo_id, opportunity, explosion, contribution, confidence,
          components_json, evidence_json, flags_json, vetoed, veto_reason,
          exceptional, selected_rank, scored_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            repo_id,
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
            bd.selected_rank,
            scored_at,
        ),
    )


def _review_blocked(
    conn: sqlite3.Connection, repo_id: int, today: date, scoring: Any
) -> bool:
    row = conn.execute(
        """
        SELECT action, created_at FROM reviews
        WHERE repo_id=? ORDER BY id DESC LIMIT 1
        """,
        (repo_id,),
    ).fetchone()
    if row is None:
        return False
    action, created = row
    day = _parse_day(created)
    cooldown = int(getattr(scoring, "reject_cooldown_days", 90))
    later = int(getattr(scoring, "later_skip_days", 14))
    if action == "enter":
        return True
    if (
        action == "reject"
        and day is not None
        and today < day + timedelta(days=cooldown)
    ):
        return True
    return action == "later" and day is not None and today < day + timedelta(days=later)


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
    rows = conn.execute(
        """
        SELECT r.full_name, v.action, v.created_at,
               e.stars_at_entry, e.entered_at
        FROM reviews v
        JOIN (
            SELECT repo_id, MAX(id) AS id FROM reviews GROUP BY repo_id
        ) last ON last.id = v.id
        JOIN repos r ON r.id = v.repo_id
        LEFT JOIN entries e ON e.repo_id = r.id
        WHERE v.action IN ('enter', 'investigate')
        ORDER BY v.created_at DESC
        """
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


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
