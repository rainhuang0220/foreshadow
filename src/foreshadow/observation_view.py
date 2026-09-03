"""Observation timeline and honest growth charts. Never interpolate missing days."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

SPARK_CHARS = "▁▂▃▄▅▆▇█"
SPARK_PENDING = ""

EVENT_LABELS_ZH: dict[str, str] = {
    "first_seen": "首次发现",
    "FIRST_SEEN": "首次发现",
    "stars_delta": "Stars",
    "STAR_DELTA": "Stars",
    "contributors_delta": "外部贡献者",
    "issues_delta": "Issues",
    "ISSUE_DELTA": "Issues",
    "prs_delta": "PRs",
    "PR_DELTA": "PRs",
    "new_release": "新 Release",
    "first_external_contributor": "首次外部贡献者",
    "external_pr_merged": "外部 PR 合入",
    "potential_up": "潜力上升",
    "maintainer_active": "维护者活跃",
    "PROMOTED_TO_OBSERVATION": "进入持续观察",
}

_DELTA_LABELS_ZH: dict[str, str] = {
    "stars": "Stars",
    "stars_delta": "Stars",
    "contributors": "外部贡献者",
    "contributor_count": "外部贡献者",
    "contributors_delta": "外部贡献者",
    "open_issues": "Issues",
    "issues": "Issues",
    "issues_delta": "Issues",
    "open_prs": "PRs",
    "prs": "PRs",
    "prs_delta": "PRs",
    "forks": "Forks",
}

_SERIES_KEYS: dict[str, tuple[str, ...]] = {
    "stars": ("stars",),
    "forks": ("forks",),
    "issues": ("issues", "open_issues"),
    "open_issues": ("open_issues", "issues"),
    "prs": ("prs", "open_prs"),
    "open_prs": ("open_prs", "prs"),
    "contributors": ("contributors", "contributor_count"),
    "contributor_count": ("contributor_count", "contributors"),
}


def load_series(conn: sqlite3.Connection, repo_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT snapshot_date, stars, open_issues, open_prs, forks,
               contributor_count, last_pushed_at
        FROM snapshots
        WHERE repo_id=?
        ORDER BY snapshot_date ASC
        """,
        (int(repo_id),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "date": str(row[0]),
                "stars": _int(row[1]),
                "open_issues": _int(row[2]),
                "issues": _int(row[2]),
                "open_prs": _int(row[3]),
                "prs": _int(row[3]),
                "forks": _int(row[4]),
                "contributors": _int(row[5]),
                "last_pushed_at": row[6],
            }
        )
    return out


def sparkline(series: list[dict[str, Any]], *, key: str = "stars") -> str:
    vals = [p.get(key) for p in series if p.get(key) is not None]
    if len(vals) < 2:
        return SPARK_PENDING
    lo = min(vals)
    hi = max(vals)
    span = hi - lo
    chars: list[str] = []
    for v in vals:
        if span <= 0:
            chars.append(SPARK_CHARS[0])
            continue
        idx = round((v - lo) / span * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[max(0, min(len(SPARK_CHARS) - 1, idx))])
    return "".join(chars)


