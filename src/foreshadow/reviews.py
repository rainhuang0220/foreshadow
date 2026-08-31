"""Append-only human reviews and Enter snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, NoReturn

from foreshadow.clock import Clock
from foreshadow.config import Settings, load_config
from foreshadow.github.client import GitHubError
from foreshadow.github.queries import HYDRATE_B
from foreshadow.pipeline.hydrate import (
    build_features_blob,
    census_contributors,
    extract_repo,
    features_json,
    hydrate_b_node,
    hydrate_phase_b_rest,
    unique_committers_30d,
    upsert_repo_from_graphql,
)
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.snapshot import payload_from_graphql, upsert_snapshot

ACTIONS = ("watch", "interested", "reject", "investigate", "enter", "later")


class ReviewError(Exception):
    """Unknown action or unresolvable repo ref. CLI → exit 2."""


class ReviewFetchError(Exception):
    """Hydrate 429 / 5xx / budget (not a missing name). CLI → exit 1."""

    def __init__(self, message: str, *, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason


def apply_review(
    conn: sqlite3.Connection,
    client: Any,
    repo_ref: str,
    action: str,
    note: str | None,
    clock: Clock,
    settings: Settings | None = None,
    user_id: int | None = None,
) -> None:
    action_n = (action or "").strip().lower()
    if action_n not in ACTIONS:
        raise ReviewError(f"unknown action: {action} ({', '.join(ACTIONS)})")
    clock = clock or Clock()
    settings = settings or load_config()
    from foreshadow.auth import ensure_local_user, is_operator_user

    uid = user_id if user_id is not None else ensure_local_user(conn)
    today = clock.today()
    local = _resolve_local(conn, repo_ref)
    unseen = local is None
    if _needs_hydrate(conn, local, action_n, today):
        if client is None:
            raise ReviewFetchError(
                f"GitHub client required to hydrate {repo_ref}",
                reason="client",
            )
        repo_id = _hydrate_one(conn, client, repo_ref, local, clock)
    else:
        assert local is not None
        repo_id = local[0]

    run_id = _today_run_id(conn, today.isoformat())
    scored: ScoredRepo | None = None
    operator = is_operator_user(conn, uid)
    if action_n == "enter" or unseen:
        scored = _score_snapshot(conn, repo_id, clock, settings.scoring)
        if (
            action_n == "enter"
            and operator
            and run_id is not None
            and scored is not None
        ):
            _upsert_score(conn, run_id, repo_id, scored, clock.now().isoformat())
    if action_n == "enter" and operator:
        _upsert_entry(conn, repo_id, scored, note, clock, run_id)
    conn.execute(
        """
        INSERT INTO reviews(repo_id, action, note, run_id, created_at, user_id)
        VALUES (?,?,?,?,?,?)
        """,
        (repo_id, action_n, note, run_id, clock.now().isoformat(), uid),
    )
    conn.commit()


def current_stances(
    conn: sqlite3.Connection, action: str | None, user_id: int | None = None
) -> list[dict[str, Any]]:
    action_n = (action or "").strip().lower() or None
    if action_n is not None and action_n not in ACTIONS:
        raise ReviewError(f"unknown action: {action} ({', '.join(ACTIONS)})")
    join_sql, params = _latest_join(conn, user_id)
    sql = f"""
        SELECT r.full_name, v.action, v.note, v.created_at, r.id,
               e.stars_at_entry, e.contributors_at_entry, e.entered_at
        FROM reviews v
        {join_sql}
        JOIN repos r ON r.id = v.repo_id
        LEFT JOIN entries e ON e.repo_id = r.id
    """
    if action_n:
        sql += " WHERE v.action=?"
        params.append(action_n)
    sql += " ORDER BY v.created_at DESC, v.id DESC"
    out: list[dict[str, Any]] = []
    for (
        full_name,
        act,
        note,
        created,
        repo_id,
        stars_e,
        contrib_e,
        entered,
    ) in conn.execute(sql, params):
        stars_now = conn.execute(
            """
            SELECT stars FROM snapshots
            WHERE repo_id=? ORDER BY snapshot_date DESC LIMIT 1
            """,
            (repo_id,),
        ).fetchone()
        out.append(
            {
                "full_name": full_name,
                "action": act,
                "note": note,
                "created_at": created,
                "repo_id": int(repo_id),
                "stars_at_entry": stars_e,
                "contributors_at_entry": contrib_e,
                "entered_at": entered,
                "stars_now": stars_now[0] if stars_now else None,
            }
        )
    return out


def format_stances(rows: list[dict[str, Any]], action: str | None = None) -> str:
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in ACTIONS}
    for row in rows:
        act = str(row.get("action") or "")
        groups.setdefault(act, []).append(row)
    order = [action] if action else list(ACTIONS)
    lines: list[str] = []
    for act in order:
        if act is None:
            continue
        items = groups.get(act) or []
        if not action and not items:
            continue
        lines.append(act)
        if not items:
            lines.append("  (none)")
        else:
            for item in items:
                lines.append(_stance_line(item))
        lines.append("")
    if not lines:
        return "no reviews\n"
    return "\n".join(lines).rstrip() + "\n"


def needs_hydrate(
    conn: sqlite3.Connection,
    repo_ref: str,
    action: str,
    clock: Clock,
) -> bool:
    """True when review must call GitHub (unseen, no snapshot, or enter without today's Phase B)."""
    action_n = (action or "").strip().lower()
    local = _resolve_local(conn, repo_ref)
    return _needs_hydrate(conn, local, action_n, clock.today())


def latest_action_map(
    conn: sqlite3.Connection, user_id: int | None = None
) -> dict[str, str]:
    """full_name -> current action for one user (CLI operator if user_id is None)."""
    rows = current_stances(conn, action=None, user_id=user_id)
    return {str(row["full_name"]): str(row["action"]) for row in rows}


def _latest_join(
    conn: sqlite3.Connection, user_id: int | None
) -> tuple[str, list[Any]]:
    from foreshadow.auth import ensure_local_user, is_operator_user

    uid = user_id if user_id is not None else ensure_local_user(conn)
    if user_id is None or is_operator_user(conn, uid):
        sql = """
        JOIN (
            SELECT repo_id, MAX(id) AS id FROM reviews
            WHERE user_id = ? OR user_id IS NULL
            GROUP BY repo_id
        ) last ON last.id = v.id
        """
        return sql, [uid]
    sql = """
        JOIN (
            SELECT repo_id, MAX(id) AS id FROM reviews
            WHERE user_id = ?
            GROUP BY repo_id
        ) last ON last.id = v.id
        """
    return sql, [uid]


def operator_latest_review(
    conn: sqlite3.Connection, repo_id: int
) -> tuple[str, str] | None:
    from foreshadow.auth import ensure_local_user

    uid = ensure_local_user(conn)
    row = conn.execute(
        """
        SELECT action, created_at FROM reviews
        WHERE repo_id=? AND (user_id=? OR user_id IS NULL)
        ORDER BY id DESC LIMIT 1
        """,
        (repo_id, uid),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def stance_blocks_top5(
    action: str,
    created_at: str | None,
    today: date,
    scoring: Any | None = None,
) -> bool:
    """Eligibility filter only — never a ranking nudge."""
    cooldown = int(getattr(scoring, "reject_cooldown_days", 90) if scoring else 90)
    later = int(getattr(scoring, "later_skip_days", 14) if scoring else 14)
    day = _parse_day(created_at)
    if action == "enter":
        return True
    if action == "reject":
        return day is not None and today < day + timedelta(days=cooldown)
    if action == "later":
        return day is not None and today < day + timedelta(days=later)
    return False


def _stance_line(item: dict[str, Any]) -> str:
    name = item.get("full_name") or ""
    extra = ""
    if item.get("action") == "enter":
        stars_e = item.get("stars_at_entry")
        stars_n = item.get("stars_now")
        if stars_e is not None:
            extra = f"  stars_at_entry={stars_e}"
            if stars_n is not None:
                try:
                    extra += f" now={stars_n} ({int(stars_n) - int(stars_e):+d})"
                except (TypeError, ValueError):
                    extra += f" now={stars_n}"
    note = f"  {item['note']}" if item.get("note") else ""
    return f"  {name}{extra}{note}"


def _resolve_local(conn: sqlite3.Connection, ref: str) -> tuple[int, str, str] | None:
    row = conn.execute(
        "SELECT id, node_id, full_name FROM repos WHERE full_name=?",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2])
    row = conn.execute(
        "SELECT id, node_id, full_name FROM repos WHERE lower(full_name)=lower(?)",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2])
    row = conn.execute(
        """
        SELECT r.id, r.node_id, r.full_name
        FROM repos r
        JOIN repo_aliases a ON a.repo_id = r.id
        WHERE a.full_name=? OR lower(a.full_name)=lower(?)
        """,
        (ref, ref),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2])
    row = conn.execute(
        "SELECT id, node_id, full_name FROM repos WHERE node_id=?",
        (ref,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1]), str(row[2])
    return None


