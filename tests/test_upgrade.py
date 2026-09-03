"""P0 DB upgrade to schema 8 and empty-HOME clean install."""

from __future__ import annotations

import importlib.resources
import os
import stat
from datetime import UTC, date, datetime

from typer.testing import CliRunner

from fakes import FakeGitHub, repo_node
from foreshadow import __version__
from foreshadow.auth import ensure_local_user
from foreshadow.cli import app
from foreshadow.config import ScoringSettings, Settings, user_config_path
from foreshadow.db import SCHEMA_VERSION, connect, migrate
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.discover import load_watchlist

_DESC = "A substantial project description for discovery tests."


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def _apply_sql(conn, version: int, filename: str) -> None:
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
    conn.commit()


def _versions(conn) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ]


def test_p0_schema1_upgrade_to_6_preserves_reviews_and_watchlist(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    _apply_sql(conn, 1, "001_init.sql")
    assert _versions(conn) == [1]
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) "
        "VALUES ('R_w','acme/watched','acme','watched','t','t')"
    )
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) "
        "VALUES ('R_i','acme/other','acme','other','t','t')"
    )
    watched = conn.execute("SELECT id FROM repos WHERE node_id='R_w'").fetchone()[0]
    other = conn.execute("SELECT id FROM repos WHERE node_id='R_i'").fetchone()[0]
    conn.execute(
        """
        INSERT INTO daily_runs(run_date, started_at, status, budget_cap)
        VALUES ('2026-08-20','t','complete',800)
        """
    )
    run_id = conn.execute("SELECT id FROM daily_runs").fetchone()[0]
    conn.execute(
        "INSERT INTO reviews(repo_id, action, note, run_id, created_at) VALUES (?,?,?,?,?)",
        (watched, "watch", "keep-watch", run_id, "2026-08-20T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO reviews(repo_id, action, note, run_id, created_at) VALUES (?,?,?,?,?)",
        (other, "interested", "keep-interest", None, "2026-08-21T00:00:00+00:00"),
    )
    conn.execute(
        """
        INSERT INTO snapshots(repo_id, snapshot_date, captured_at, stars, completeness)
        VALUES (?,?,?,?,1)
        """,
        (watched, "2026-08-20", "t", 42),
    )
    conn.execute(
        """
        INSERT INTO scores(
          run_id, repo_id, opportunity, explosion, contribution, confidence,
          components_json, evidence_json, flags_json, scored_at
        ) VALUES (?,?,50,NULL,40,'low','{}','{}','[]','t')
        """,
        (run_id, watched),
    )
    conn.commit()
    for version, filename in (
        (2, "002_users.sql"),
        (3, "003_score_version.sql"),
        (4, "004_missions.sql"),
        (5, "005_learning.sql"),
        (6, "006_observations.sql"),
        (7, "007_v03.sql"),
    ):
        _apply_sql(conn, version, filename)
    uid = ensure_local_user(conn)
    conn.execute("UPDATE reviews SET user_id=? WHERE user_id IS NULL", (uid,))
    conn.execute(
        """
        INSERT INTO contribution_jobs(
          user_id, repo_id, full_name, status, backend, task_json, log_json,
          created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (uid, watched, "acme/watched", "queued", "native", "{}", "[]", "t", "t"),
    )
    conn.commit()
    migrate(conn)
    assert SCHEMA_VERSION == 8
    assert _versions(conn) == [1, 2, 3, 4, 5, 6, 7, 8]
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "observations" in tables
    assert "users" in tables
    reviews = conn.execute(
        "SELECT r.full_name, v.action, v.note FROM reviews v JOIN repos r ON r.id=v.repo_id ORDER BY v.id"
    ).fetchall()
    assert reviews == [
        ("acme/watched", "watch", "keep-watch"),
        ("acme/other", "interested", "keep-interest"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 2
    uid_row = conn.execute("SELECT user_id FROM reviews WHERE repo_id=?", (watched,))
    assert uid_row.fetchone()[0] is not None
    watch = load_watchlist(conn, date(2026, 8, 24), ScoringSettings())
    names = {w.full_name: w.action for w in watch}
    assert names["acme/watched"] == "watch"
    assert names["acme/other"] == "interested"
    stars = conn.execute(
        "SELECT stars FROM snapshots WHERE repo_id=? AND snapshot_date='2026-08-20'",
        (watched,),
    ).fetchone()[0]
    assert stars == 42
    score = conn.execute(
        "SELECT score_version, opportunity FROM scores WHERE repo_id=?", (watched,)
    ).fetchone()
    assert score == ("v1", 50)
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    job = conn.execute(
        "SELECT full_name, status, repo_id FROM contribution_jobs"
    ).fetchone()
    assert job == ("acme/watched", "queued", watched)


def test_clean_install_empty_home_init_version_migrate(tmp_path, monkeypatch):
    home = tmp_path / "empty_home"
    home.mkdir()
    data = home / "foreshadow-data"
    _isolate(monkeypatch, data)
    monkeypatch.setenv("HOME", str(home))
    assert list(home.iterdir()) == []
    assert not data.exists()
    assert SCHEMA_VERSION == 8
    ver = CliRunner().invoke(app, ["version"])
    assert ver.exit_code == 0
    assert __version__ in ver.stdout
    inited = CliRunner().invoke(app, ["init"])
    if inited.exit_code != 0:
        conn = connect(data / "foreshadow.sqlite3")
        migrate(conn)
        conn.close()
    assert (data / "foreshadow.sqlite3").is_file()
    cfg = user_config_path()
    assert cfg == home / ".config" / "foreshadow" / "config.toml"
    node = repo_node(
        "R_keep",
        "acme/keep",
        topics=["mcp"],
        forkCount=3,
        description=_DESC,
    )
    gh = FakeGitHub(nodes={"R_keep": node}, search_nodes=[node])
    from foreshadow.clock import Clock

    clock = Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
    result = run_pipeline(
        clock=clock, force=False, llm=False, client=gh, settings=Settings()
    )
    assert result.skipped is False
    assert result.status in {"complete", "degraded"}
    assert cfg.is_file()
    db_path = data / "foreshadow.sqlite3"
    assert db_path.is_file()
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600
    conn = connect(db_path)
    migrate(conn)
    assert _versions(conn) == [1, 2, 3, 4, 5, 6, 7, 8]
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "observations" in tables
    assert "reviews" in tables
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
    assert (data / "reports" / "2026-08-24.md").is_file()


def test_migrate_on_empty_db_is_schema_8(tmp_home):
    db = tmp_home / "foreshadow.sqlite3"
    assert not db.exists()
    conn = connect(db)
    migrate(conn)
    assert SCHEMA_VERSION == 8
    assert _versions(conn) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert os.stat(db).st_mode & 0o777 == 0o600
    row = conn.execute("SELECT username FROM users WHERE is_local=1").fetchone()
    assert row[0] == "local"
    cols = [r[1] for r in conn.execute("PRAGMA table_info(observations)")]
    assert "expires_on" in cols
    assert "repo_id" in cols
