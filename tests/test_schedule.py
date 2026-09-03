"""launchd / systemd / cron install must never name a Desktop worktree."""

from __future__ import annotations

from pathlib import Path

import pytest

from foreshadow.schedule import (
    CRON_BEGIN,
    CRON_END,
    TRAIN_LABEL,
    ScheduleError,
    install,
    render_cron_block,
    render_cron_line,
    render_cron_train_line,
    render_plist,
    render_systemd_service,
    render_systemd_timer,
    render_systemd_train_service,
    render_systemd_train_timer,
    render_train_plist,
    stray_agent_plists,
    train_wrapper_path,
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
    assert "<key>Weekday</key>" not in body
    assert TRAIN_LABEL not in body
    assert "<string>train</string>" not in body
    assert ".worktrees" not in body
    assert "Desktop/Foreshadow" not in body
    assert "dogfood-run" not in body
    assert str(tmp_home) in body
    assert str(spec.home / "logs") in body
    wrap = wrapper_path(tmp_home)
    assert wrap.is_file()
    assert "python" in wrap.read_text(encoding="utf-8")
    assert "-m foreshadow run" in wrap.read_text(encoding="utf-8")
    train_plist = Path.home() / "Library" / "LaunchAgents" / f"{TRAIN_LABEL}.plist"
    train_body = train_plist.read_text(encoding="utf-8")
    assert TRAIN_LABEL in train_body
    assert str(py.resolve()) in train_body
    assert "-m" in train_body
    assert "train" in train_body
    assert "<key>Weekday</key>" in train_body
    assert "foreshadow run" not in train_body
    assert "github" not in train_body.lower()
    assert ".worktrees" not in train_body
    assert "Desktop/Foreshadow" not in train_body
    assert str(tmp_home) in train_body
    assert str(spec.home / "logs") in train_body
    twrap = train_wrapper_path(tmp_home)
    assert twrap.is_file()
    twrap_text = twrap.read_text(encoding="utf-8")
    assert "-m foreshadow train" in twrap_text
    assert "unset GITHUB_TOKEN" in twrap_text
    assert "foreshadow run" not in twrap_text
    assert not any(p.name == f"{TRAIN_LABEL}.plist" for p in stray_agent_plists())
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
    assert not train_plist.is_file()
    assert not wrap.is_file()
    assert not twrap.is_file()


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
    train_line = render_cron_train_line(spec)
    block = render_cron_block(spec)
    assert CRON_BEGIN.split()[1] == "BEGIN"
    assert "-m" in line or "foreshadow" in line
    assert "run" in line
    assert ".worktrees" not in line
    assert "train" in train_line
    assert train_line.split()[4] == "0"
    assert "env -u GITHUB_TOKEN -u GH_TOKEN" in train_line
    assert "'train'" in train_line or "foreshadow train" in train_line
    assert line in block
    assert train_line in block
    assert ".worktrees" not in block
    from foreshadow.schedule import _crontab_replace

    first = _crontab_replace("", block)
    second = _crontab_replace(first, block)
    assert first.count(CRON_BEGIN) == 1
    assert second.count(CRON_BEGIN) == 1
    assert second.count(CRON_END) == 1
    assert "foreshadow train" in first or "'train'" in first
    cleared = _crontab_replace(second, None)
    assert CRON_BEGIN not in cleared
    assert "foreshadow train" not in cleared


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
    assert "foreshadow" in body
    assert "run" in body
    train = render_train_plist(spec)
    assert TRAIN_LABEL in train
    assert "train" in train
    assert "<key>Weekday</key>" in train
    assert "/usr/bin/python3" in train
    assert str(tmp_home) in train
    assert "github.com" not in train.lower()


def test_systemd_train_is_weekly_oneshot_not_daily(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_HOME", str(tmp_home))
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setattr("foreshadow.schedule.is_unstable_path", lambda _p: False)
    py = _fake_python(tmp_home)
    spec, notes = install(
        at="08:00",
        python=py,
        home=tmp_home,
        apply=False,
        verify=False,
        backend="systemd",
    )
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    daily_service = (unit_dir / "foreshadow-daily.service").read_text(encoding="utf-8")
    daily_timer = (unit_dir / "foreshadow-daily.timer").read_text(encoding="utf-8")
    train_service = (unit_dir / "foreshadow-train.service").read_text(encoding="utf-8")
    train_timer = (unit_dir / "foreshadow-train.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in daily_service
    assert "foreshadow" in daily_service and "'run'" in daily_service
    assert "foreshadow-train" not in daily_service
    assert "'train'" not in daily_service
    assert "foreshadow-train" not in daily_timer
    assert "Unit=foreshadow-daily.service" in daily_timer
    assert "*-*-*" in daily_timer
    assert "Type=oneshot" in train_service
    assert "MemoryMax=400M" in train_service
    assert "Nice=10" in train_service
    assert "UnsetEnvironment=GITHUB_TOKEN GH_TOKEN" in train_service
    assert "After=foreshadow-daily.service" in train_service
    assert str(py.resolve()) in train_service
    assert "-m" in train_service
    assert "'train'" in train_service
    assert "'run'" not in train_service
    assert str(spec.home) in train_service
    assert f"WorkingDirectory={spec.home}" in train_service
    assert ".worktrees" not in train_service
    assert "Desktop/Foreshadow" not in train_service
    assert "OnCalendar=Sun" in train_timer
    assert "Unit=foreshadow-train.service" in train_timer
    assert "Unit=foreshadow-daily.service" not in train_timer
    assert any("foreshadow-train.service" in n for n in notes)
    rendered_daily = render_systemd_service(spec)
    rendered_timer = render_systemd_timer(spec)
    assert rendered_daily == daily_service
    assert rendered_timer == daily_timer
    assert "'train'" not in render_systemd_service(spec)
    assert "MemoryMax" not in render_systemd_service(spec)
    assert "MemoryMax=400M" in render_systemd_train_service(spec)
    assert "OnCalendar=Sun" in render_systemd_train_timer(spec)
    uninstall(apply=False, backend="systemd")
    assert not (unit_dir / "foreshadow-daily.service").is_file()
    assert not (unit_dir / "foreshadow-train.service").is_file()
    assert not (unit_dir / "foreshadow-train.timer").is_file()


def test_train_units_refuse_worktree_python_in_body(tmp_home):
    from foreshadow.schedule import ScheduleSpec

    spec = ScheduleSpec(
        backend="systemd",
        python=Path("/usr/bin/python3"),
        home=tmp_home,
        hour=8,
        minute=0,
        user_home=tmp_home,
    )
    service = render_systemd_train_service(spec)
    timer = render_systemd_train_timer(spec)
    plist = render_train_plist(spec)
    cron = render_cron_train_line(spec)
    for body in (service, timer, plist, cron):
        assert ".worktrees" not in body
        assert "Desktop/Foreshadow" not in body
        assert "github.com" not in body.lower()
        assert "api.github" not in body.lower()