def _needs_hydrate(
    conn: sqlite3.Connection,
    local: tuple[int, str, str] | None,
    action: str,
    today: date,
) -> bool:
    if local is None:
        return True
    if not _has_snapshot(conn, local[0]):
        return True
    return action == "enter" and not _phase_b_today(conn, local[0], today)


def _has_snapshot(conn: sqlite3.Connection, repo_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM snapshots WHERE repo_id=? LIMIT 1", (repo_id,)
    ).fetchone()
    return row is not None


def _phase_b_today(conn: sqlite3.Connection, repo_id: int, today: date) -> bool:
    row = conn.execute(
        """
        SELECT features_json, contributor_count
        FROM snapshots WHERE repo_id=? AND snapshot_date=?
        """,
        (repo_id, today.isoformat()),
    ).fetchone()
    if row is None:
        return False
    return _phase_b_payload(row[0], row[1])


def _phase_b_payload(features_json_s: str | None, contributor_count: Any) -> bool:
    if contributor_count is not None:
        return True
    raw = features_json_s or ""
    if raw in ("", "{}", "null"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict) or not data:
        return False
    return data.get("phase") == "B" or "tree_names" in data or "u_issue" in data


def _hydrate_one(
    conn: sqlite3.Connection,
    client: Any,
    repo_ref: str,
    local: tuple[int, str, str] | None,
    clock: Clock,
) -> int:
    now = clock.now().isoformat()
    body, err = _fetch_phase_b(client, repo_ref, local)
    repo = extract_repo(body) if body is not None else None
    if err is not None or repo is None:
        _raise_hydrate_failure(repo_ref, err)
    repo_id = upsert_repo_from_graphql(conn, repo, now)
    owner, name = _split_name(str(repo.get("nameWithOwner") or repo_ref))
    rest = hydrate_phase_b_rest(
        client, owner, name, clock, is_fork=bool(repo.get("isFork"))
    )
    blob = build_features_blob(repo, rest)
    c_rows = rest.get("contributors")
    if c_rows is None:
        total = ident = anon = censored = None
    else:
        total, ident, anon, censored = census_contributors(c_rows)
    commits = rest.get("commits")
    unique = None if commits is None else unique_committers_30d(commits)
    payload = payload_from_graphql(
        repo,
        captured_at=now,
        created_at=repo.get("createdAt"),
        features_json=features_json(blob),
        contributor_count=total,
        contributor_identified=ident,
        contributor_anon=anon,
        contributor_censored=censored,
        unique_committers_30d=unique,
    )
    upsert_snapshot(conn, repo_id, clock.today(), payload)
    return repo_id


