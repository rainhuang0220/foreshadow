from foreshadow.db import connect, migrate


def test_schema_unique_snapshot(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) VALUES ('X','a/b','a','b','t','t')"
    )
    rid = conn.execute("SELECT id FROM repos").fetchone()[0]
    conn.execute(
        "INSERT INTO snapshots(repo_id, snapshot_date, captured_at, completeness) VALUES (?,?,?,1)",
        (rid, "2026-08-24", "t"),
    )
    import sqlite3

    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO snapshots(repo_id, snapshot_date, captured_at, completeness) VALUES (?,?,?,1)",
            (rid, "2026-08-24", "t"),
        )


def test_sql_packaged():
    import importlib.resources

    text = (
        importlib.resources.files("foreshadow").joinpath("sql/001_init.sql").read_text()
    )
    assert "CREATE TABLE repos" in text
    assert "unique_human_authors_100" not in text
