"""Owner-only traffic. The token never enters SQLite, plans, or work orders."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

TOKEN_ENV = "FORESHADOW_OWNER_TRAFFIC_TOKEN"
_HOST = "https://api.github.com"
_KINDS = {
    "views": "/repos/{owner}/{repo}/traffic/views?per=day",
    "clones": "/repos/{owner}/{repo}/traffic/clones?per=day",
    "referrers": "/repos/{owner}/{repo}/traffic/popular/referrers",
    "paths": "/repos/{owner}/{repo}/traffic/popular/paths",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("traffic endpoint redirected")


def token_from_env() -> str:
    return os.environ.get(TOKEN_ENV, "")


def redact(text: str, token: str) -> str:
    if token and token in text:
        return text.replace(token, "[redacted]")
    return text


def traffic_url(identity: str, kind: str) -> str:
    if kind not in _KINDS:
        raise ValueError("unsupported traffic endpoint")
    owner, _, repo = identity.partition("/")
    if not owner or not repo or "/" in repo:
        raise ValueError("repository identity must be owner/name")
    url = _HOST + _KINDS[kind].format(owner=owner, repo=repo)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        raise ValueError("traffic URL is not the GitHub API")
    if "/traffic/" not in parsed.path:
        raise ValueError("traffic URL left the traffic API")
    return url


def _optional_int(item: dict, key: str) -> int | None:
    if key not in item or item[key] is None:
        return None
    if type(item[key]) is not int:
        raise ValueError(f"{key} must be an integer or null")
    return item[key]


def utc_now() -> datetime:
    """The production fetch clock. Tests pass their own clock into the recorder."""
    return datetime.now(UTC)


def _fetch_moment(clock: Callable[[], datetime] | None) -> datetime:
    moment = utc_now() if clock is None else clock()
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ValueError("clock needs a timezone")
    return moment


def _day(timestamp: str, *, now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("clock needs a timezone")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("traffic timestamp needs a timezone")
    if parsed.date() > now.date():
        raise ValueError("future observation")
    return parsed.date().isoformat()


def parse_daily(payload: dict, *, series: str, now: datetime) -> list[dict]:
    """Keep only days GitHub returned. An absent day is not zero."""
    if series not in payload or payload[series] is None:
        return []
    rows = []
    seen = set()
    for item in payload[series]:
        day = _day(item["timestamp"], now=now)
        if day in seen:
            raise ValueError("duplicate traffic day")
        seen.add(day)
        count_key = "count"
        rows.append(
            {
                "observed_on": day,
                "count": _optional_int(item, count_key),
                "uniques": _optional_int(item, "uniques"),
            }
        )
    return rows


def parse_referrers(payload: list, *, fetched_on: str) -> list[dict]:
    """A referrer list is one 14-day window, not a daily history."""
    rows = []
    for item in payload:
        name = item.get("referrer")
        if not name:
            continue
        rows.append(
            {
                "observed_on": fetched_on,
                "referrer": name,
                "count": _optional_int(item, "count"),
                "uniques": _optional_int(item, "uniques"),
                "grain": "window",
            }
        )
    return rows


def parse_paths(payload: list, *, fetched_on: str) -> list[dict]:
    rows = []
    for item in payload:
        path = item.get("path")
        if not path:
            continue
        rows.append(
            {
                "observed_on": fetched_on,
                "path": path,
                "count": _optional_int(item, "count"),
                "uniques": _optional_int(item, "uniques"),
                "grain": "window",
            }
        )
    return rows


def fetch_json(identity: str, kind: str, *, token: str, opener=None, allowed=None) -> object:
    if not token:
        raise ValueError("owner traffic token is missing")
    if allowed is not None and identity not in allowed:
        raise ValueError("owner traffic is limited to configured owned repositories")
    url = traffic_url(identity, kind)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "foreshadow-owner-traffic",
        },
        method="GET",
    )
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = redact(exc.read().decode("utf-8", errors="replace"), token)
        raise ValueError(redact(f"traffic request failed: {exc.code} {detail}", token)) from None
    except Exception as exc:
        raise ValueError(redact(f"traffic request failed: {exc}", token)) from None
    return json.loads(body.decode("utf-8"))


def _upsert(
    conn,
    *,
    identity: str,
    source: str,
    observed_on: str,
    metric: str,
    value: int | None,
    fetched_at: str,
    grain: str,
) -> None:
    conn.execute(
        """
        INSERT INTO owner_traffic_observations(
          identity, source, observed_on, metric, value, fetched_at, grain
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(identity, source, metric, observed_on)
        DO UPDATE SET
          value=excluded.value,
          fetched_at=excluded.fetched_at,
          grain=excluded.grain
        """,
        (identity, source, observed_on, metric, value, fetched_at, grain),
    )


def store_daily(conn, *, identity: str, source: str, rows: list[dict], fetched_at: str) -> None:
    if source not in {"views", "clones"}:
        raise ValueError("daily traffic source must be views or clones")
    metric = {
        "views": ("daily_views", "daily_unique_visitors"),
        "clones": ("daily_clones", "daily_unique_cloners"),
    }[source]
    for row in rows:
        pairs = ((metric[0], row["count"]), (metric[1], row["uniques"]))
        for name, value in pairs:
            _upsert(
                conn,
                identity=identity,
                source=source,
                observed_on=row["observed_on"],
                metric=name,
                value=value,
                fetched_at=fetched_at,
                grain="day",
            )
    conn.commit()


def store_response_totals(
    conn,
    *,
    identity: str,
    source: str,
    observed_on: str,
    payload: dict,
    fetched_at: str,
) -> None:
    """Store the views/clones top-level count and uniques for the last 14 days.

    GitHub's REST description for those endpoints is the total plus a per-day
    breakdown. The total is a separate field. It is not the sum of daily uniques.
    A missing key is left unstored. A returned zero is stored as zero.
    """
    if source not in {"views", "clones"}:
        raise ValueError("response totals come from views or clones")
    metric = {
        "views": ("rolling_14d_views", "rolling_14d_unique_visitors"),
        "clones": ("rolling_14d_clones", "rolling_14d_unique_cloners"),
    }[source]
    for key, name in (("count", metric[0]), ("uniques", metric[1])):
        if key not in payload:
            continue
        _upsert(
            conn,
            identity=identity,
            source=source,
            observed_on=observed_on,
            metric=name,
            value=_optional_int(payload, key),
            fetched_at=fetched_at,
            grain="window",
        )
    conn.commit()


def store_window(
    conn,
    *,
    identity: str,
    source: str,
    rows: list[dict],
    fetched_at: str,
    observed_on: str | None = None,
) -> None:
    """Replace one top-list snapshot. observed_on is the fetch date, not a traffic day."""
    if source not in {"referrers", "paths"}:
        raise ValueError("window traffic source must be referrers or paths")
    label_key = "referrer" if source == "referrers" else "path"
    dates = {row["observed_on"] for row in rows}
    if observed_on is None:
        if len(dates) != 1:
            raise ValueError("a window snapshot has one fetch date")
        observed_on = next(iter(dates))
    elif dates and dates != {observed_on}:
        raise ValueError("a window snapshot has one fetch date")
    conn.execute("SAVEPOINT owner_traffic_snapshot")
    try:
        conn.execute(
            """
            DELETE FROM owner_traffic_observations
            WHERE identity=? AND source=? AND observed_on=?
            """,
            (identity, source, observed_on),
        )
        for row in rows:
            if row.get("grain") != "window":
                raise ValueError("referrer and path rows are a window, not a day")
            label = row[label_key]
            for name, key in (("window_count", "count"), ("window_uniques", "uniques")):
                _upsert(
                    conn,
                    identity=identity,
                    source=source,
                    observed_on=observed_on,
                    metric=f"{name}:{label}",
                    value=row[key],
                    fetched_at=fetched_at,
                    grain="window",
                )
    except Exception:
        conn.execute("ROLLBACK TO owner_traffic_snapshot")
        conn.execute("RELEASE owner_traffic_snapshot")
        raise
    conn.execute("RELEASE owner_traffic_snapshot")
    conn.commit()


def record_owner_traffic(
    conn,
    *,
    identity: str,
    token: str,
    allowed: set[str],
    opener=None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Fetch the four read-only traffic reads and store dated rows. The token is not written.

    fetched_at and the referrer/path snapshot date come from clock, or from the
    process clock when clock is omitted. A caller-supplied historical date is
    not accepted under another name: the live command does not pass one.
    """
    if identity not in allowed:
        raise ValueError("owner traffic is limited to configured owned repositories")
    moment = _fetch_moment(clock)
    fetched_at = moment.isoformat().replace("+00:00", "Z")
    fetched_on = moment.date().isoformat()
    views = fetch_json(identity, "views", token=token, opener=opener, allowed=allowed)
    clones = fetch_json(identity, "clones", token=token, opener=opener, allowed=allowed)
    referrers = fetch_json(identity, "referrers", token=token, opener=opener, allowed=allowed)
    paths = fetch_json(identity, "paths", token=token, opener=opener, allowed=allowed)
    view_rows = parse_daily(views, series="views", now=moment)
    clone_rows = parse_daily(clones, series="clones", now=moment)
    referrer_rows = parse_referrers(referrers, fetched_on=fetched_on)
    path_rows = parse_paths(paths, fetched_on=fetched_on)
    store_daily(conn, identity=identity, source="views", rows=view_rows, fetched_at=fetched_at)
    store_response_totals(
        conn,
        identity=identity,
        source="views",
        observed_on=fetched_on,
        payload=views,
        fetched_at=fetched_at,
    )
    store_daily(conn, identity=identity, source="clones", rows=clone_rows, fetched_at=fetched_at)
    store_response_totals(
        conn,
        identity=identity,
        source="clones",
        observed_on=fetched_on,
        payload=clones,
        fetched_at=fetched_at,
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=referrer_rows,
        fetched_at=fetched_at,
        observed_on=fetched_on,
    )
    store_window(
        conn,
        identity=identity,
        source="paths",
        rows=path_rows,
        fetched_at=fetched_at,
        observed_on=fetched_on,
    )


def load_metric(conn, *, identity: str, metric: str) -> list[dict]:
    found = conn.execute(
        """
        SELECT observed_on, value FROM owner_traffic_observations
        WHERE identity=? AND metric=?
        ORDER BY observed_on
        """,
        (identity, metric),
    ).fetchall()
    return [{"observed_on": day, "value": value} for day, value in found]