def _fetch_phase_b(
    client: Any,
    repo_ref: str,
    local: tuple[int, str, str] | None,
) -> tuple[dict[str, Any] | None, GitHubError | None]:
    node_id = local[1] if local else (None if "/" in repo_ref else repo_ref)
    owner, name = _split_name(local[2] if local else repo_ref)
    body: dict[str, Any] | None = None
    err: GitHubError | None = None
    if node_id:
        body, err = hydrate_b_node(client, node_id)
        if err is None and extract_repo(body) is not None:
            return body, None
        if err is not None and not _is_not_found(err):
            return None, err
    if owner and name:
        named, named_err = _hydrate_b_name(client, owner, name)
        if named_err is None and extract_repo(named) is not None:
            return named, None
        if named_err is not None and not _is_not_found(named_err):
            return None, named_err
        if body is None:
            body, err = named, named_err
    if body is not None and extract_repo(body) is not None:
        return body, None
    return None, err or GitHubError(
        "http_404",
        f"unknown repo: {repo_ref}",
        retryable=False,
        status=404,
        source="HydrateB",
    )


def _is_not_found(exc: GitHubError) -> bool:
    if exc.status in {404, 410, 451}:
        return True
    return exc.reason == "http_404"


def _raise_hydrate_failure(repo_ref: str, err: GitHubError | None) -> NoReturn:
    if err is not None and not _is_not_found(err):
        raise ReviewFetchError(
            err.detail or err.reason or f"hydrate failed for {repo_ref}",
            reason=err.reason,
        ) from err
    raise ReviewError(f"unknown repo: {repo_ref}")


def _hydrate_b_name(
    client: Any, owner: str, name: str, *, force: bool = False
) -> tuple[dict[str, Any] | None, GitHubError | None]:
    try:
        body = client.graphql(HYDRATE_B, {"owner": owner, "name": name}, force=force)
    except GitHubError as exc:
        return None, exc
    return body, None


def _split_name(full: str) -> tuple[str, str]:
    base = full.split("#", 1)[0]
    if "/" in base:
        owner, name = base.split("/", 1)
        return owner, name
    return "", base


