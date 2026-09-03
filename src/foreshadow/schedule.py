"""Daily scheduler: launchd (macOS), systemd --user or cron (Linux).

Never points ProgramArguments, WorkingDirectory, or logs at a Desktop
worktree. HOME is platformdirs (or a stable FORESHADOW_HOME override).
The daily job is ``<absolute python> -m foreshadow run``.

``install`` / ``install_schedule`` also write a weekly oneshot train hook
(``python -m foreshadow train``). That is not a second always-on service
and is only created when the scheduler is installed:

- systemd --user: ``foreshadow-train.service`` (Type=oneshot, MemoryMax=400M,
  Nice=10) + ``foreshadow-train.timer`` (weekly). Do **not** add OnCalendar
  to the daily unit — that unit must keep starting ``foreshadow run``.
- launchd: ``ai.foreshadow.train`` (StartCalendarInterval Weekday).
- cron: a second line in the same ``FORESHADOW DAILY`` crontab block.

Train is local-only: it must not call GitHub. Daily units stay ``run``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from foreshadow.paths import (
    default_data_dir,
    is_unstable_path,
    resolve_data_dir,
    resolve_log_dir,
)

LAUNCHD_LABEL = "ai.foreshadow.daily"
TRAIN_LABEL = "ai.foreshadow.train"
DOGFOOD_LABEL = "ai.foreshadow.dogfood"
SYSTEMD_UNIT = "foreshadow-daily"
SYSTEMD_TRAIN_UNIT = "foreshadow-train"
CRON_BEGIN = "# BEGIN FORESHADOW DAILY"
CRON_END = "# END FORESHADOW DAILY"
META_NAME = "schedule.json"
DEFAULT_AT = "08:00"
WRAPPER_NAME = "foreshadow-daily"
TRAIN_WRAPPER_NAME = "foreshadow-train"


class ScheduleError(RuntimeError):
    """Install / uninstall / run-now failed. Safe to print."""


@dataclass
class ScheduleSpec:
    backend: str
    python: Path
    home: Path
    hour: int
    minute: int
    user_home: Path
    label: str = LAUNCHD_LABEL
    wrapper: Path | None = None

    @property
    def log_out(self) -> Path:
        return self.home / "logs" / f"{self.backend}.out.log"

    @property
    def log_err(self) -> Path:
        return self.home / "logs" / f"{self.backend}.err.log"

    @property
    def train_log_out(self) -> Path:
        return self.home / "logs" / f"{self.backend}-train.out.log"

    @property
    def train_log_err(self) -> Path:
        return self.home / "logs" / f"{self.backend}-train.err.log"

    @property
    def program_args(self) -> list[str]:
        return self.job_args("run")

    @property
    def train_program_args(self) -> list[str]:
        return self.job_args("train")

    def job_args(self, command: str) -> list[str]:
        if is_unstable_path(self.python):
            if command == "run":
                wrap = self.wrapper or wrapper_path(self.home)
            else:
                wrap = train_wrapper_path(self.home)
            return ["/bin/bash", str(wrap)]
        return [str(self.python), "-m", "foreshadow", command]

    def to_json(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "python": str(self.python),
            "home": str(self.home),
            "hour": self.hour,
            "minute": self.minute,
            "user_home": str(self.user_home),
            "label": self.label,
            "wrapper": str(self.wrapper) if self.wrapper else None,
        }


def parse_hhmm(value: str) -> tuple[int, int]:
    text = (value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ScheduleError(f"invalid --at {value!r} (want HH:MM)")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ScheduleError(f"invalid --at {value!r} (want HH:MM)") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ScheduleError(f"invalid --at {value!r} (want HH:MM)")
    return hour, minute


def detect_backend(platform: str | None = None) -> str:
    forced = os.environ.get("FORESHADOW_SCHEDULE_BACKEND")
    if forced:
        return forced.strip().lower()
    plat = platform or sys.platform
    if plat == "darwin":
        return "launchd"
    if plat.startswith("linux"):
        if _systemd_user_available():
            return "systemd"
        return "cron"
    if plat.startswith("win"):
        return "windows"
    return "cron"


def scheduled_home() -> Path:
    current = resolve_data_dir()
    if is_unstable_path(current):
        stable = default_data_dir()
        if is_unstable_path(stable):
            raise ScheduleError(
                "refusing to schedule into a Desktop/worktree HOME; "
                "install to a stable prefix or unset FORESHADOW_HOME"
            )
        return stable
    return current


def stable_python() -> Path:
    candidates: list[Path] = [Path(sys.executable)]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    seen: set[Path] = set()
    unstable_seen = False
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_unstable_path(resolved):
            unstable_seen = True
            continue
        if not resolved.is_file():
            continue
        if _imports_foreshadow(resolved):
            return resolved
    hint = (
        "no stable Python with foreshadow installed "
        "(refusing repo / Desktop worktree interpreters). "
        "Install with `uv tool install .` or `pipx install .`, then retry."
    )
    if unstable_seen:
        raise ScheduleError(hint)
    raise ScheduleError(hint)


def wrapper_path(home: Path | None = None) -> Path:
    return (
        (Path(home) if home is not None else resolve_data_dir()) / "bin" / WRAPPER_NAME
    )


def train_wrapper_path(home: Path | None = None) -> Path:
    return (
        (Path(home) if home is not None else resolve_data_dir())
        / "bin"
        / TRAIN_WRAPPER_NAME
    )


def macos_plist_path() -> Path:
    return _plist_path()


def _fallback_python() -> Path:
    for cand in (
        Path("/usr/bin/python3"),
        Path("/usr/local/bin/python3"),
        Path("/opt/homebrew/bin/python3"),
    ):
        if cand.is_file() and not is_unstable_path(cand):
            return cand
    found = shutil.which("python3")
    if found and not is_unstable_path(found):
        return Path(found)
    raise ScheduleError(
        "no stable Python for the scheduler (refusing Desktop/worktree). "
        "Install with `uv tool install .` then retry."
    )


def _resolve_scheduled_python(python: Path | None) -> tuple[Path, bool]:
    if python is not None:
        py = Path(python)
        try:
            py = py.resolve()
        except OSError:
            py = py.absolute()
        if is_unstable_path(py):
            return _fallback_python(), True
        return py, False
    try:
        return stable_python(), False
    except ScheduleError:
        return _fallback_python(), True


def _write_wrapper(spec: ScheduleSpec, *, command: str = "run") -> Path:
    if command == "train":
        path = train_wrapper_path(spec.home)
        comment = (
            "# Weekly train (local only). Never cd to a Desktop worktree. "
            "Does not call GitHub."
        )
        unset_github = "unset GITHUB_TOKEN GH_TOKEN || true\n"
    else:
        path = spec.wrapper or wrapper_path(spec.home)
        comment = "# Foreshadow daily job. Never cd to a Desktop worktree."
        unset_github = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    py_exec = str(spec.python) if not is_unstable_path(spec.python) else "python3"
    path_value = ":".join(
        [
            str(spec.user_home / ".local" / "bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
    )
    py_line = "python3" if py_exec == "python3" else _sh_quote(py_exec)
    body = f"""#!/bin/bash
{comment}
set -euo pipefail
{unset_github}export HOME={_sh_quote(str(spec.user_home))}
export FORESHADOW_HOME={_sh_quote(str(spec.home))}
export PATH={_sh_quote(path_value)}
cd "$FORESHADOW_HOME" || cd /tmp
if command -v foreshadow >/dev/null 2>&1; then
  exec foreshadow {command} "$@"
