from typer.testing import CliRunner

from foreshadow.cli import app


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("run", "report", "show", "review", "watchlist", "board", "enter"):
        assert name in result.stdout
