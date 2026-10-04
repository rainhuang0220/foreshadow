"""Owner-only traffic. The token never enters SQLite, plans, or work orders."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
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


def _day(timestamp: str, *, as_of: datetime) -> str:
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a timezone")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("traffic timestamp needs a timezone")
    if parsed.date() > as_of.date():
        raise ValueError("future observation")
    return parsed.date().isoformat()


def parse_daily(payload: dict, *, series: str, as_of: datetime) -> list[dict]:
    """Keep only days GitHub returned. An absent day is not zero."""
    if series not in payload or payload[series] is None:
        return []
    rows = []
    seen = set()
    for item in payload[series]:
        day = _day(item["timestamp"], as_of=as_of)
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


def store_daily(conn, *, identity: str, source: str, rows: list[dict], fetched_at: str) -> None:
    if source not in {"views", "clones"}:
        raise ValueError("daily traffic source must be views or clones")
    metric = {
        "views": ("views", "unique_visitors"),
        "clones": ("clones", "unique_cloners"),
    }[source]
    for row in rows:
        pairs = ((metric[0], row["count"]), (metric[1], row["uniques"]))
        for name, value in pairs:
            conn.execute(
                """
                INSERT INTO owner_traffic_observations(
                  identity, source, observed_on, metric, value, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity, source, metric, observed_on)
                DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at
                """,
                (identity, source, row["observed_on"], name, value, fetched_at),
            )
    conn.commit()


def store_window(conn, *, identity: str, source: str, rows: list[dict], fetched_at: str) -> None:
    """Persist a top-list snapshot. observed_on is the fetch date, not a traffic day."""
    if source not in {"referrers", "paths"}:
        raise ValueError("window traffic source must be referrers or paths")
    label_key = "referrer" if source == "referrers" else "path"
    for row in rows:
        if row.get("grain") != "window":
            raise ValueError("referrer and path rows are a window, not a day")
        label = row[label_key]
        for suffix in ("count", "uniques"):
            conn.execute(
                """
                INSERT INTO owner_traffic_observations(
                  identity, source, observed_on, metric, value, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity, source, metric, observed_on)
                DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at
                """,
                (identity, source, row["observed_on"], f"{suffix}:{label}", row[suffix], fetched_at),
            )
    conn.commit()


def record_owner_traffic(conn, *, identity: str, token: str, as_of: datetime, allowed: set[str], opener=None) -> None:
    """Fetch the four read-only traffic reads and store dated rows. The token is not written."""
    if identity not in allowed:
        raise ValueError("owner traffic is limited to configured owned repositories")
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a timezone")
    fetched_at = as_of.isoformat().replace("+00:00", "Z")
    fetched_on = as_of.date().isoformat()
    views = fetch_json(identity, "views", token=token, opener=opener, allowed=allowed)
    clones = fetch_json(identity, "clones", token=token, opener=opener, allowed=allowed)
    referrers = fetch_json(identity, "referrers", token=token, opener=opener, allowed=allowed)
    paths = fetch_json(identity, "paths", token=token, opener=opener, allowed=allowed)
    store_daily(
        conn,
        identity=identity,
        source="views",
        rows=parse_daily(views, series="views", as_of=as_of),
        fetched_at=fetched_at,
    )
    store_daily(
        conn,
        identity=identity,
        source="clones",
        rows=parse_daily(clones, series="clones", as_of=as_of),
        fetched_at=fetched_at,
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=parse_referrers(referrers, fetched_on=fetched_on),
        fetched_at=fetched_at,
    )
    store_window(
        conn,
        identity=identity,
        source="paths",
        rows=parse_paths(paths, fetched_on=fetched_on),
        fetched_at=fetched_at,
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
