from typer.testing import CliRunner

from foreshadow.cli import app
from foreshadow.db import connect, migrate
from foreshadow.reviews import apply_review, current_stances


def test_watchlist_lists_all_without_flag(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    apply_review(conn, fake_github, "acme/other", "enter", None, frozen_clock)
    rows = current_stances(conn, action=None)
    assert {r["action"] for r in rows} >= {"watch", "enter"}


def test_watchlist_filters_action(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    apply_review(conn, fake_github, "acme/other", "enter", None, frozen_clock)
    rows = current_stances(conn, action="enter")
    assert {r["action"] for r in rows} == {"enter"}
    assert {r["full_name"] for r in rows} == {"acme/other"}


def test_cli_watchlist_grouped_and_filter(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    apply_review(conn, fake_github, "acme/other", "enter", None, frozen_clock)
    runner = CliRunner()
    all_rows = runner.invoke(app, ["watchlist"])
    assert all_rows.exit_code == 0
    out = all_rows.stdout
    assert "watch" in out
    assert "enter" in out
    assert "acme/memkit" in out
    assert "acme/other" in out
    filtered = runner.invoke(app, ["watchlist", "--action", "enter"])
    assert filtered.exit_code == 0
    assert "acme/other" in filtered.stdout
    assert "acme/memkit" not in filtered.stdout
