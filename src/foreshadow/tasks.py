"""Local Mission → Task → Action → Result. Never pushes or posts."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from foreshadow.mission import (
    _git_env,
    dependency_authorization_gate,
    detect_local_tests,
    refuse_unsafe_local_cmd,
    run_local_tests,
)

LOG_LIMIT = 8000


@dataclass
class TaskResult:
    task: str
    action: str
    ok: bool
    blocked: bool
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifact: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "action": self.action,
            "ok": self.ok,
            "blocked": self.blocked,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifact": self.artifact,
        }


def append_task_log(
    dest: Path,
    *,
    task: str,
    command: str = "",
    exit_code: int | None = None,
    result: str = "",
    verdict: str = "UNKNOWN",
    next_step: str = "",
) -> str | None:
    """Append a TASK/COMMAND/EXIT/RESULT/VERDICT/NEXT block. dest is sidecar dir or file."""
    path = Path(dest)
    if path.suffix.lower() != ".md":
        path = path / "TASK_LOG.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        exit_s = "—" if exit_code is None else str(exit_code)
        when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = (
            f"WHEN: {when}\n"
            f"TASK: {task}\n"
            f"COMMAND: {command or '—'}\n"
            f"EXIT: {exit_s}\n"
            f"RESULT: {(result or '—')[:LOG_LIMIT]}\n"
            f"VERDICT: {verdict or 'UNKNOWN'}\n"
            f"NEXT: {next_step or '—'}\n\n"
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(block)
    except OSError:
        return None
    return str(path)


def run_task(
    clone_dir: Path,
    task: str,
    *,
    runner: Any | None = None,
    message: str | None = None,
) -> TaskResult:
    if task in {"reproduce_issue", "collect_tests"}:
        return _run_tests(clone_dir, task, runner=runner)
    if task == "inspect_tree":
        return _inspect(clone_dir)
    if task == "local_commit":
        return local_commit(clone_dir, message or "chore: local entry work", runner=runner)
    return TaskResult(
        task=task,
        action="skip",
        ok=False,
        blocked=False,
        status="skipped",
        stderr=f"unknown task {task}",
    )


def _run_tests(clone_dir: Path, task: str, *, runner: Any | None) -> TaskResult:
    detected = detect_local_tests(clone_dir)
    kind = detected.get("kind")
    sidecar = Path(clone_dir).parent
    if kind in {"node", "cargo"}:
        gate = dependency_authorization_gate(clone_dir)
        msg = (gate or {}).get("message_zh") or (
            f"{kind} tests skipped; Foreshadow will not run npm/cargo"
        )
        status = str((gate or {}).get("status") or "skipped")
        log = append_task_log(
            sidecar,
            task=task,
            command="",
            result=msg,
            verdict="UNKNOWN",
            next_step="等待你的确认才能执行任何远程 GitHub 操作。",
        )
        return TaskResult(
            task=task,
            action="skip",
            ok=False,
            blocked=False,
            status=status,
            stderr=msg,
            artifact=log,
        )
    out = run_local_tests(clone_dir, runner=runner, execute=False)
    log = append_task_log(
        sidecar,
        task=task,
        command=str(out.get("command") or ""),
        exit_code=out.get("returncode"),
        result=str(out.get("summary") or out.get("error") or out.get("status") or ""),
        verdict="UNKNOWN",
        next_step="等待你的确认才能执行任何远程 GitHub 操作。",
    )
    return TaskResult(
        task=task,
        action="run_test",
        ok=bool(out.get("ok")),
        blocked=False,
        status=str(out.get("status") or "failed"),
        exit_code=out.get("returncode") if "returncode" in out else None,
        stdout=str(out.get("summary") or out.get("stdout") or "")[:LOG_LIMIT],
        stderr=str(out.get("error") or out.get("stderr") or "")[:LOG_LIMIT],
        artifact=log,
    )


def _inspect(clone_dir: Path) -> TaskResult:
    root = Path(clone_dir)
    if not root.is_dir():
        return TaskResult(
            task="inspect_tree",
            action="skip",
            ok=False,
            blocked=False,
            status="skipped",
            stderr="no clone",
        )
    names = sorted(p.name for p in root.iterdir())[:20]
    return TaskResult(
        task="inspect_tree",
        action="list",
        ok=True,
        blocked=False,
        status="ok",
        stdout=", ".join(names),
    )


def local_commit(
    clone_dir: Path,
    message: str,
    *,
    runner: Any | None = None,
) -> TaskResult:
    root = Path(clone_dir)
    if not (root / ".git").exists():
        return TaskResult(
            task="local_commit",
            action="git_commit",
            ok=False,
            blocked=False,
            status="skipped",
            stderr="no clone",
        )
    if not (message or "").strip():
        return TaskResult(
            task="local_commit",
            action="git_commit",
            ok=False,
            blocked=True,
            status="blocked",
            stderr="empty commit message",
        )
    run = runner or subprocess.run

    def git(*args: str) -> Any:
        cmd = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args]
        blocked = refuse_unsafe_local_cmd(cmd)
        if blocked is not None:
            return blocked
        return run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=_git_env(),
        )

    added = git("add", "-A")
    if isinstance(added, dict):
        return TaskResult(
            task="local_commit",
            action="git_commit",
            ok=False,
            blocked=True,
            status="blocked",
            stderr=str(added.get("error") or "refused"),
        )
    committed = git("commit", "-m", message.strip())
    if isinstance(committed, dict):
        return TaskResult(
            task="local_commit",
            action="git_commit",
            ok=False,
            blocked=True,
            status="blocked",
            stderr=str(committed.get("error") or "refused"),
        )
    code = getattr(committed, "returncode", 1)
    stdout = (getattr(committed, "stdout", None) or "")[:LOG_LIMIT]
    stderr = (getattr(committed, "stderr", None) or "")[:LOG_LIMIT]
    if code != 0:
        return TaskResult(
            task="local_commit",
            action="git_commit",
            ok=False,
            blocked=False,
            status="skipped" if "nothing to commit" in (stdout + stderr).lower() else "failed",
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
        )
    return TaskResult(
        task="local_commit",
        action="git_commit",
        ok=True,
        blocked=False,
        status="ok",
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
    )
