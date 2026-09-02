"""Product CLI: init, doctor, status, version, schedule files. No live GitHub."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from foreshadow.cli import app
from foreshadow.paths import resolve_data_dir
from foreshadow.schedule import install, scheduler_status, uninstall


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def test_version_and_init_doctor_status(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    runner = CliRunner()
    ver = runner.invoke(app, ["version"])
    assert ver.exit_code == 0
    assert "0.2.4" in ver.stdout
    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    assert "Foreshadow is ready" in first.stdout
    assert (tmp_home / "foreshadow.sqlite3").is_file()
    again = runner.invoke(app, ["init"])
    assert again.exit_code == 0
    doc = runner.invoke(app, ["doctor"])
    assert "HOME" in doc.stdout or "home" in doc.stdout.lower()
    assert "token" in doc.stdout.lower()
    st = runner.invoke(app, ["status"])
    assert st.exit_code == 0
    assert "last run: none" in st.stdout
    assert resolve_data_dir() == tmp_home


def test_doctor_missing_token_exits_1(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("foreshadow.github.client.shutil.which", lambda _cmd: None)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "token" in result.stdout.lower()


def test_schedule_install_writes_plist_without_launchctl(tmp_home, monkeypatch):
    _isolate(monkeypatch, tmp_home)
    monkeypatch.setattr("foreshadow.schedule.is_unstable_path", lambda _p: False)
    fake_py = tmp_home / "bin" / "python3"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_py.chmod(0o755)
    spec, notes = install(
        at="08:00",
        python=fake_py,
        home=tmp_home,
        apply=False,
        verify=False,
        backend="launchd",
    )
    assert Path(spec.home) == tmp_home.resolve() or Path(spec.home) == tmp_home
    plist = Path.home() / "Library" / "LaunchAgents" / "ai.foreshadow.daily.plist"
    assert plist.is_file()
    body = plist.read_text(encoding="utf-8")
    assert "ai.foreshadow.daily" in body
    assert str(fake_py.resolve()) in body
    assert ".worktrees" not in body
    status = scheduler_status()
    assert status["installed"] is True
    notes2 = uninstall(apply=False, backend="launchd")
    assert notes or notes2
    assert not plist.is_file()
