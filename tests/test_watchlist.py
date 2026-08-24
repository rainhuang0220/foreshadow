from typer.testing import CliRunner

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.cli import app
from foreshadow.db import connect, migrate
from foreshadow.pipeline import run_pipeline
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


def test_watchlist_appendix_excludes_h_rejected(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    keep = repo_node("R_keep", "acme/keeper")
    dead = repo_node("R_dead", "acme/dead", isArchived=True)
    rid_keep = seed_repo(conn, "R_keep", "acme/keeper")
    rid_dead = seed_repo(conn, "R_dead", "acme/dead")
    seed_review(conn, rid_keep, "watch", "2026-08-23T00:00:00+00:00")
    seed_review(conn, rid_dead, "watch", "2026-08-23T00:01:00+00:00")
    conn.commit()
    gh = FakeGitHub(
        nodes={"R_keep": keep, "R_dead": dead},
        search_nodes=[keep, dead],
    )
    result = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert result.report is not None
    watch_names = [item.get("full_name") for item in result.report.watchlist_appendix]
    assert "acme/dead" not in watch_names
    assert "acme/keeper" in watch_names
    below = result.report.below_bar
    assert any(
        item.get("full_name") == "acme/dead"
        and (item.get("kind") == "veto" or item.get("veto_reason"))
        for item in below
    )
