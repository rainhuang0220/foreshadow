from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline.discover import discover_hydrate_snapshot


def test_deleted_suffixes_full_name(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_old", "acme/gone")
    seed_review(conn, rid, "watch", "2026-08-20T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(missing={"R_old"}, nodes={})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        "SELECT full_name, status, id FROM repos WHERE node_id=?", ("R_old",)
    ).fetchone()
    assert row[1] == "not_found"
    assert row[0] == "acme/gone#deleted-R_old"
    reviews = conn.execute("SELECT repo_id FROM reviews").fetchall()
    assert [r[0] for r in reviews] == [rid]


def test_renamed_updates_full_name_and_alias(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    node = repo_node("R_1", "acme/new", description="renamed")
    rid = seed_repo(conn, "R_1", "acme/old")
    seed_review(conn, rid, "watch", "2026-08-20T00:00:00+00:00")
    conn.commit()
    gh = FakeGitHub(nodes={"R_1": node})
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    row = conn.execute(
        "SELECT full_name, status, id FROM repos WHERE node_id=?", ("R_1",)
    ).fetchone()
    assert row[0] == "acme/new"
    assert row[1] == "active"
    assert row[2] == rid
    aliases = conn.execute(
        "SELECT full_name FROM repo_aliases WHERE repo_id=? ORDER BY full_name",
        (rid,),
    ).fetchall()
    assert "acme/old" in [a[0] for a in aliases]
    assert conn.execute("SELECT repo_id FROM reviews").fetchone()[0] == rid


def test_name_reuse_two_rows_no_merge(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    old_id = seed_repo(conn, "R_old", "acme/memkit#deleted-R_old", status="not_found")
    seed_review(conn, old_id, "watch", "2026-08-01T00:00:00+00:00")
    conn.commit()
    new = repo_node("R_new", "acme/memkit")
    gh = FakeGitHub(nodes={"R_new": new}, search_nodes=[new])
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    rows = conn.execute(
        "SELECT node_id, full_name, status FROM repos ORDER BY node_id"
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    assert by_id["R_old"][1] == "acme/memkit#deleted-R_old"
    assert by_id["R_new"][1] == "acme/memkit"
    assert by_id["R_new"][2] == "active"
    assert conn.execute("SELECT repo_id FROM reviews").fetchone()[0] == old_id


def test_same_run_race_suffix_then_insert(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    old_id = seed_repo(conn, "R_old", "acme/memkit")
    seed_review(conn, old_id, "interested", "2026-08-20T00:00:00+00:00")
    conn.commit()
    new = repo_node("R_new", "acme/memkit", description="occupant")
    gh = FakeGitHub(
        nodes={"R_new": new},
        missing={"R_old"},
        search_nodes=[new],
    )
    discover_hydrate_snapshot(conn, gh, Settings(), clock=frozen_clock)
    rows = conn.execute(
        "SELECT node_id, full_name, status, id FROM repos ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    by_nid = {r[0]: r for r in rows}
    assert by_nid["R_old"][1] == "acme/memkit#deleted-R_old"
    assert by_nid["R_old"][2] == "not_found"
    assert by_nid["R_new"][1] == "acme/memkit"
    assert by_nid["R_new"][2] == "active"
    assert by_nid["R_old"][3] == old_id
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
    assert conn.execute("SELECT repo_id FROM reviews").fetchone()[0] == old_id
    names = [r[1] for r in rows]
    assert names.count("acme/memkit") == 1