fi
exec {py_line} -m foreshadow {command} "$@"
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    if command == "run":
        spec.wrapper = path
    return path


def next_local_run(hour: int, minute: int, *, now: datetime | None = None) -> datetime:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    nxt = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= current:
        nxt += timedelta(days=1)
    return nxt


def install(
    *,
    at: str = DEFAULT_AT,
    python: Path | None = None,
    home: Path | None = None,
    apply: bool = True,
    verify: bool = True,
    backend: str | None = None,
) -> tuple[ScheduleSpec, list[str]]:
    kind = backend or detect_backend()
    if kind == "windows":
        raise ScheduleError(
            "Windows Task Scheduler is not supported yet. "
            "Run `python -m foreshadow run` from Task Scheduler yourself."
        )
    hour, minute = parse_hhmm(at)
    py, unsafe = _resolve_scheduled_python(python)
    if verify and not unsafe and not _imports_foreshadow(py):
        raise ScheduleError(f"python cannot import foreshadow: {py}")
    data_home = Path(home) if home is not None else scheduled_home()
    try:
        data_home = data_home.resolve()
    except OSError:
        data_home = data_home.absolute()
    if is_unstable_path(data_home):
        raise ScheduleError(
            f"refusing unstable HOME {data_home} (Desktop/worktree). "
            "Unset FORESHADOW_HOME to use the platformdirs data dir."
        )
    user_home = Path.home()
    spec = ScheduleSpec(
        backend=kind,
        python=py,
        home=data_home,
        hour=hour,
        minute=minute,
        user_home=user_home,
        wrapper=wrapper_path(data_home),
    )
    data_home.mkdir(parents=True, exist_ok=True)
    resolve_log_dir(data_home)
    (data_home / "reports").mkdir(exist_ok=True)
    _write_wrapper(spec)
    _write_wrapper(spec, command="train")
    _assert_spec_stable(spec)
    notes: list[str] = [f"wrote {spec.wrapper}"]
    if kind == "launchd":
        notes.extend(_install_launchd(spec, apply=apply))
    elif kind == "systemd":
        notes.extend(_install_systemd(spec, apply=apply))
    elif kind == "cron":
        notes.extend(_install_cron(spec, apply=apply))
    else:
        raise ScheduleError(f"unknown scheduler backend: {kind}")
    _write_meta(spec)
    return spec, notes


