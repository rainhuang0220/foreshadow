from typer.testing import CliRunner

from foreshadow.cli import app


def test_cli_outcome_records_without_github(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    runner = CliRunner()
    entered = runner.invoke(app, ["enter", "acme/toy"])
    assert entered.exit_code == 0
    assert "FORESHADOW.md" in entered.stdout
    assert "ISSUE_DRAFT.md" in entered.stdout
    assert "第一步" in entered.stdout
    assert "remote GitHub writes are blocked until you approve them." in entered.stdout
    result = runner.invoke(app, ["outcome", "acme/toy", "--event", "abandoned"])
    assert result.exit_code == 0
    assert "does not post" in result.stdout
    listed = runner.invoke(app, ["missions"])
    assert listed.exit_code == 0
    assert "acme/toy" in listed.stdout


def test_cli_outcome_rejects_system_event(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    runner = CliRunner()
    entered = runner.invoke(app, ["enter", "acme/toy"])
    assert entered.exit_code == 0
    bad = runner.invoke(app, ["outcome", "acme/toy", "--event", "clone_ok"])
    assert bad.exit_code == 2
    assert "unknown event" in bad.output
    ok = runner.invoke(app, ["outcome", "acme/toy", "--event", "paused"])
    assert ok.exit_code == 0
    logs = list(tmp_home.glob("work/u*/acme__toy/TASK_LOG.md"))
    assert logs
    log = logs[0].read_text(encoding="utf-8")
    assert "TASK: paused" in log
    assert "TASK: clone_ok" not in log


def test_cli_enter_rejects_invalid_repo(tmp_home):
    runner = CliRunner()
    for name in ("not-a-repo", "../etc/passwd", "a/b;rm"):
        result = runner.invoke(app, ["enter", name])
        assert result.exit_code == 2
        assert "owner/repo" in result.output
    work = tmp_home / "work"
    assert not work.exists() or not any(work.iterdir())


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in (
        "run",
        "report",
        "show",
        "review",
        "watchlist",
        "board",
        "enter",
        "outcome",
        "missions",
        "sample-access",
    ):
        assert name in result.stdout
