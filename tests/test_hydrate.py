import json
from datetime import date

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.github.rest import fetch_contributors
from foreshadow.pipeline.discover import discover_hydrate_snapshot
from foreshadow.pipeline.features import SnapshotPoint, star_velocity
from foreshadow.pipeline.h_rules import evaluate_h
from foreshadow.pipeline.hydrate import (
    build_features_blob,
    hydrate_a_many,
    unique_committers_30d,
)
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.snapshot import payload_from_graphql, upsert_snapshot


def _star_payload(stars: int, forks: int = 10, captured_at: str = "") -> dict:
    return {
        "stars": stars,
        "forks": forks,
        "open_issues": 1,
        "open_prs": 0,
        "last_pushed_at": "2026-08-20T00:00:00Z",
        "created_at": "2026-05-01T00:00:00Z",
        "captured_at": captured_at or "2026-08-24T00:05:00+00:00",
        "topics_json": "[]",
        "features_json": "{}",
    }


def test_open_issues_count_not_stored(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_x", "acme/x")
    mixed = {
        "stargazerCount": 10,
        "forkCount": 1,
        "open_issues_count": 99,
        "watchers_count": 10,
        "watchers": 10,
        "stargazers_count": 10,
        "issuesOpen": {"totalCount": 3},
        "issuesClosed": {"totalCount": 8},
        "prsOpen": {"totalCount": 2},
        "pushedAt": "2026-08-20T00:00:00Z",
        "createdAt": "2026-01-01T00:00:00Z",
        "defaultBranchRef": {
            "name": "main",
            "target": {"committedDate": "2026-08-20T00:00:00Z"},
        },
        "discussions": {"totalCount": 0},
        "repositoryTopics": {"nodes": []},
    }
    payload = payload_from_graphql(
        mixed,
        captured_at=frozen_clock.now().isoformat(),
        created_at="2026-01-01T00:00:00Z",
    )
    upsert_snapshot(conn, rid, "2026-08-24", payload)
    conn.commit()
    row = conn.execute(
        "SELECT open_issues, watchers, stars, open_prs FROM snapshots WHERE repo_id=?",
        (rid,),
    ).fetchone()
    assert row[0] == 3
    assert row[0] != 99
    assert row[1] is None
    assert row[2] == 10
    assert row[3] == 2


def test_watchers_always_null_even_if_rest_payload(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_y", "acme/y")
    payload = payload_from_graphql(
        {
            "stargazerCount": 50,
            "forkCount": 4,
            "watchers_count": 50,
            "subscribers_count": 7,
            "issuesOpen": {"totalCount": 1},
            "prsOpen": {"totalCount": 0},
        },
        captured_at=frozen_clock.now().isoformat(),
        created_at="2026-01-01T00:00:00Z",
    )
    upsert_snapshot(conn, rid, "2026-08-24", payload)
    watchers = conn.execute("SELECT watchers FROM snapshots").fetchone()[0]
    assert watchers is None
    assert "watchers" not in (payload.get("features_json") or "")


def test_unique_committers_are_authors_not_commit_count():
    commits = [
        {"author": {"login": "alice", "type": "User"}},
        {"author": {"login": "alice", "type": "User"}},
        {"author": {"login": "bob", "type": "User"}},
        {"author": {"login": "dependabot[bot]", "type": "Bot"}},
        {
            "author": None,
            "commit": {"author": {"name": "Anon", "email": "a@e.com"}},
        },
    ]
    assert unique_committers_30d(commits) == 3
    assert unique_committers_30d(commits) != len(commits)


def test_unique_committers_land_in_snapshot(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_c", "acme/c")
    rid = seed_repo(conn, "R_c", "acme/c")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    commits = [
        {"author": {"login": "alice", "type": "User"}},
        {"author": {"login": "alice", "type": "User"}},
        {"author": {"login": "bob", "type": "User"}},
    ]
    gh = FakeGitHub(nodes={"R_c": node}, commits={"acme/c": commits})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    u = conn.execute(
        "SELECT unique_committers_30d FROM snapshots WHERE repo_id=?", (rid,)
    ).fetchone()[0]
    assert u == 2


def test_contributor_pagination_stops_early():
    page1 = [{"login": f"u{i}", "type": "User"} for i in range(80)]
    page2 = [{"login": "extra", "type": "User"}]
    gh = FakeGitHub(contributor_pages={"acme/c": [page1, page2]})
    rows = fetch_contributors(gh, "acme", "c")
    assert len(rows) == 80
    assert gh.contributor_requests == [("acme/c", 1)]


def test_rest_errors_do_not_zero_fill(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node(
        "R_x",
        "acme/x",
        stargazerCount=6000,
        forkCount=10,
        createdAt="2026-07-20T00:00:00Z",
    )
    rid = seed_repo(conn, "R_x", "acme/x", created_at="2026-07-20T00:00:00Z")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(
        nodes={"R_x": node},
        rest_status={
            ("acme/x", "contributors"): 403,
            ("acme/x", "commits"): 500,
            ("acme/x", "contents"): 500,
            ("acme/x", "workflows"): 403,
        },
    )
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        """
        SELECT contributor_count, unique_committers_30d, features_json, stars
        FROM snapshots WHERE repo_id=?
        """,
        (rid,),
    ).fetchone()
    assert row[3] == 6000
    assert row[0] is None
    assert row[1] is None
    feat = json.loads(row[2] or "{}")
    assert feat.get("gap_tests") is None
    assert feat.get("gap_ci") is None
    assert feat.get("tree_names") is None
    h = evaluate_h(
        {
            "age_days": 35,
            "S": 6000,
            "fork_star": 10 / 6000,
            "U_commit_30d": row[1],
            "C": row[0],
            "features": feat,
            "tree_names": feat.get("tree_names"),
        }
    )
    assert "H6" not in h.fired
    scored = score_repo(
        {
            "owner": "acme",
            "full_name": "acme/x",
            "S": 6000,
            "F": 10,
            "C": row[0],
            "U_commit_30d": row[1],
            "age_days": 35,
            "created_at": "2026-07-20",
            "features": feat,
            "snapshots": [{"date": "2026-08-24", "stars": 6000, "forks": 10}],
        },
        clock=frozen_clock,
    )
    assert "contributor_starved" not in scored.breakdown.flags


def test_contributors_204_is_c_zero(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_z", "acme/z")
    rid = seed_repo(conn, "R_z", "acme/z")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(nodes={"R_z": node}, rest_status={("acme/z", "contributors"): 204})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    c = conn.execute(
        "SELECT contributor_count FROM snapshots WHERE repo_id=?", (rid,)
    ).fetchone()[0]
    assert c == 0


def test_phase_b_404_keeps_phase_a_snapshot(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_b", "acme/b", stargazerCount=42, forkCount=7)
    rid = seed_repo(conn, "R_b", "acme/b")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(nodes={"R_b": node}, b_missing={"R_b"})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        """
        SELECT stars, forks, open_issues, contributor_count, features_json
        FROM snapshots WHERE repo_id=? AND snapshot_date='2026-08-24'
        """,
        (rid,),
    ).fetchone()
    assert row is not None
    assert row[0] == 42
    assert row[1] == 7
    assert row[2] == 4
    assert row[3] is None
    assert row[4] in ("{}", None)
    status = conn.execute(
        "SELECT hydrate_status FROM candidates WHERE repo_id=?", (rid,)
    ).fetchone()[0]
    assert status in {"not_found", "incomplete"}


def test_failed_phase_a_does_not_upsert_null_star_row(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_fail", "acme/fail", stargazerCount=900)
    rid = seed_repo(conn, "R_fail", "acme/fail")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    upsert_snapshot(conn, rid, "2026-08-16", _star_payload(200, 18))
    upsert_snapshot(conn, rid, "2026-08-23", _star_payload(850, 80))
    conn.commit()
    gh = FakeGitHub(nodes={"R_fail": node}, fail_ids={"R_fail"})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    today = conn.execute(
        """
        SELECT stars FROM snapshots
        WHERE repo_id=? AND snapshot_date='2026-08-24'
        """,
        (rid,),
    ).fetchone()
    assert today is None
    nulls = conn.execute(
        "SELECT snapshot_date FROM snapshots WHERE repo_id=? AND stars IS NULL",
        (rid,),
    ).fetchall()
    assert nulls == []
    status = conn.execute(
        "SELECT hydrate_status FROM candidates WHERE repo_id=?", (rid,)
    ).fetchone()[0]
    assert status == "failed"


def test_failed_phase_a_keeps_today_stars_v7_slack(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_x", "acme/x", stargazerCount=900)
    rid = seed_repo(conn, "R_x", "acme/x")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    upsert_snapshot(conn, rid, "2026-08-16", _star_payload(200, 18))
    upsert_snapshot(conn, rid, "2026-08-24", _star_payload(900, 85))
    conn.commit()
    gh = FakeGitHub(nodes={"R_x": node}, fail_ids={"R_x"})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        """
        SELECT stars FROM snapshots
        WHERE repo_id=? AND snapshot_date='2026-08-24'
        """,
        (rid,),
    ).fetchone()
    assert row is not None
    assert row[0] == 900
    rows = conn.execute(
        """
        SELECT snapshot_date, stars, forks FROM snapshots
        WHERE repo_id=? ORDER BY snapshot_date
        """,
        (rid,),
    ).fetchall()
    assert not any(r[1] is None for r in rows)
    snaps = [
        SnapshotPoint(date.fromisoformat(str(r[0])), r[1], r[2], None) for r in rows
    ]
    v, src = star_velocity(snaps, date(2026, 8, 24), 7, slack_days=1)
    assert src == "nearest-1d"
    assert v == (900 - 200) / 7


def test_empty_phase_b_issue_sample_is_zero_not_na(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node(
        "R_empty",
        "acme/emptyiss",
        issuesOpen={"totalCount": 0},
        issuesClosed={"totalCount": 0},
        issuesOpenSample={"totalCount": 0, "nodes": []},
        issuesClosedSample={"nodes": []},
    )
    rid = seed_repo(conn, "R_empty", "acme/emptyiss")
    seed_review(conn, rid, "watch", "2026-08-23T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(nodes={"R_empty": node})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    feat = json.loads(
        conn.execute(
            "SELECT features_json FROM snapshots WHERE repo_id=?", (rid,)
        ).fetchone()[0]
        or "{}"
    )
    assert feat.get("help_n") == 0
    assert feat.get("u_issue") == 0
    assert feat.get("u_issue_ext") == 0
    assert feat.get("bug_n") == 0
    assert feat.get("talk_n") == 0
    assert feat.get("repeat_clusters") == 0
    assert feat.get("unassigned_help") == 0
    assert feat.get("issue_sample_n") == 0
    scored = score_repo(
        {
            "owner": "acme",
            "name": "emptyiss",
            "full_name": "acme/emptyiss",
            "S": 100,
            "F": 10,
            "C": 1,
            "has_issues": True,
            "created_at": "2026-05-01T00:00:00Z",
            "features": feat,
            "snapshots": [{"date": "2026-08-24", "stars": 100, "forks": 10}],
        },
        clock=frozen_clock,
    )
    assert scored.breakdown.contribution_opp.value is not None


def test_missing_phase_b_issue_sample_stays_na():
    repo = repo_node("R_a", "acme/a")
    del repo["issuesOpenSample"]
    del repo["issuesClosedSample"]
    rest = {
        "contents": [
            {"name": "README.md", "type": "file"},
            {"name": "src", "type": "dir"},
            {"name": "pyproject.toml", "type": "file"},
        ],
        "workflows": {"total_count": 1, "workflows": [{"name": "ci"}]},
        "community": {"health_percentage": 70, "files": {"contributing": None}},
    }
    blob = build_features_blob(repo, rest)
    assert blob.help_n is None
    assert blob.u_issue is None
    assert blob.repeat_clusters is None
    assert blob.bug_n is None
    assert blob.issue_sample_n is None


def test_open_issue_titles_include_number():
    repo = repo_node("R_num", "acme/num")
    repo["issuesOpenSample"] = {
        "totalCount": 1,
        "nodes": [
            {
                "number": 12,
                "title": "crash on eviction",
                "author": {"login": "bob"},
                "authorAssociation": "NONE",
                "labels": {"nodes": []},
                "comments": {"totalCount": 0, "nodes": []},
                "assignees": {"totalCount": 0},
            }
        ],
    }
    blob = build_features_blob(repo, {"contents": [], "workflows": {}, "community": {}})
    assert blob.open_issue_titles == ["#12 crash on eviction"]


def test_hydrate_a_many_keeps_fake_github_serial():
    memkit = repo_node("R_memkit", "acme/memkit")
    other = repo_node("R_other", "acme/other")
    gh = FakeGitHub(nodes={"R_memkit": memkit, "R_other": other})
    out = hydrate_a_many(gh, ["R_memkit", "R_other"], force=True)
    assert set(out) == {"R_memkit", "R_other"}
    body, err = out["R_memkit"]
    assert err is None
    assert body is not None
