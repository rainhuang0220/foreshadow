"""UTC calendar dates and observation TTL. Does not retune scoring."""

from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fakes import FakeGitHub, repo_node, seed_repo
from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.db import connect, migrate
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.discover import discover_hydrate_snapshot
from foreshadow.pipeline.observation import (
    admit_from_scores,
    expire_due,
    load_active,
)
from foreshadow.pipeline.score import ScoredRepo

_DESC = "A substantial project description for discovery tests."
_TTL = DiscoverySettings().observation_ttl_days


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def _keep(node_id: str, full_name: str, **over) -> dict:
    over.setdefault("topics", ["mcp"])
    over.setdefault("forkCount", 3)
    over.setdefault("description", _DESC)
    return repo_node(node_id, full_name, **over)


def _scored(full_name: str, opportunity: float) -> ScoredRepo:
    mid = ComponentScore(value=20, confidence="medium")
    bd = ScoreBreakdown(
        opportunity=ComponentScore(value=opportunity, confidence="medium"),
        explosion=ComponentScore(value=None, confidence="low", missing=["v7"]),
        contribution=mid,
        momentum=ComponentScore(value=None, confidence="low", missing=["v7"]),
        real_user=mid,
        gap=mid,
        contribution_opp=mid,
        early_entry=mid,
        direction_fit=ComponentScore(value=80, confidence="medium"),
        maintainer=mid,
    )
    return ScoredRepo(
        owner=full_name.split("/", 1)[0],
        full_name=full_name,
        breakdown=bd,
        evidence={},
    )


def _tzset(name: str | None) -> None:
    tzset = getattr(time, "tzset", None)
    if tzset is None:
        return
    if name is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = name
    tzset()


def test_clock_today_is_utc_under_shanghai_and_la():
    """Laptop TZ must not change Clock.today(); snapshot identity is UTC."""
    utc = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    assert utc.astimezone(ZoneInfo("America/Los_Angeles")).date() == date(2026, 8, 23)
    assert utc.astimezone(ZoneInfo("Asia/Shanghai")).date() == date(2026, 8, 24)
    prev = os.environ.get("TZ")
    try:
        for tz in ("Asia/Shanghai", "America/Los_Angeles"):
            _tzset(tz)
            clock = Clock(now=utc)
            assert clock.today() == date(2026, 8, 24)
            assert clock.now().tzinfo is not None
            assert clock.now().utcoffset() == timedelta(0)
        # Shanghai local date is already the 24th; pick a UTC instant where CST is next day.
        split = datetime(2026, 8, 23, 16, 30, tzinfo=UTC)
        assert split.astimezone(ZoneInfo("Asia/Shanghai")).date() == date(2026, 8, 24)
        assert split.astimezone(ZoneInfo("America/Los_Angeles")).date() == date(
            2026, 8, 23
        )
        for tz in ("Asia/Shanghai", "America/Los_Angeles"):
            _tzset(tz)
            assert Clock(now=split).today() == date(2026, 8, 23)
    finally:
        _tzset(prev)


def test_snapshot_date_is_utc_not_local_tz(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    utc = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)
    node = _keep("R_keep", "acme/keep")
    prev = os.environ.get("TZ")
    try:
        for tz in ("Asia/Shanghai", "America/Los_Angeles"):
            _tzset(tz)
            conn = connect(tmp_home / f"{tz.replace('/', '_')}.sqlite3")
            migrate(conn)
            gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[node])
            clock = Clock(now=utc)
            discover_hydrate_snapshot(conn, gh, Settings(), clock=clock)
            dates = [
                row[0]
                for row in conn.execute("SELECT DISTINCT snapshot_date FROM snapshots")
            ]
            assert dates == ["2026-08-24"], tz
            assert clock.today().isoformat() == "2026-08-24"
            conn.close()
    finally:
        _tzset(prev)