def uninstall(*, apply: bool = True, backend: str | None = None) -> list[str]:
    kind = backend or detect_backend()
    spec = load_spec()
    notes: list[str] = []
    if kind == "launchd" or (spec and spec.backend == "launchd"):
        notes.extend(_uninstall_launchd(spec, apply=apply))
    if kind == "systemd" or (spec and spec.backend == "systemd"):
        notes.extend(_uninstall_systemd(spec, apply=apply))
    if kind == "cron" or (spec and spec.backend == "cron"):
        notes.extend(_uninstall_cron(apply=apply))
    for root in _meta_roots():
        path = root / META_NAME
        if path.is_file():
            path.unlink()
            notes.append(f"removed {path}")
        wrap = wrapper_path(root)
        if wrap.is_file():
            wrap.unlink()
            notes.append(f"removed {wrap}")
        twrap = train_wrapper_path(root)
        if twrap.is_file():
            twrap.unlink()
            notes.append(f"removed {twrap}")
    if not notes:
        notes.append("scheduler not installed")
    return notes


def load_spec(home: Path | None = None) -> ScheduleSpec | None:
    for root in _meta_roots(home):
        path = root / META_NAME
        if path.is_file():
            spec = _read_meta(path)
            if spec is not None:
                return spec
    return None


def scheduler_status(*, now: datetime | None = None) -> dict[str, Any]:
    spec = load_spec()
    kind = spec.backend if spec else detect_backend()
    loaded: bool | None = None
    if spec and spec.backend == "launchd":
        loaded = _launchd_loaded(spec.label)
    elif spec and spec.backend == "systemd":
        loaded = _systemd_loaded()
    nxt = None
    if spec is not None:
        nxt = next_local_run(spec.hour, spec.minute, now=now)
    plist = (
        _plist_path()
        if kind == "launchd" or (spec and spec.backend == "launchd")
        else None
    )
    return {
        "backend": kind,
        "installed": spec is not None,
        "python": str(spec.python) if spec else None,
        "home": str(spec.home) if spec else None,
        "hour": spec.hour if spec else None,
        "minute": spec.minute if spec else None,
        "next_run": nxt.isoformat(timespec="seconds") if nxt else None,
        "loaded": loaded,
        "plist": str(plist) if plist is not None else None,
        "log_out": str(spec.log_out) if spec else None,
        "log_err": str(spec.log_err) if spec else None,
        "wrapper": str(spec.wrapper)
        if spec and spec.wrapper
        else (str(wrapper_path(spec.home)) if spec else None),
        "unstable": _installed_paths_unstable(spec, plist),
        "stray": [str(p) for p in stray_agent_plists()],
    }


