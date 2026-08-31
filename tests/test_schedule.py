"""launchd / systemd / cron install must never name a Desktop worktree."""

from __future__ import annotations

from pathlib import Path

import pytest

from foreshadow.schedule import (
    CRON_BEGIN,
    CRON_END,
    ScheduleError,
    install,
    render_cron_line,
    render_plist,
    uninstall,
    wrapper_path,
)


def _fake_python(home: Path) -> Path:
    py = home / "opt" / "python3"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    py.chmod(0o755)
    return py


def test_launchd_plist_uses_python_dash_m_and_stable_home(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setattr("foreshadow.schedule.is_unstable_path", lambda _p: False)
    py = _fake_python(tmp_home)
    spec, _notes = install(
        at="07:00",
        python=py,
        home=tmp_home,
        apply=False,
        verify=False,
        backend="launchd",
    )
    plist = Path.home() / "Library" / "LaunchAgents" / "ai.foreshadow.daily.plist"
    body = plist.read_text(encoding="utf-8")
    assert "ai.foreshadow.daily" in body
    assert str(py.resolve()) in body
    assert "-m" in body
    assert "foreshadow" in body
    assert "run" in body
    assert ".worktrees" not in body
    assert "Desktop/Foreshadow" not in body
    assert "dogfood-run" not in body
    assert str(tmp_home) in body
    assert str(spec.home / "logs") in body
    wrap = wrapper_path(tmp_home)
    assert wrap.is_file()
    assert "python" in wrap.read_text(encoding="utf-8")
    assert "-m foreshadow run" in wrap.read_text(encoding="utf-8")
    again, _ = install(
        at="07:00",
        python=py,
        home=tmp_home,
        apply=False,
        verify=False,
        backend="launchd",
    )
    assert again.hour == 7
    uninstall(apply=False, backend="launchd")
    assert not plist.is_file()
    assert not wrap.is_file()


def test_refuses_worktree_home(tmp_path, monkeypatch):
    dirty = tmp_path / "Desktop" / "Foreshadow" / ".worktrees" / "x"
    dirty.mkdir(parents=True)
    monkeypatch.setenv("FORESHADOW_HOME", str(dirty))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    py = _fake_python(tmp_path)
    with pytest.raises(ScheduleError, match="unstable HOME"):
        install(
            python=py,
            home=dirty,
            apply=False,
            verify=False,
            backend="launchd",
        )


def test_cron_markers_idempotent(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setattr("foreshadow.schedule.is_unstable_path", lambda _p: False)
    py = _fake_python(tmp_home)
    spec, _ = install(
        python=py,
        home=tmp_home,
        apply=False,
        verify=False,
        backend="cron",
    )
    line = render_cron_line(spec)
    assert CRON_BEGIN.split()[1] == "BEGIN"
    assert "-m" in line or "foreshadow" in line
    assert ".worktrees" not in line
    from foreshadow.schedule import _crontab_replace

    first = _crontab_replace("", line)
    second = _crontab_replace(first, line)
    assert first.count(CRON_BEGIN) == 1
    assert second.count(CRON_BEGIN) == 1
    assert second.count(CRON_END) == 1
    cleared = _crontab_replace(second, None)
    assert CRON_BEGIN not in cleared


def test_plist_render_rejects_worktree_python(tmp_home, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_home))
    from foreshadow.schedule import ScheduleSpec

    spec = ScheduleSpec(
        backend="launchd",
        python=Path("/usr/bin/python3"),
        home=tmp_home,
        hour=8,
        minute=0,
        user_home=tmp_home,
    )
    body = render_plist(spec)
    assert "/usr/bin/python3" in body
    assert "-m" in body
    assert "WorkingDirectory" in body
    assert str(tmp_home / "logs") in body
