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
    users = (
        importlib.resources.files("foreshadow")
        .joinpath("sql/002_users.sql")
        .read_text()
    )
    assert "CREATE TABLE users" in users
    assert "password_hash" in users
    v3 = (
        importlib.resources.files("foreshadow")
        .joinpath("sql/003_score_version.sql")
        .read_text()
    )
    assert "score_version" in v3
    assert "UNIQUE (run_id, repo_id, score_version)" in v3
    assert "CREATE TABLE score_compare" in v3
    v4 = (
        importlib.resources.files("foreshadow")
        .joinpath("sql/004_missions.sql")
        .read_text()
    )
    assert "CREATE TABLE entry_missions" in v4
    v5 = (
        importlib.resources.files("foreshadow")
        .joinpath("sql/005_learning.sql")
        .read_text()
    )
    assert "CREATE TABLE contribution_events" in v5


def test_migrate_adds_users_and_backfills_reviews(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    row = conn.execute(
        "SELECT username, is_local FROM users WHERE is_local=1"
    ).fetchone()
    assert row[0] == "local"
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reviews)")]
    assert "user_id" in cols
    score_cols = [r[1] for r in conn.execute("PRAGMA table_info(scores)")]
    assert "score_version" in score_cols
    assert "pool_rank" in score_cols
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "score_compare" in tables


def test_migrate_copies_existing_scores_as_v1(tmp_home):
    import importlib.resources
    from datetime import UTC, datetime

    conn = connect(tmp_home / "foreshadow.sqlite3")
    for version, filename in ((1, "001_init.sql"), (2, "002_users.sql")):
        sql = (
            importlib.resources.files("foreshadow")
            .joinpath(f"sql/{filename}")
            .read_text(encoding="utf-8")
        )
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) "
        "VALUES ('R1','a/b','a','b','t','t')"
    )
    rid = conn.execute("SELECT id FROM repos").fetchone()[0]
    conn.execute(
        "INSERT INTO daily_runs(run_date, started_at, status, budget_cap) "
        "VALUES ('2026-08-24','t','complete',800)"
    )
    run_id = conn.execute("SELECT id FROM daily_runs").fetchone()[0]
    conn.execute(
        """
        INSERT INTO scores(
          run_id, repo_id, opportunity, explosion, contribution, confidence,
          components_json, evidence_json, flags_json, scored_at
        ) VALUES (?,?,50,NULL,40,'low','{}','{}','[]','t')
        """,
        (run_id, rid),
    )
    conn.commit()
    migrate(conn)
    row = conn.execute(
        "SELECT score_version, opportunity, pool_rank FROM scores"
    ).fetchone()
    assert row[0] == "v1"
    assert row[1] == 50
    assert row[2] is None
    assert (
        conn.execute("SELECT COUNT(*) FROM scores WHERE score_version='v2'").fetchone()[
            0
        ]
        == 0
    )