def format_status(info: dict[str, Any]) -> str:
    lines = [
        f"backend: {info.get('backend') or 'none'}",
        f"installed: {'yes' if info.get('installed') else 'no'}",
    ]
    if info.get("python"):
        lines.append(f"python: {info['python']}")
    if info.get("home"):
        lines.append(f"HOME: {info['home']}")
    if info.get("installed"):
        hour = info.get("hour")
        minute = info.get("minute")
        if hour is not None and minute is not None:
            lines.append(f"at: {int(hour):02d}:{int(minute):02d} local")
        if info.get("next_run"):
            lines.append(f"next run: {info['next_run']} (local)")
        loaded = info.get("loaded")
        if loaded is True:
            lines.append("loaded: yes")
        elif loaded is False:
            lines.append("loaded: no")
        if info.get("log_out"):
            lines.append(f"stdout: {info['log_out']}")
            lines.append(f"stderr: {info['log_err']}")
    else:
        lines.append("next run: not scheduled")
        lines.append("next: foreshadow schedule install")
    if info.get("unstable"):
        lines.append("FAIL: scheduler paths point at a Desktop/worktree")
        lines.append(
            "next: foreshadow schedule uninstall && foreshadow schedule install"
        )
    for stray in info.get("stray") or []:
        lines.append(f"WARN: extra LaunchAgent {stray}")
        lines.append("next: foreshadow schedule uninstall")
    return "\n".join(lines) + "\n"


