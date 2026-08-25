from typer.testing import CliRunner

from foreshadow.cli import app


def test_cli_outcome_records_without_github(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    runner = CliRunner()
    entered = runner.invoke(app, ["enter", "acme/toy"])
    assert entered.exit_code == 0
    result = runner.invoke(app, ["outcome", "acme/toy", "--event", "abandoned"])
    assert result.exit_code == 0
    assert "does not post" in result.stdout


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
    ):
        assert name in result.stdout