def test_ttl_day0_live_through_day14_gone_day15(tmp_home):
    """System observation TTL is 14 calendar days from added_on, not sliding.

    Day 0 is added_on. expires_on = added_on + observation_ttl_days (default 14).
    expire_due uses ``expires_on < today`` and load_active uses
    ``expires_on >= today``, so the expiry calendar date (Day 14) is still
    live and Day 15 is gone. Last_observed_on does not extend membership.
    """
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    day0 = date(2026, 8, 24)
    rid = seed_repo(conn, "R_ttl", "acme/ttl")
    scored = _scored("acme/ttl", 40)
    n = admit_from_scores(
        conn,
        today=day0,
        scored_rows=[(rid, scored, {"node_id": "R_ttl"})],
        selected_ids=set(),
        watchlist_ids=set(),
        disc=DiscoverySettings(),
    )
    assert n == 1
    expires = conn.execute(
        "SELECT expires_on, added_on FROM observations WHERE repo_id=?", (rid,)
    ).fetchone()
    assert expires[1] == day0.isoformat()
    assert expires[0] == (day0 + timedelta(days=_TTL)).isoformat()
    assert expires[0] == "2026-09-07"
    conn.execute(
        "UPDATE observations SET last_observed_on=? WHERE repo_id=?",
        ((day0 + timedelta(days=10)).isoformat(), rid),
    )
    conn.commit()
    for offset in range(_TTL + 1):
        day = day0 + timedelta(days=offset)
        expired = expire_due(conn, day)
        assert expired == 0, f"Day{offset} ({day}) must not expire"
        active = load_active(conn, day)
        assert [e.repo_id for e in active] == [rid], f"Day{offset} must stay live"
    day15 = day0 + timedelta(days=_TTL + 1)
    assert day15.isoformat() == "2026-09-08"
    assert expire_due(conn, day15) == 1
    assert load_active(conn, day15) == []
    state = conn.execute("SELECT state FROM observations WHERE repo_id=?", (rid,))
    assert state.fetchone()[0] == "expired"


def test_ttl_crosses_year_boundary(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_nye", "acme/nye")
    added = date(2026, 12, 20)
    n = admit_from_scores(
        conn,
        today=added,
        scored_rows=[(rid, _scored("acme/nye", 40), {"node_id": "R_nye"})],
        selected_ids=set(),
        watchlist_ids=set(),
        disc=DiscoverySettings(),
    )
    assert n == 1
    expires = conn.execute("SELECT expires_on FROM observations").fetchone()[0]
    assert expires == "2027-01-03"
    assert load_active(conn, date(2027, 1, 3))
    assert expire_due(conn, date(2027, 1, 3)) == 0
    assert expire_due(conn, date(2027, 1, 4)) == 1
    assert load_active(conn, date(2027, 1, 4)) == []


def test_day_boundary_235959_and_000000(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = _keep("R_keep", "acme/keep")
    gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[node])
    late = Clock(now=datetime(2026, 8, 24, 23, 59, 59, tzinfo=UTC))
    gh.begin_day(late.today())
    discover_hydrate_snapshot(conn, gh, Settings(), clock=late)
    early = Clock(now=datetime(2026, 8, 25, 0, 0, 0, tzinfo=UTC))
    gh.begin_day(early.today())
    discover_hydrate_snapshot(conn, gh, Settings(), clock=early)
    dates = [
        row[0]
        for row in conn.execute(
            "SELECT snapshot_date FROM snapshots ORDER BY snapshot_date"
        )
    ]
    assert dates == ["2026-08-24", "2026-08-25"]
    runs = [
        row[0]
        for row in conn.execute("SELECT run_date FROM daily_runs ORDER BY run_date")
    ]
    assert runs == ["2026-08-24", "2026-08-25"]
    assert late.today() == date(2026, 8, 24)
    assert early.today() == date(2026, 8, 25)


def test_month_and_year_boundary_snapshot_dates(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = _keep("R_keep", "acme/keep")
    gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[node])
    edges = [
        datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC),
        datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC),
    ]
    for when in edges:
        clock = Clock(now=when)
        gh.begin_day(clock.today())
        discover_hydrate_snapshot(conn, gh, Settings(), clock=clock)
    dates = [
        row[0]
        for row in conn.execute(
            "SELECT snapshot_date FROM snapshots ORDER BY snapshot_date"
        )
    ]
    assert dates == ["2026-02-28", "2026-03-01", "2026-12-31", "2027-01-01"]
    assert Clock(now=edges[0]).today() == date(2026, 2, 28)
    assert Clock(now=edges[1]).today() == date(2026, 3, 1)
    assert Clock(now=edges[2]).today() == date(2026, 12, 31)
    assert Clock(now=edges[3]).today() == date(2027, 1, 1)
