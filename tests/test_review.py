from datetime import date

import pytest
from typer.testing import CliRunner

from fakes import seed_repo
from foreshadow.cli import app
from foreshadow.db import connect, migrate
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.snapshot import upsert_snapshot
from foreshadow.reviews import (
    ReviewError,
    apply_review,
    stance_blocks_top5,
)


def test_enter_writes_entry_and_scores(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "enter", "docs", frozen_clock)
    row = conn.execute(
        "SELECT stars_at_entry, scores_at_entry_json FROM entries"
    ).fetchone()
    assert row[0] is not None
    assert row[1] != "{}"
    assert fake_github.hydrate_b_calls >= 1


def test_rerun_does_not_duplicate_reviews(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    run_pipeline(clock=frozen_clock, force=True, llm=False)
    n = conn.execute("SELECT count(*) FROM reviews").fetchone()[0]
    assert n == 1


def test_show_does_not_hydrate_unknown(tmp_home, fake_github):
    result = CliRunner().invoke(app, ["show", "nope/unknown"])
    assert result.exit_code == 2
    assert fake_github.hydrate_calls == 0


def test_reviews_are_append_only_latest_is_stance(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    apply_review(conn, fake_github, "acme/memkit", "enter", "docs", frozen_clock)
    n = conn.execute("SELECT count(*) FROM reviews").fetchone()[0]
    assert n == 2
    action = conn.execute(
        "SELECT action FROM reviews ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert action == "enter"


def test_unknown_action_lists_actions(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    with pytest.raises(ReviewError, match="watch"):
        apply_review(conn, fake_github, "acme/memkit", "star", None, frozen_clock)
    assert fake_github.hydrate_calls == 0


def test_review_resolves_alias(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_renamed", "acme/newkit")
    conn.execute(
        "INSERT INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?,?,?)",
        (rid, "acme/memkit", frozen_clock.now().isoformat()),
    )
    upsert_snapshot(
        conn,
        rid,
        "2026-08-24",
        {
            "stars": 10,
            "forks": 1,
            "open_issues": 1,
            "open_prs": 0,
            "last_pushed_at": "2026-08-20T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
            "captured_at": frozen_clock.now().isoformat(),
            "topics_json": "[]",
            "features_json": "{}",
            "completeness": 1.0,
        },
    )
    conn.commit()
    calls = fake_github.hydrate_calls
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    assert fake_github.hydrate_calls == calls
    assert conn.execute("SELECT repo_id FROM reviews").fetchone()[0] == rid


def test_review_resolves_unseen_node_id(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "R_memkit", "watch", None, frozen_clock)
    assert conn.execute("SELECT full_name FROM repos").fetchone()[0] == "acme/memkit"
    assert fake_github.hydrate_b_calls >= 1


def test_reject_later_enter_filter_top5_not_nudge():
    today = date(2026, 8, 24)
    assert stance_blocks_top5("reject", "2026-07-01T00:00:00+00:00", today)
    assert not stance_blocks_top5("reject", "2026-05-01T00:00:00+00:00", today)
    assert stance_blocks_top5("later", "2026-08-20T00:00:00+00:00", today)
    assert not stance_blocks_top5("later", "2026-08-01T00:00:00+00:00", today)
    assert stance_blocks_top5("enter", "2026-08-24T00:00:00+00:00", today)
    assert not stance_blocks_top5("watch", "2026-08-24T00:00:00+00:00", today)
    assert not stance_blocks_top5("interested", "2026-08-24T00:00:00+00:00", today)


def test_cli_review_enter_and_unknown_action(tmp_home, fake_github):
    runner = CliRunner()
    ok = runner.invoke(app, ["review", "acme/memkit", "enter", "-m", "docs"])
    assert ok.exit_code == 0
    conn = connect(tmp_home / "foreshadow.sqlite3")
    row = conn.execute(
        "SELECT stars_at_entry, scores_at_entry_json, note FROM entries"
    ).fetchone()
    assert row[0] is not None
    assert row[1] != "{}"
    assert row[2] == "docs"
    bad = runner.invoke(app, ["review", "acme/memkit", "star"])
    assert bad.exit_code == 2
    assert "watch" in (bad.stdout + bad.stderr)
