from fakes import FakeGitHub, repo_node, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline.discover import discover_hydrate_snapshot


def test_second_run_same_utc_date_replaces_candidates_not_reviews(
    tmp_home, frozen_clock
):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_a", "acme/a")
    gh = FakeGitHub(nodes={"R_a": node}, search_nodes=[node])
    r1 = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    repo_id = conn.execute("SELECT id FROM repos WHERE node_id='R_a'").fetchone()[0]
    seed_review(conn, repo_id, "watch", "2026-08-24T01:00:00+00:00", run_id=r1.run_id)
    conn.execute(
        """
        INSERT INTO scores(
          run_id, repo_id, opportunity, explosion, contribution, confidence,
          components_json, evidence_json, flags_json, scored_at
        ) VALUES (?, ?, 1, 1, 1, 'low', '{}', '{}', '[]', ?)
        """,
        (r1.run_id, repo_id, frozen_clock.now().isoformat()),
    )
    conn.commit()
    r2 = discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    assert r1.run_id == r2.run_id
    runs = conn.execute("SELECT COUNT(*) FROM daily_runs").fetchone()[0]
    assert runs == 1
    cands = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE run_id=?", (r2.run_id,)
    ).fetchone()[0]
    assert cands == 1
    scores = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE run_id=?", (r2.run_id,)
    ).fetchone()[0]
    assert scores == 0
    reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    assert reviews == 1
    snaps = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE repo_id=? AND snapshot_date='2026-08-24'",
        (repo_id,),
    ).fetchone()[0]
    assert snaps == 1


def test_force_bypasses_graphql_cache(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_b", "acme/b")
    gh = FakeGitHub(nodes={"R_b": node}, search_nodes=[node])
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock, force=False)
    n1 = gh.graphql_network_calls
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock, force=False)
    n2 = gh.graphql_network_calls
    assert n2 == n1
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock, force=True)
    n3 = gh.graphql_network_calls
    assert n3 > n2


def test_snapshot_upsert_same_date(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_c", "acme/c", stargazerCount=10)
    gh = FakeGitHub(nodes={"R_c": node}, search_nodes=[node])
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    node["stargazerCount"] = 99
    gh.nodes["R_c"] = node
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock, force=True)
    rows = conn.execute(
        "SELECT stars FROM snapshots WHERE snapshot_date='2026-08-24'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 99
