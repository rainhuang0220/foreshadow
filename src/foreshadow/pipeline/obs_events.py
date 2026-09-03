"""Compare consecutive snapshots and persist observation_events.

NULL is unknown: never treat a missing count as 0. first_seen only on the
first snapshot. Does not write the observations membership table.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import date, datetime
from typing import Any

DELTA_KINDS = (
    ("stars_delta", ("stars",)),
    ("contributors_delta", ("contributor_count", "contributors")),
    ("issues_delta", ("open_issues", "issues")),
    ("prs_delta", ("open_prs", "prs")),
)

_RELEASE_KEYS = ("last_release", "latest_release", "released_at")
_EXT_PR_KEYS = ("pr_external_merged_closed_n", "pr_external_merged_n")


def record_observation_events(
    conn: Any,
    repo_id: int,
    today: date,
    prev_snap: dict[str, Any] | None,
    cur_snap: dict[str, Any],
) -> int:
    """Write kinds for today vs the previous snapshot. Returns events emitted."""
    day = today.isoformat() if isinstance(today, date) else str(today)
    cur = cur_snap or {}
    if prev_snap is None:
        return _upsert(conn, repo_id, day, "first_seen", {})

    n = 0
    for kind, keys in DELTA_KINDS:
        payload = _numeric_delta(prev_snap, cur, keys)
        if payload is not None:
            n += _upsert(conn, repo_id, day, kind, payload)

    prev_c = _int_field(prev_snap, "contributor_count", "contributors")
    cur_c = _int_field(cur, "contributor_count", "contributors")
    if (prev_c == 1 and cur_c is not None and cur_c > 1) or (
        prev_c is None and cur_c is not None and cur_c >= 2
    ):
        n += _upsert(
            conn,
            repo_id,
            day,
            "first_external_contributor",
            {"from": prev_c, "to": cur_c},
        )

    ext = _numeric_delta(prev_snap, cur, _EXT_PR_KEYS)
    if ext is not None and int(ext["delta"]) > 0:
        n += _upsert(conn, repo_id, day, "external_pr_merged", ext)

    if _new_release(prev_snap, cur):
        n += _upsert(
            conn, repo_id, day, "new_release", _release_payload(prev_snap, cur)
        )

    prev_push = _field(prev_snap, "last_pushed_at")
    cur_push = _field(cur, "last_pushed_at")
    if _ts_advanced(prev_push, cur_push):
        n += _upsert(
            conn,
            repo_id,
            day,
            "maintainer_active",
            {"from": prev_push, "to": cur_push},
        )

    pot = _potential_delta(prev_snap, cur)
    if pot is not None:
        n += _upsert(conn, repo_id, day, "potential_up", pot)
    return n


def record_today_observation_events(conn: Any, today: date) -> int:
    """Compare each of today's snapshots to the previous snapshot for that repo."""
    today_s = today.isoformat() if isinstance(today, date) else str(today)
    cur_rows = conn.execute(
        """
        SELECT repo_id, stars, open_issues, open_prs, contributor_count,
               last_pushed_at, features_json
        FROM snapshots
        WHERE snapshot_date=?
        """,
        (today_s,),
    ).fetchall()
    if not cur_rows:
        return 0
    ids = [int(row[0]) for row in cur_rows]
    placeholders = ",".join("?" * len(ids))
    prev_rows = conn.execute(
        f"""
        SELECT s.repo_id, s.stars, s.open_issues, s.open_prs, s.contributor_count,
               s.last_pushed_at, s.features_json
        FROM snapshots s
        JOIN (
          SELECT repo_id, MAX(snapshot_date) AS d
          FROM snapshots
          WHERE snapshot_date < ? AND repo_id IN ({placeholders})
          GROUP BY repo_id
        ) p ON p.repo_id = s.repo_id AND p.d = s.snapshot_date
        """,
        [today_s, *ids],
    ).fetchall()
    prev_map = {int(row[0]): _row_to_snap(row) for row in prev_rows}
    n = 0
    for row in cur_rows:
        rid = int(row[0])
        n += record_observation_events(
            conn, rid, today, prev_map.get(rid), _row_to_snap(row)
        )
    n += record_potential_ups_for_today(conn, today)
    return n


