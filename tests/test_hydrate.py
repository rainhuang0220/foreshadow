import json

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.github.rest import fetch_contributors
from foreshadow.pipeline.discover import discover_hydrate_snapshot
from foreshadow.pipeline.h_rules import evaluate_h
from foreshadow.pipeline.hydrate import unique_committers_30d
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.snapshot import payload_from_graphql, upsert_snapshot


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
