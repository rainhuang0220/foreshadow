"""foreshadow init / doctor / status. No live GitHub."""

from __future__ import annotations

from typer.testing import CliRunner

from foreshadow.cli import app
from foreshadow.db import SCHEMA_VERSION, connect
from foreshadow.paths import resolve_data_dir


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def test_init_creates_home_db_config(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "Foreshadow is ready" in result.stdout
    assert resolve_data_dir() == tmp_home
    assert (tmp_home / "foreshadow.sqlite3").is_file()
    assert (tmp_home / "logs").is_dir()
    assert (tmp_home / "reports").is_dir()
    conn = connect(tmp_home / "foreshadow.sqlite3")
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    assert int(row[0]) == SCHEMA_VERSION
    again = runner.invoke(app, ["init"])
    assert again.exit_code == 0


def test_init_without_foreshadow_home_uses_platformdirs(tmp_path, monkeypatch):
    data = tmp_path / "pd"
    monkeypatch.delenv("FORESHADOW_HOME", raising=False)
    monkeypatch.setattr("foreshadow.paths.user_data_dir", lambda _name: str(data))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (data / "foreshadow.sqlite3").is_file()


def test_doctor_and_status_after_init(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    doc = runner.invoke(app, ["doctor"])
    assert doc.exit_code == 0
    assert "home:" in doc.stdout.lower()
    assert "github token: ok" in doc.stdout
    st = runner.invoke(app, ["status"])
    assert st.exit_code == 0
    assert "last run: none" in st.stdout
    assert "observation:" in st.stdout
    assert str(tmp_home) in st.stdout


def test_init_does_not_overwrite_config(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    runner = CliRunner()
    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    cfg = tmp_home / ".config" / "foreshadow" / "config.toml"
    assert cfg.is_file()
    cfg.write_text("[discovery]\nstar_min = 99\n", encoding="utf-8")
    again = runner.invoke(app, ["init"])
    assert again.exit_code == 0
    assert "star_min = 99" in cfg.read_text(encoding="utf-8")


def test_doctor_missing_token_explains_github_token(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("foreshadow.doctor.shutil.which", lambda _cmd: None)
    monkeypatch.setattr("foreshadow.github.client.shutil.which", lambda _cmd: None)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    out = result.stdout + result.stderr
    assert "GITHUB_TOKEN" in out
    assert "gh auth" in out.lower()


def test_doctor_missing_git_tells_user(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)

    def which(cmd: str) -> str | None:
        if cmd == "git":
            return None
        return "/usr/bin/" + cmd

    monkeypatch.setattr("foreshadow.doctor.shutil.which", which)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "git" in result.stdout.lower()
    assert "xcode-select" in result.stdout or "git-scm.com" in result.stdout


def test_doctor_port_occupied_suggests_flag(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    monkeypatch.setattr("foreshadow.doctor._port_free", lambda _host, _port: False)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["doctor"])
    assert "--port" in result.stdout


def test_run_missing_token_explains_github_token(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.setattr("foreshadow.github.client.shutil.which", lambda _cmd: None)
    result = CliRunner().invoke(app, ["run"])
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    assert "GITHUB_TOKEN" in out
    assert "gh auth" in out.lower()


def test_same_day_skip_prints_status_and_exits_3(tmp_home, fake_github, monkeypatch):
    from foreshadow.cli import EXIT_SKIPPED

    _isolate(monkeypatch, tmp_home)
    runner = CliRunner()
    first = runner.invoke(app, ["run", "--date", "2026-08-24"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["run", "--date", "2026-08-24"])
    assert second.exit_code == EXIT_SKIPPED
    out = second.stdout + second.stderr
    assert "last run" in out.lower() or "already ran today" in out.lower()
    assert "--force" in out


def test_enter_missing_git_tells_user(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    monkeypatch.delenv("FORESHADOW_SKIP_CLONE", raising=False)

    def boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr("foreshadow.mission.subprocess.run", boom)
    result = CliRunner().invoke(app, ["enter", "acme/toy"])
    assert result.exit_code == 0, result.output
    out = result.stdout + result.stderr
    assert "git" in out.lower()
    assert "xcode-select" in out or "git-scm.com" in out


def test_board_port_occupied_suggests_other_port(tmp_home, monkeypatch):
    import errno

    from foreshadow.db import migrate

    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    conn.close()

    def boom(*_a, **_k):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr("foreshadow.board.server.make_server", boom)
    result = CliRunner().invoke(app, ["board", "--port", "8765", "--no-open"])
    assert result.exit_code in {1, 2}
    out = result.stdout + result.stderr
    assert "8765" in out
    assert "--port" in out


def test_board_without_data_points_at_init_run(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    result = CliRunner().invoke(app, ["board", "--no-open"])
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    assert "foreshadow init" in out
    assert "foreshadow run" in out


def test_board_clock_stays_on_report_date_after_utc_midnight(tmp_home, monkeypatch):
    """Opening the board after UTC midnight must not rescore yesterday with today."""
    from datetime import UTC, datetime

    from foreshadow.cli import _board_clock
    from foreshadow.clock import Clock
    from foreshadow.db import migrate

    _isolate(monkeypatch, tmp_home)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute(
        """
        INSERT INTO daily_runs(run_date, started_at, status, budget_cap, report_path)
        VALUES ('2026-08-31', 't', 'complete', 800, ?)
        """,
        (str(tmp_home / "reports" / "2026-08-31.md"),),
    )
    conn.commit()
    conn.close()
    reports = tmp_home / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-08-31.md").write_text("ok\n", encoding="utf-8")
    later = datetime(2026, 9, 1, 0, 5, tzinfo=UTC)
    monkeypatch.setattr(
        "foreshadow.cli.Clock",
        lambda now=None: Clock(now=now or later),
    )
    clock, day = _board_clock(None)
    assert day == "2026-08-31"
    assert clock.today().isoformat() == "2026-08-31"