def record_potential_ups_for_today(conn: Any, today: date) -> int:
    """Emit potential_up from intel_scores when the intel module is present."""
    if not _intel_present():
        return 0
    today_s = today.isoformat() if isinstance(today, date) else str(today)
    try:
        rows = conn.execute(
            """
            SELECT repo_id, components_json FROM intel_scores
            WHERE as_of_date=?
            """,
            (today_s,),
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    n = 0
    for repo_id, components_json in rows:
        cur = _potential_from_components(components_json)
        try:
            prev_row = conn.execute(
                """
                SELECT components_json FROM intel_scores
                WHERE repo_id=? AND as_of_date < ?
                ORDER BY as_of_date DESC LIMIT 1
                """,
                (int(repo_id), today_s),
            ).fetchone()
        except sqlite3.OperationalError:
            return n
        prev = _potential_from_components(prev_row[0]) if prev_row else None
        payload = _potential_payload(prev, cur)
        if payload is None:
            continue
        n += _upsert(conn, int(repo_id), today_s, "potential_up", payload)
    return n


def _row_to_snap(row: tuple[Any, ...]) -> dict[str, Any]:
    try:
        feat = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        feat = {}
    if not isinstance(feat, dict):
        feat = {}
    last_rel = (
        feat.get("last_release")
        or feat.get("latest_release")
        or feat.get("released_at")
    )
    return {
        "stars": row[1],
        "open_issues": row[2],
        "issues": row[2],
        "open_prs": row[3],
        "prs": row[3],
        "contributor_count": row[4],
        "contributors": row[4],
        "last_pushed_at": row[5],
        "releases_30d": feat.get("releases_30d"),
        "last_release": last_rel,
        "pr_external_merged_closed_n": feat.get("pr_external_merged_closed_n"),
        "pr_external_merged_n": feat.get("pr_external_merged_n"),
        "potential": feat.get("potential"),
        "features": feat,
    }


def _upsert(
    conn: Any, repo_id: int, day: str, kind: str, payload: dict[str, Any]
) -> int:
    conn.execute(
        """
        INSERT INTO observation_events(repo_id, occurred_on, kind, payload_json)
        VALUES (?,?,?,?)
        ON CONFLICT(repo_id, occurred_on, kind) DO UPDATE SET
          payload_json=excluded.payload_json
        """,
        (int(repo_id), day, kind, json.dumps(payload, ensure_ascii=False)),
    )
    return 1


def _features(snap: dict[str, Any]) -> dict[str, Any]:
    raw = snap.get("features")
    if raw is None:
        raw = snap.get("features_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _field(snap: dict[str, Any] | None, *keys: str) -> Any:
    if not snap:
        return None
    for key in keys:
        if key in snap and snap[key] is not None:
            return snap[key]
    feat = _features(snap)
    for key in keys:
        if key in feat and feat[key] is not None:
            return feat[key]
    return None


def _to_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_field(snap: dict[str, Any] | None, *keys: str) -> int | None:
    return _to_int(_field(snap, *keys))


def _numeric_delta(
    prev_snap: dict[str, Any], cur_snap: dict[str, Any], keys: tuple[str, ...]
) -> dict[str, int] | None:
    a = _int_field(prev_snap, *keys)
    b = _int_field(cur_snap, *keys)
    if a is None or b is None:
        return None
    delta = b - a
    if delta == 0:
        return None
    return {"from": a, "to": b, "delta": delta}


def _new_release(prev_snap: dict[str, Any], cur_snap: dict[str, Any]) -> bool:
    prev_last = _field(prev_snap, *_RELEASE_KEYS)
    cur_last = _field(cur_snap, *_RELEASE_KEYS)
    if cur_last is not None and str(cur_last) != str(prev_last or ""):
        return True
    prev_n = _int_field(prev_snap, "releases_30d")
    cur_n = _int_field(cur_snap, "releases_30d")
    return prev_n is not None and cur_n is not None and cur_n > prev_n


def _release_payload(
    prev_snap: dict[str, Any], cur_snap: dict[str, Any]
) -> dict[str, Any]:
    return {
        "from": _field(prev_snap, *_RELEASE_KEYS),
        "to": _field(cur_snap, *_RELEASE_KEYS),
        "releases_30d_from": _int_field(prev_snap, "releases_30d"),
        "releases_30d_to": _int_field(cur_snap, "releases_30d"),
    }


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _ts_advanced(prev: Any, cur: Any) -> bool:
    if prev is None or cur is None or prev == cur:
        return False
    prev_dt = _parse_iso(prev)
    cur_dt = _parse_iso(cur)
    if prev_dt is not None and cur_dt is not None:
        return cur_dt > prev_dt
    return str(cur) > str(prev)


def _intel_present() -> bool:
    try:
        return importlib.util.find_spec("foreshadow.pipeline.intel") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _potential_from_components(raw: Any) -> float | None:
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    value = data.get("potential")
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _potential_payload(prev: Any, cur: Any) -> dict[str, Any] | None:
    if prev is None or cur is None:
        return None
    try:
        a = float(prev)
        b = float(cur)
    except (TypeError, ValueError):
        return None
    if b <= a:
        return None
    delta: int | float = b - a
    if delta == int(delta):
        delta = int(delta)
    return {"from": a, "to": b, "delta": delta}


def _potential_delta(
    prev_snap: dict[str, Any], cur_snap: dict[str, Any]
) -> dict[str, Any] | None:
    if not _intel_present():
        return None
    return _potential_payload(
        _field(prev_snap, "potential"), _field(cur_snap, "potential")
    )