def delta_pair(series: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """First→last observed values for ``key``. NULL is not 0."""
    vals: list[int] = []
    for point in series:
        raw = _point_value(point, key)
        if raw is None:
            continue
        vals.append(int(raw))
    if len(vals) < 2:
        return {"from": None, "to": None, "delta": None, "pending": True}
    first, last = vals[0], vals[-1]
    return {"from": first, "to": last, "delta": last - first, "pending": False}


def format_delta_zh(key: str, pair: dict[str, Any]) -> str:
    label = _DELTA_LABELS_ZH.get(key) or EVENT_LABELS_ZH.get(key, key)
    before, after = pair.get("from"), pair.get("to")
    if pair.get("pending") or before is None or after is None:
        return f"{label}：尚不足"
    return f"{label}：{before} → {after}"


def star_delta(series: list[dict[str, Any]], *, days: int = 7) -> dict[str, Any]:
    stars = [(p["date"], p["stars"]) for p in series if p.get("stars") is not None]
    if len(stars) < 2:
        return {
            "days": days,
            "delta": None,
            "from": None,
            "to": None,
            "pending": True,
            "observed_days": len(stars),
        }
    last_day, last_val = stars[-1]
    first_day, first_val = stars[0]
    return {
        "days": days,
        "delta": int(last_val) - int(first_val),
        "from": first_val,
        "to": last_val,
        "pending": False,
        "observed_days": len(stars),
        "first_date": first_day,
        "last_date": last_day,
        "window_complete": len(stars) >= days,
    }


def interpret_growth(series: list[dict[str, Any]]) -> str:
    delta = star_delta(series, days=7)
    if delta["pending"]:
        n = delta["observed_days"]
        if n <= 0:
            return "还没有本地快照，不能谈增长。"
        return "增长历史还不够，7 日趋势尚未形成。"
    d = int(delta["delta"] or 0)
    n = int(delta["observed_days"])
    if d > 0:
        return f"近 {n} 个观察日 Stars {d:+d}（未补齐缺失日期，不是 7 日插值）。"
    if d < 0:
        return f"近 {n} 个观察日 Stars {d:+d}。"
    return f"近 {n} 个观察日 Stars 没有净增长。"


def decision_for(
    series: list[dict[str, Any]],
    *,
    official: bool,
    observing: bool,
) -> str:
    if official:
        return "正式机会"
    delta = star_delta(series)
    if delta["pending"]:
        return "继续观察" if observing else "候选"
    if observing:
        return "继续观察"
    return "候选"


def timeline_for(
    conn: sqlite3.Connection, repo_id: int, *, today: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    stored = _load_stored_events(conn, repo_id)
    has_first = any(str(e.get("kind", "")).lower() == "first_seen" for e in stored)
    repo = conn.execute(
        "SELECT first_seen_at, full_name FROM repos WHERE id=?",
        (int(repo_id),),
    ).fetchone()
    if repo and repo[0] and not has_first:
        events.append(
            {
                "date": str(repo[0])[:10],
                "kind": "FIRST_SEEN",
                "label_zh": EVENT_LABELS_ZH["FIRST_SEEN"],
                "payload": {"full_name": repo[1]},
            }
        )
    obs = conn.execute(
        """
        SELECT added_on, last_observed_on, expires_on, reason, state
        FROM observations WHERE repo_id=?
        """,
        (int(repo_id),),
    ).fetchone()
    if obs:
        events.append(
            {
                "date": str(obs[0]),
                "kind": "PROMOTED_TO_OBSERVATION",
                "label_zh": EVENT_LABELS_ZH["PROMOTED_TO_OBSERVATION"],
                "payload": {"reason": obs[3], "expires_on": obs[2]},
            }
        )
    if stored:
        events.extend(stored)
    else:
        series = load_series(conn, repo_id)
        prev: dict[str, Any] | None = None
        for point in series:
            if prev is not None:
                _delta_event(
                    events,
                    point["date"],
                    "STAR_DELTA",
                    EVENT_LABELS_ZH["STAR_DELTA"],
                    prev.get("stars"),
                    point.get("stars"),
                )
                _delta_event(
                    events,
                    point["date"],
                    "ISSUE_DELTA",
                    EVENT_LABELS_ZH["ISSUE_DELTA"],
                    prev.get("open_issues"),
                    point.get("open_issues"),
                )
                _delta_event(
                    events,
                    point["date"],
                    "PR_DELTA",
                    EVENT_LABELS_ZH["PR_DELTA"],
                    prev.get("open_prs"),
                    point.get("open_prs"),
                )
            prev = point
    events.sort(key=lambda e: (e["date"], e["kind"]))
    return events


def card_layers(
    conn: sqlite3.Connection,
    repo_id: int,
    *,
    official: bool,
    observing: bool,
) -> dict[str, Any]:
    series = load_series(conn, repo_id)
    delta = star_delta(series)
    last = series[-1] if series else {}
    return {
        "series": series,
        "sparkline": sparkline(series),
        "star_delta": delta,
        "fact": {
            "stars": last.get("stars"),
            "star_delta": delta["delta"],
            "star_delta_pending": delta["pending"],
            "observed_days": delta["observed_days"],
            "open_issues": last.get("open_issues"),
            "open_prs": last.get("open_prs"),
        },
        "interpretation": interpret_growth(series),
        "decision": decision_for(series, official=official, observing=observing),
        "timeline": timeline_for(conn, repo_id, today=last.get("date") or ""),
    }


def _delta_event(
    events: list[dict[str, Any]],
    day: str,
    kind: str,
    label: str,
    before: int | None,
    after: int | None,
) -> None:
    if before is None or after is None:
        return
    d = int(after) - int(before)
    if d == 0:
        return
    events.append(
        {
            "date": day,
            "kind": kind,
            "label_zh": f"{label} {d:+d}",
            "payload": {"delta": d, "from": before, "to": after},
        }
    )


def enrich_board_payload(
    payload: dict[str, Any], conn: sqlite3.Connection
) -> dict[str, Any]:
    """Attach honest observation layers to each candidate. Mutates payload."""
    names = [
        c.get("full_name")
        for c in payload.get("candidates") or []
        if c.get("full_name")
    ]
    id_map: dict[str, int] = {}
    if names:
        q = ",".join("?" * len(names))
        for row in conn.execute(
            f"SELECT full_name, id FROM repos WHERE full_name IN ({q})",
            names,
        ):
            id_map[str(row[0])] = int(row[1])
    observing_ids = {
        int(r[0])
        for r in conn.execute("SELECT repo_id FROM observations WHERE state='active'")
    }
    official_n = 0
    for card in payload.get("candidates") or []:
        rid = id_map.get(str(card.get("full_name") or ""))
        official = card.get("status") == "official"
        if official:
            official_n += 1
        observing = rid in observing_ids if rid else bool(card.get("observation_zh"))
        layers = (
            card_layers(conn, rid, official=official, observing=observing)
            if rid
            else {
                "sparkline": SPARK_PENDING,
                "star_delta": star_delta([]),
                "fact": {},
                "interpretation": "还没有本地快照，不能谈增长。",
                "decision": "继续观察" if observing else "候选",
                "timeline": [],
            }
        )
        card["sparkline"] = layers["sparkline"]
        card["star_delta"] = layers["star_delta"]
        card["fact"] = layers["fact"]
        card["interpretation"] = layers["interpretation"]
        card["decision"] = layers["decision"]
        card["timeline"] = layers["timeline"]
        card["pool"] = _pool_name(card, observing=observing, official=official)
        rec = _recommended_action(card, layers)
        card["recommended_action"] = rec
        if rid:
            from foreshadow.entry import load_entry

            stored = load_entry(conn, rid)
            if stored is not None:
                card["entry"] = stored.as_dict()
    counts = payload.setdefault("counts", {})
    counts["observing"] = sum(
        1 for c in payload.get("candidates") or [] if c.get("pool") == "observing"
    )
    payload["filters"] = [
        {"id": "all", "label": "全部"},
        {"id": "observing", "label": "持续观察"},
        {"id": "candidate", "label": "候选"},
        {"id": "official", "label": "正式机会"},
        {"id": "entered", "label": "已进入"},
        {"id": "expired", "label": "已过期"},
    ]
    return payload


def repo_detail(conn: sqlite3.Connection, full_name: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, full_name, description, first_seen_at, html_url, language
        FROM repos WHERE full_name=?
        """,
        (full_name,),
    ).fetchone()
    if row is None:
        return None
    rid = int(row[0])
    obs = conn.execute(
        """
        SELECT added_on, last_observed_on, expires_on, reason, state
        FROM observations WHERE repo_id=?
        """,
        (rid,),
    ).fetchone()
    observing = bool(obs) and str(obs[4]) == "active"
    layers = card_layers(conn, rid, official=False, observing=observing)
    day = None
    if obs:
        try:
            from datetime import date as date_cls

            added = date_cls.fromisoformat(str(obs[0]))
            last = date_cls.fromisoformat(str(obs[1]))
            day = (last - added).days + 1
        except ValueError:
            day = None
    return {
        "full_name": row[1],
        "description": row[2],
        "first_seen_at": row[3],
        "html_url": row[4],
        "language": row[5],
        "observation": None
        if obs is None
        else {
            "added_on": obs[0],
            "last_observed_on": obs[1],
            "expires_on": obs[2],
            "reason": obs[3],
            "state": obs[4],
            "day": day,
        },
        **layers,
    }


def _pool_name(card: dict[str, Any], *, observing: bool, official: bool) -> str:
    if card.get("mission_status") and card.get("mission_status") not in {
        "ABANDONED",
        None,
        "",
    }:
        return "entered"
    if official:
        return "official"
    if observing:
        return "observing"
    if card.get("status") in {"preview_top", "shortlist", "deep"}:
        return "candidate"
    return "candidate"


def _recommended_action(card: dict[str, Any], layers: dict[str, Any]) -> str:
    if layers.get("star_delta", {}).get("pending"):
        return "等待趋势确认"
    if card.get("strategy_path") in {"ISSUE", "BUG_FIX", "TEST", "DOCUMENTATION"}:
        return "查看切入点"
    if layers.get("decision") == "正式机会":
        return "可以进入"
    return "继续观察"


def _load_stored_events(conn: sqlite3.Connection, repo_id: int) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT occurred_on, kind, payload_json
            FROM observation_events
            WHERE repo_id=?
            ORDER BY occurred_on ASC, kind ASC
            """,
            (int(repo_id),),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict[str, Any]] = []
    for occurred_on, kind, payload_json in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        kind_s = str(kind)
        if kind_s in {
            "stars_delta",
            "contributors_delta",
            "issues_delta",
            "prs_delta",
        }:
            label = format_delta_zh(kind_s, payload)
        else:
            label = EVENT_LABELS_ZH.get(kind_s, kind_s)
        out.append(
            {
                "date": str(occurred_on),
                "kind": kind_s,
                "label_zh": label,
                "payload": payload,
            }
        )
    return out


def _point_value(point: dict[str, Any], key: str) -> int | None:
    for alias in _SERIES_KEYS.get(key, (key,)):
        raw = point.get(alias)
        if raw is None:
            continue
        parsed = _int(raw)
        if parsed is not None:
            return parsed
    return None


def _int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
