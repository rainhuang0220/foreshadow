from datetime import date

import pytest
from typer.testing import CliRunner

from fakes import seed_repo
from foreshadow.cli import app
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.snapshot import upsert_snapshot
from foreshadow.reviews import (
    ReviewError,
    ReviewFetchError,
    apply_review,
    stance_blocks_top5,
)


def _seed_snapshot(
    conn, repo_id: int, captured_at: str, day: str = "2026-08-24"
) -> None:
    upsert_snapshot(
        conn,
        repo_id,
        day,
        {
            "stars": 10,
            "forks": 1,
            "open_issues": 1,
            "open_prs": 0,
            "last_pushed_at": "2026-08-20T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
            "captured_at": captured_at,
            "topics_json": "[]",
            "features_json": "{}",
            "completeness": 1.0,
        },
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
    _seed_snapshot(conn, rid, frozen_clock.now().isoformat())
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


@pytest.mark.parametrize("action", ["watch", "interested", "reject", "later"])
def test_cli_watch_known_repo_without_token(tmp_home, monkeypatch, action):
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)

    def boom() -> str:
        raise SystemExit(2)

    monkeypatch.setattr("foreshadow.github.client.resolve_token", boom)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_memkit", "acme/memkit")
    _seed_snapshot(conn, rid, "2026-08-24T00:05:00+00:00")
    conn.commit()
    result = CliRunner().invoke(app, ["review", "acme/memkit", action])
    assert result.exit_code == 0
    conn = connect(tmp_home / "foreshadow.sqlite3")
    assert conn.execute("SELECT action FROM reviews").fetchone()[0] == action


def test_enter_uses_settings_scoring(tmp_home, frozen_clock, fake_github, monkeypatch):
    seen: dict = {}
    real = score_repo

    def wrapped(repo, *, clock=None, scoring=None, bags=None):
        seen["scoring"] = scoring
        return real(repo, clock=clock, scoring=scoring, bags=bags)

    monkeypatch.setattr("foreshadow.reviews.score_repo", wrapped)
    settings = Settings()
    settings.scoring.window_slack_days = 7
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(
        conn, fake_github, "acme/memkit", "enter", None, frozen_clock, settings=settings
    )
    assert seen["scoring"] is settings.scoring
    assert seen["scoring"].window_slack_days == 7


def test_cli_enter_uses_load_config_scoring(tmp_home, fake_github, monkeypatch):
    cfg = tmp_home / ".config" / "foreshadow" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("[scoring]\nwindow_slack_days = 3\n", encoding="utf-8")
    seen: dict = {}
    real = score_repo

    def wrapped(repo, *, clock=None, scoring=None, bags=None):
        seen["scoring"] = scoring
        return real(repo, clock=clock, scoring=scoring, bags=bags)

    monkeypatch.setattr("foreshadow.reviews.score_repo", wrapped)
    result = CliRunner().invoke(app, ["review", "acme/memkit", "enter"])
    assert result.exit_code == 0
    assert seen["scoring"].window_slack_days == 3


def test_hydrate_5xx_is_not_unknown_repo(tmp_home, frozen_clock, fake_github):
    fake_github.fail_ids.add("R_memkit")
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    with pytest.raises(ReviewFetchError, match="server error"):
        apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    assert conn.execute("SELECT count(*) FROM reviews").fetchone()[0] == 0


def test_cli_hydrate_5xx_exit_1_not_unknown(tmp_home, fake_github):
    fake_github.fail_ids.add("R_memkit")
    result = CliRunner().invoke(app, ["review", "acme/memkit", "watch"])
    assert result.exit_code == 1
    out = result.stdout + result.stderr
    assert "unknown repo" not in out.lower()


def test_cli_hydrate_budget_exit_1(tmp_home, fake_github):
    fake_github.graphql_used = 800
    result = CliRunner().invoke(app, ["review", "acme/memkit", "watch"])
    assert result.exit_code == 1
    out = result.stdout + result.stderr
    assert "unknown repo" not in out.lower()


def test_cli_unknown_repo_exit_2(tmp_home, fake_github):
    result = CliRunner().invoke(app, ["review", "nope/unknown", "watch"])
    assert result.exit_code == 2
    assert "unknown repo" in (result.stdout + result.stderr)