def run_now(*, apply: bool = True, force: bool = False) -> int:
    spec = load_spec()
    if spec is None:
        raise ScheduleError("scheduler not installed — foreshadow schedule install")
    if apply and spec.backend == "launchd" and not force:
        kicked = _kickstart_launchd(spec.label)
        if kicked is not None:
            return kicked
    if apply and spec.backend == "systemd" and not force:
        proc = _run(["systemctl", "--user", "start", f"{SYSTEMD_UNIT}.service"])
        if proc.returncode == 0:
            return 0
    argv = list(spec.program_args)
    env = os.environ.copy()
    env["FORESHADOW_HOME"] = str(spec.home)
    env.setdefault("HOME", str(spec.user_home))
    py_dir = str(spec.python.parent)
    env["PATH"] = os.pathsep.join(
        [py_dir, "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
        + ([env["PATH"]] if env.get("PATH") else [])
    )
    if is_unstable_path(spec.python) or is_unstable_path(spec.home):
        raise ScheduleError(
            "installed scheduler points at a Desktop/worktree; "
            "run foreshadow schedule uninstall && foreshadow schedule install"
        )
    if not apply:
        return 0
    proc = subprocess.run(argv, env=env, check=False)
    return int(proc.returncode)


def stray_agent_plists() -> list[Path]:
    agents = _launch_agents_dir()
    if not agents.is_dir():
        return []
    found: list[Path] = []
    known = {f"{LAUNCHD_LABEL}.plist", f"{TRAIN_LABEL}.plist"}
    for path in sorted(agents.glob("*.plist")):
        name = path.name
        if name in known:
            continue
        if "foreshadow" not in name.lower() and name != f"{DOGFOOD_LABEL}.plist":
            continue
        found.append(path)
    dogfood = agents / f"{DOGFOOD_LABEL}.plist"
    if dogfood.is_file() and dogfood not in found:
        found.append(dogfood)
    return found


def plist_text_unstable(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return ".worktrees" in text or "Desktop/Foreshadow" in text


def _assert_spec_stable(spec: ScheduleSpec) -> None:
    paths: list[Path | str] = [
        spec.home,
        spec.log_out,
        spec.log_err,
        spec.train_log_out,
        spec.train_log_err,
        spec.user_home,
        *spec.program_args,
        *spec.train_program_args,
        train_wrapper_path(spec.home),
    ]
    if spec.wrapper is not None:
        paths.append(spec.wrapper)
    if not is_unstable_path(spec.python):
        paths.append(spec.python)
    for raw in paths:
        if is_unstable_path(raw):
            raise ScheduleError(f"refusing unstable scheduler path: {raw}")
        text = str(raw)
        if ".worktrees" in text or "Desktop/Foreshadow" in text:
            raise ScheduleError(f"refusing unstable scheduler path: {raw}")


def _installed_paths_unstable(spec: ScheduleSpec | None, plist: Path | None) -> bool:
    if spec is not None:
        try:
            _assert_spec_stable(spec)
        except ScheduleError:
            return True
    for path in (plist, _train_plist_path()):
        if path is not None and path.is_file() and plist_text_unstable(path):
            return True
    return False


def _meta_roots(home: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if home is not None:
        roots.append(Path(home))
    roots.append(resolve_data_dir())
    default = default_data_dir()
    if default not in roots:
        roots.append(default)
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            key = root.resolve()
        except OSError:
            key = root
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _write_meta(spec: ScheduleSpec) -> None:
    path = spec.home / META_NAME
    path.write_text(json.dumps(spec.to_json(), indent=2) + "\n", encoding="utf-8")
    current = resolve_data_dir()
    try:
        same = current.resolve() == spec.home.resolve()
    except OSError:
        same = current == spec.home
    if not same and not is_unstable_path(current):
        (current / META_NAME).write_text(
            json.dumps(spec.to_json(), indent=2) + "\n", encoding="utf-8"
        )


def _read_meta(path: Path) -> ScheduleSpec | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ScheduleSpec(
            backend=str(data["backend"]),
            python=Path(str(data["python"])),
            home=Path(str(data["home"])),
            hour=int(data["hour"]),
            minute=int(data["minute"]),
            user_home=Path(str(data.get("user_home") or Path.home())),
            label=str(data.get("label") or LAUNCHD_LABEL),
            wrapper=Path(str(data["wrapper"])) if data.get("wrapper") else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _imports_foreshadow(python: Path) -> bool:
    try:
        if python.resolve() == Path(sys.executable).resolve():
            return True
    except OSError:
        pass
    try:
        proc = subprocess.run(
            [str(python), "-c", "import foreshadow"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _systemd_user_available() -> bool:
    if not shutil.which("systemctl"):
        return False
    proc = _run(["systemctl", "--user", "is-system-running"])
    text = (proc.stdout or proc.stderr or "").strip().lower()
    if proc.returncode == 0:
        return True
    if "offline" in text:
        return False
    if proc.returncode == 4:
        return False
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return bool(runtime and (Path(runtime) / "systemd").exists())


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _plist_path() -> Path:
    return _launch_agents_dir() / f"{LAUNCHD_LABEL}.plist"


def _train_plist_path() -> Path:
    return _launch_agents_dir() / f"{TRAIN_LABEL}.plist"


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_plist(
    spec: ScheduleSpec,
    *,
    label: str | None = None,
    args: list[str] | None = None,
    weekly: bool = False,
    log_out: Path | None = None,
    log_err: Path | None = None,
) -> str:
    argv = spec.program_args if args is None else args
    args_xml = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in argv)
    path_dirs = [
        str(spec.user_home / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    if not is_unstable_path(spec.python):
        parent = str(spec.python.parent)
        if parent not in path_dirs:
            path_dirs.insert(0, parent)
    path_value = ":".join(path_dirs)
    job_label = label if label is not None else spec.label
    stdout = log_out if log_out is not None else spec.log_out
    stderr = log_err if log_err is not None else spec.log_err
    if weekly:
        calendar = f"""  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>0</integer>
    <key>Hour</key>
    <integer>{int(spec.hour)}</integer>
    <key>Minute</key>
    <integer>{int(spec.minute)}</integer>
  </dict>"""
    else:
        calendar = f"""  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{int(spec.hour)}</integer>
    <key>Minute</key>
    <integer>{int(spec.minute)}</integer>
  </dict>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_escape(job_label)}</string>
  <key>WorkingDirectory</key>
  <string>{_xml_escape(str(spec.home))}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>{_xml_escape(str(spec.user_home))}</string>
    <key>FORESHADOW_HOME</key>
    <string>{_xml_escape(str(spec.home))}</string>
    <key>PATH</key>
    <string>{_xml_escape(path_value)}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
{calendar}
  <key>StandardOutPath</key>
  <string>{_xml_escape(str(stdout))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(stderr))}</string>
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
"""


def render_train_plist(spec: ScheduleSpec) -> str:
    """Weekly launchd job: python -m foreshadow train. Not an always-on agent."""
    return render_plist(
        spec,
        label=TRAIN_LABEL,
        args=spec.train_program_args,
        weekly=True,
        log_out=spec.train_log_out,
        log_err=spec.train_log_err,
    )


def _install_launchd(spec: ScheduleSpec, *, apply: bool) -> list[str]:
    agents = _launch_agents_dir()
    agents.mkdir(parents=True, exist_ok=True)
    plist = _plist_path()
    train_plist = _train_plist_path()
    body = render_plist(spec)
    train_body = render_train_plist(spec)
    for text in (body, train_body):
        if ".worktrees" in text or "Desktop/Foreshadow" in text:
            raise ScheduleError("generated launchd plist would include a worktree path")
    plist.write_text(body, encoding="utf-8")
    train_plist.write_text(train_body, encoding="utf-8")
    notes = [f"wrote {plist}", f"wrote {train_plist}"]
    if apply:
        notes.extend(_activate_launchd(plist, spec.label))
        notes.extend(_activate_launchd(train_plist, TRAIN_LABEL))
    return notes


def _activate_launchd(plist: Path, label: str) -> list[str]:
    uid = os.getuid()
    domain = f"gui/{uid}"
    target = f"{domain}/{label}"
    notes: list[str] = []
    boot = _run(["launchctl", "bootout", target])
    load = _run(["launchctl", "bootstrap", domain, str(plist)])
    if load.returncode != 0:
        fallback = _run(["launchctl", "load", "-w", str(plist)])
        if fallback.returncode != 0:
            err = (load.stderr or fallback.stderr or load.stdout or "").strip()
            notes.append(f"launchctl load failed: {err or load.returncode}")
            notes.append("plist written; next: foreshadow doctor")
            return notes
    _run(["launchctl", "enable", target])
    if boot.returncode == 0:
        notes.append(f"reloaded {label}")
    else:
        notes.append(f"loaded {label}")
    return notes


def _uninstall_launchd(spec: ScheduleSpec | None, *, apply: bool) -> list[str]:
    notes: list[str] = []
    labels = [LAUNCHD_LABEL, TRAIN_LABEL]
    if spec and spec.label not in labels:
        labels.insert(0, spec.label)
    plists = {_plist_path(), _train_plist_path()}
    if apply:
        uid = os.getuid()
        for label in labels:
            plist = _launch_agents_dir() / f"{label}.plist"
            target = f"gui/{uid}/{label}"
            proc = _run(["launchctl", "bootout", target])
            if proc.returncode != 0:
                _run(["launchctl", "unload", "-w", str(plist)])
            notes.append(f"unloaded {label}")
    for plist in sorted(plists):
        if plist.is_file():
            plist.unlink()
            notes.append(f"removed {plist}")
    return notes


def _launchd_loaded(label: str) -> bool | None:
    if not shutil.which("launchctl"):
        return None
    uid = os.getuid()
    proc = _run(["launchctl", "print", f"gui/{uid}/{label}"])
    if proc.returncode == 0:
        return True
    listed = _run(["launchctl", "list", label])
    return listed.returncode == 0


def _kickstart_launchd(label: str) -> int | None:
    if not shutil.which("launchctl"):
        return None
    uid = os.getuid()
    target = f"gui/{uid}/{label}"
    proc = _run(["launchctl", "kickstart", "-k", target])
    if proc.returncode == 0:
        return 0
    started = _run(["launchctl", "start", label])
    if started.returncode == 0:
        return 0
    return None


def _systemd_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def render_systemd_service(spec: ScheduleSpec) -> str:
    args = " ".join(_sh_quote(a) for a in spec.program_args)
    return f"""[Unit]
Description=Foreshadow daily radar
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={spec.home}
Environment=HOME={spec.user_home}
Environment=FORESHADOW_HOME={spec.home}
ExecStart={args}
StandardOutput=append:{spec.log_out}
StandardError=append:{spec.log_err}
"""


def render_systemd_timer(spec: ScheduleSpec) -> str:
    return f"""[Unit]
Description=Foreshadow daily radar timer

[Timer]
OnCalendar=*-*-* {spec.hour:02d}:{spec.minute:02d}:00
Persistent=true
Unit={SYSTEMD_UNIT}.service

[Install]
WantedBy=timers.target
"""


def render_systemd_train_service(spec: ScheduleSpec) -> str:
    """Weekly oneshot. Memory-capped so 2GB VMs survive. Does not call GitHub."""
    args = " ".join(_sh_quote(a) for a in spec.train_program_args)
    return f"""[Unit]
Description=Foreshadow weekly train (local, no GitHub)
# Written only by `foreshadow schedule install`. Type=oneshot + timer, not a daemon.
# Do not add OnCalendar to {SYSTEMD_UNIT}.timer; that unit must stay run.
After={SYSTEMD_UNIT}.service

[Service]
Type=oneshot
WorkingDirectory={spec.home}
Environment=HOME={spec.user_home}
Environment=FORESHADOW_HOME={spec.home}
UnsetEnvironment=GITHUB_TOKEN GH_TOKEN
ExecStart={args}
StandardOutput=append:{spec.train_log_out}
StandardError=append:{spec.train_log_err}
Nice=10
MemoryMax=400M
"""


def render_systemd_train_timer(spec: ScheduleSpec) -> str:
    """Weekly calendar. Separate unit so the daily timer still starts `run`."""
    return f"""[Unit]
Description=Foreshadow weekly train timer

[Timer]
OnCalendar=Sun *-*-* {spec.hour:02d}:{spec.minute:02d}:00
Persistent=true
Unit={SYSTEMD_TRAIN_UNIT}.service

[Install]
WantedBy=timers.target
"""


def _install_systemd(spec: ScheduleSpec, *, apply: bool) -> list[str]:
    unit_dir = _systemd_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / f"{SYSTEMD_UNIT}.service"
    timer = unit_dir / f"{SYSTEMD_UNIT}.timer"
    train_service = unit_dir / f"{SYSTEMD_TRAIN_UNIT}.service"
    train_timer = unit_dir / f"{SYSTEMD_TRAIN_UNIT}.timer"
    bodies = {
        service: render_systemd_service(spec),
        timer: render_systemd_timer(spec),
        train_service: render_systemd_train_service(spec),
        train_timer: render_systemd_train_timer(spec),
    }
    for body in bodies.values():
        if ".worktrees" in body or "Desktop/Foreshadow" in body:
            raise ScheduleError("generated systemd unit would include a worktree path")
    notes: list[str] = []
    for path, body in bodies.items():
        path.write_text(body, encoding="utf-8")
        notes.append(f"wrote {path}")
    if apply:
        reload = _run(["systemctl", "--user", "daemon-reload"])
        enable = _run(
            [
                "systemctl",
                "--user",
                "enable",
                "--now",
                f"{SYSTEMD_UNIT}.timer",
                f"{SYSTEMD_TRAIN_UNIT}.timer",
            ]
        )
        if reload.returncode != 0 or enable.returncode != 0:
            err = (enable.stderr or reload.stderr or "").strip()
            notes.append(f"systemctl failed: {err or enable.returncode}")
            notes.append("units written; next: foreshadow doctor")
        else:
            notes.append(f"enabled {SYSTEMD_UNIT}.timer")
            notes.append(f"enabled {SYSTEMD_TRAIN_UNIT}.timer")
    return notes


def _uninstall_systemd(spec: ScheduleSpec | None, *, apply: bool) -> list[str]:
    notes: list[str] = []
    if apply:
        _run(["systemctl", "--user", "disable", "--now", f"{SYSTEMD_UNIT}.timer"])
        _run(["systemctl", "--user", "disable", "--now", f"{SYSTEMD_TRAIN_UNIT}.timer"])
        _run(["systemctl", "--user", "stop", f"{SYSTEMD_UNIT}.service"])
        _run(["systemctl", "--user", "stop", f"{SYSTEMD_TRAIN_UNIT}.service"])
        _run(["systemctl", "--user", "daemon-reload"])
        notes.append(f"disabled {SYSTEMD_UNIT}.timer")
        notes.append(f"disabled {SYSTEMD_TRAIN_UNIT}.timer")
    unit_dir = _systemd_dir()
    for name in (
        f"{SYSTEMD_UNIT}.service",
        f"{SYSTEMD_UNIT}.timer",
        f"{SYSTEMD_TRAIN_UNIT}.service",
        f"{SYSTEMD_TRAIN_UNIT}.timer",
    ):
        path = unit_dir / name
        if path.is_file():
            path.unlink()
            notes.append(f"removed {path}")
    return notes


def _systemd_loaded() -> bool | None:
    if not shutil.which("systemctl"):
        return None
    proc = _run(["systemctl", "--user", "is-enabled", f"{SYSTEMD_UNIT}.timer"])
    text = (proc.stdout or "").strip()
    if proc.returncode == 0 or text == "enabled":
        return True
    if text in {"disabled", "masked", "static"}:
        return False
    return False


def render_cron_line(spec: ScheduleSpec) -> str:
    env = (
        f"HOME={_sh_quote(str(spec.user_home))} "
        f"FORESHADOW_HOME={_sh_quote(str(spec.home))}"
    )
    cmd = " ".join(_sh_quote(a) for a in spec.program_args)
    out = _sh_quote(str(spec.log_out))
    err = _sh_quote(str(spec.log_err))
    work = _sh_quote(str(spec.home))
    return (
        f"{spec.minute} {spec.hour} * * * {env} cd {work} && {cmd} >> {out} 2>> {err}"
    )


def render_cron_train_line(spec: ScheduleSpec) -> str:
    """Sunday line in the same crontab block. Local train; no GitHub env."""
    env = (
        f"HOME={_sh_quote(str(spec.user_home))} "
        f"FORESHADOW_HOME={_sh_quote(str(spec.home))}"
    )
    cmd = " ".join(_sh_quote(a) for a in spec.train_program_args)
    out = _sh_quote(str(spec.train_log_out))
    err = _sh_quote(str(spec.train_log_err))
    work = _sh_quote(str(spec.home))
    return (
        f"{spec.minute} {spec.hour} * * 0 {env} cd {work} && "
        f"env -u GITHUB_TOKEN -u GH_TOKEN {cmd} >> {out} 2>> {err}"
    )


def render_cron_block(spec: ScheduleSpec) -> str:
    return render_cron_line(spec) + "\n" + render_cron_train_line(spec)


def _install_cron(spec: ScheduleSpec, *, apply: bool) -> list[str]:
    block = render_cron_block(spec)
    if ".worktrees" in block or "Desktop/Foreshadow" in block:
        raise ScheduleError("generated cron line would include a worktree path")
    notes = [f"cron: {CRON_BEGIN}"]
    if not apply:
        notes.append(block)
        return notes
    current = _crontab_get()
    updated = _crontab_replace(current, block)
    err = _crontab_set(updated)
    if err:
        notes.append(f"crontab failed: {err}")
        notes.append("next: foreshadow doctor")
    else:
        notes.append("installed crontab entry")
    return notes


def _uninstall_cron(*, apply: bool) -> list[str]:
    if not apply:
        return ["cron markers would be removed"]
    current = _crontab_get()
    if CRON_BEGIN not in current:
        return []
    updated = _crontab_replace(current, None)
    err = _crontab_set(updated)
    if err:
        return [f"crontab failed: {err}"]
    return ["removed crontab entry"]


def _crontab_get() -> str:
    proc = _run(["crontab", "-l"])
    if proc.returncode != 0:
        return ""
    return proc.stdout or ""


def _crontab_set(text: str) -> str | None:
    proc = subprocess.run(
        ["crontab", "-"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or str(proc.returncode)).strip()
    return None


def _crontab_replace(existing: str, line: str | None) -> str:
    rows = existing.splitlines()
    out: list[str] = []
    skipping = False
    for row in rows:
        if row.strip() == CRON_BEGIN:
            skipping = True
            continue
        if skipping:
            if row.strip() == CRON_END:
                skipping = False
            continue
        out.append(row)
    if line is not None:
        if out and out[-1].strip():
            out.append("")
        out.extend([CRON_BEGIN, line, CRON_END])
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 1, "", str(exc))


def install_schedule(*, apply: bool = True, at: str = DEFAULT_AT) -> dict[str, Any]:
    spec, notes = install(at=at, apply=apply, verify=False)
    wrap = spec.wrapper or wrapper_path(spec.home)
    return {
        "kind": spec.backend,
        "home": str(spec.home),
        "python": str(spec.python),
        "wrapper": str(wrap),
        "plist": str(_plist_path()) if spec.backend == "launchd" else None,
        "notes": notes,
        "unsafe_executable": is_unstable_path(sys.executable),
        "hour": spec.hour,
        "minute": spec.minute,
    }


def format_install(info: dict[str, Any]) -> str:
    lines = [
        f"scheduler: {info.get('kind')}",
        f"home: {info.get('home')}",
        f"wrapper: {info.get('wrapper')}",
        f"python: {info.get('python')}",
        "job: python -m foreshadow run",
        "train: python -m foreshadow train (weekly oneshot, no GitHub)",
    ]
    if info.get("unsafe_executable"):
        lines.append(
            "WARN: current interpreter is a Desktop/worktree; "
            "the installed job uses a HOME wrapper, not that checkout"
        )
    for note in info.get("notes") or []:
        lines.append(str(note))
    lines.append("next: foreshadow schedule status")
    return "\n".join(lines) + "\n"


def uninstall_schedule(*, apply: bool = True) -> dict[str, Any]:
    notes = uninstall(apply=apply)
    return {"notes": notes, "removed": True}


def format_uninstall(info: dict[str, Any]) -> str:
    notes = info.get("notes") or ["scheduler not installed"]
    return "\n".join(str(n) for n in notes) + "\n"


def schedule_status(*, now: datetime | None = None) -> dict[str, Any]:
    return scheduler_status(now=now)


def format_schedule_status(info: dict[str, Any]) -> str:
    return format_status(info)