def _today_run_id(conn: sqlite3.Connection, today: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM daily_runs WHERE run_date=?", (today,)
    ).fetchone()
    return int(row[0]) if row else None


def _score_snapshot(
    conn: sqlite3.Connection,
    repo_id: int,
    clock: Clock,
    scoring: Any,
) -> ScoredRepo | None:
    from foreshadow.pipeline import load_score_input

    data = load_score_input(conn, repo_id)
    if data is None:
        return None
    return score_repo(data, clock=clock, scoring=scoring)


def _scores_json(scored: ScoredRepo | None) -> str:
    if scored is None:
        return json.dumps(
            {
                "opportunity": None,
                "explosion": None,
                "contribution": None,
                "components": {
                    "momentum": None,
                    "real_user": None,
                    "gap": None,
                    "contribution_opp": None,
                    "early_entry": None,
                    "direction_fit": None,
                    "maintainer": None,
                },
                "flags": [],
                "missing": ["snapshot"],
            },
            ensure_ascii=False,
        )
    bd = scored.breakdown
    payload = {
        "opportunity": bd.opportunity.model_dump(mode="json"),
        "explosion": bd.explosion.model_dump(mode="json"),
        "contribution": bd.contribution.model_dump(mode="json"),
        "components": {
            "momentum": bd.momentum.model_dump(mode="json"),
            "real_user": bd.real_user.model_dump(mode="json"),
            "gap": bd.gap.model_dump(mode="json"),
            "contribution_opp": bd.contribution_opp.model_dump(mode="json"),
            "early_entry": bd.early_entry.model_dump(mode="json"),
            "direction_fit": bd.direction_fit.model_dump(mode="json"),
            "maintainer": bd.maintainer.model_dump(mode="json"),
        },
        "flags": list(bd.flags),
        "vetoed": bd.vetoed,
        "veto_reason": bd.veto_reason,
        "exceptional": bd.exceptional,
        "evidence": scored.evidence,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _upsert_entry(
    conn: sqlite3.Connection,
    repo_id: int,
    scored: ScoredRepo | None,
    note: str | None,
    clock: Clock,
    run_id: int | None,
) -> None:
    snap = conn.execute(
        """
        SELECT stars, contributor_count, open_issues
        FROM snapshots WHERE repo_id=?
        ORDER BY snapshot_date DESC LIMIT 1
        """,
        (repo_id,),
    ).fetchone()
    stars = snap[0] if snap else None
    contrib = snap[1] if snap else None
    open_issues = snap[2] if snap else None
    bd = scored.breakdown if scored is not None else None
    conn.execute(
        """
        INSERT INTO entries(
          repo_id, entered_at, run_id, stars_at_entry, contributors_at_entry,
          open_issues_at_entry, opportunity_at_entry, explosion_at_entry,
          contribution_at_entry, scores_at_entry_json, chosen_contribution, note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(repo_id) DO UPDATE SET
          entered_at=excluded.entered_at,
          run_id=excluded.run_id,
          stars_at_entry=excluded.stars_at_entry,
          contributors_at_entry=excluded.contributors_at_entry,
          open_issues_at_entry=excluded.open_issues_at_entry,
          opportunity_at_entry=excluded.opportunity_at_entry,
          explosion_at_entry=excluded.explosion_at_entry,
          contribution_at_entry=excluded.contribution_at_entry,
          scores_at_entry_json=excluded.scores_at_entry_json,
          note=excluded.note
        """,
        (
            repo_id,
            clock.now().isoformat(),
            run_id,
            stars,
            contrib,
            open_issues,
            bd.opportunity.value if bd else None,
            bd.explosion.value if bd else None,
            bd.contribution.value if bd else None,
            _scores_json(scored),
            None,
            note,
        ),
    )


def _upsert_score(
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
          run_id, repo_id, score_version, opportunity, explosion, contribution,
          confidence, components_json, evidence_json, flags_json, vetoed,
          veto_reason, exceptional, selected_rank, pool_rank, scored_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id, repo_id, score_version) DO UPDATE SET
          opportunity=excluded.opportunity,
          explosion=excluded.explosion,
          contribution=excluded.contribution,
          confidence=excluded.confidence,
          components_json=excluded.components_json,
          evidence_json=excluded.evidence_json,
          flags_json=excluded.flags_json,
          vetoed=excluded.vetoed,
          veto_reason=excluded.veto_reason,
          exceptional=excluded.exceptional,
          scored_at=excluded.scored_at
        """,
        (
            run_id,
            repo_id,
            "v1",
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
            None,
            scored_at,
        ),
    )


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
