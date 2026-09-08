"""Host worktree backend. Packages an already-cloned mission repo. Never demo_add."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from foreshadow.contribution.executor import (
    ContributionError,
    ContributionJob,
    PatchArtifact,
    RemoteWriteRefused,
)
from foreshadow.contribution.native import sandbox_env
from foreshadow.contribution.qa import diff_files
from foreshadow.contribution.task import StructuredTask


class WorkspaceExecutor:
    name = "workspace"

    def __init__(self) -> None:
        self.last_sandbox_env: dict[str, str] | None = None

    def prepare(self, job: ContributionJob) -> None:
        sandbox = _resolve_sandbox(job)
        job.sandbox_path = sandbox
        job.work_dir = job.work_dir or sandbox.parent
        _disable_hooks(sandbox)
        remotes = _git(sandbox, "remote")
        if remotes.stdout.strip():
            for name in remotes.stdout.split():
                _git(sandbox, "remote", "remove", name)
        self.last_sandbox_env = sandbox_env(home=(job.work_dir or sandbox.parent) / "home")
        job.log.append(
            {
                "step": "prepare",
                "sandbox": str(sandbox),
                "backend": self.name,
                "hooksPath": "/dev/null",
            }
        )

    def analyze(self, job: ContributionJob) -> None:
        sandbox = _require(job)
        job.log.append(
            {
                "step": "analyze",
                "files": sorted(p.name for p in sandbox.iterdir() if p.name != ".git")[:24],
            }
        )

    def implement(self, job: ContributionJob) -> None:
        if str((job.task or {}).get("fixture") or "") == "demo_add":
            raise ContributionError("workspace backend refuses demo_add")
        sandbox = _require(job)
        dirty = _git(sandbox, "status", "--porcelain")
        if not (dirty.stdout or "").strip():
            raise ContributionError(
                "workspace backend needs an existing local implementation; "
                "it will not invent a demo_add patch"
            )
        job.log.append({"step": "implement", "via": "existing_worktree"})

    def test(self, job: ContributionJob) -> None:
        sandbox = _require(job)
        env = sandbox_env(home=(job.work_dir or sandbox.parent) / "home")
        self.last_sandbox_env = dict(env)
        commands = list((job.task or {}).get("test_commands") or [])
        structured = (job.task or {}).get("structured")
        if not commands and isinstance(structured, dict):
            commands = list(structured.get("test_commands") or [])
        if not commands:
            commands = ["go test ./cmd/deja -count=1"]
        logs: list[str] = []
        ok = True
        last_code = 0
        used = commands[0]
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=sandbox,
                capture_output=True,
                text=True,
                shell=True,
                timeout=360,
                check=False,
                env=_test_env(env, command),
            )
            used = command
            last_code = completed.returncode
            logs.append(completed.stdout or "")
            logs.append(completed.stderr or "")
            if completed.returncode != 0:
                ok = False
                break
        job.test_result = {
            "ok": ok,
            "returncode": last_code,
            "command": used,
            "log": "\n".join(logs),
        }
        job.log.append(
            {"step": "test", "ok": ok, "returncode": last_code, "command": used}
        )

    def iterate(self, job: ContributionJob) -> None:
        return

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        sandbox = _require(job)
        # New files are untracked until added. Stage locally so the package
        # includes them; never commit, never push.
        _git(sandbox, "add", "-A")
        diff = _git(sandbox, "diff", "--cached", "--no-ext-diff", "HEAD").stdout or ""
        if not diff.strip():
            diff = _git(sandbox, "diff", "--no-ext-diff", "HEAD").stdout or ""
        files = diff_files(diff)
        tests = job.test_result or {}
        structured = _structured(job)
        title = _pr_title(structured, files)
        artifact = PatchArtifact(
            diff=diff,
            why=job.why or (structured.why if structured else ""),
            test_log=str(tests.get("log") or ""),
            files=files,
            title=title[:120],
            body=structured.to_prompt() if structured else job.why,
            tests_passed=bool(tests.get("ok")),
        )
        job.log.append(
            {"step": "produce_patch", "files": files, "diff_bytes": len(diff)}
        )
        return artifact


def _pr_title(structured: StructuredTask | None, files: list[str]) -> str:
    if structured is None:
        return ""
    if structured.issue_number is None:
        return structured.task[:120]
    blob = " ".join(files).lower()
    scope = "deja"
    if "doctor" in blob or "plugin" in blob:
        scope = "doctor"
    elif "/sources/" in blob:
        scope = "sources"
    summary = (structured.task or "").strip()
    if "grok" in summary.lower() and "stale" in summary.lower():
        summary = "report a stale Grok plugin"
    elif summary:
        summary = summary[0].lower() + summary[1:]
        if len(summary) > 60:
            summary = summary[:57] + "..."
    else:
        summary = "contribution"
    return f"fix({scope}): {summary} (#{structured.issue_number})"[:120]


def _structured(job: ContributionJob) -> StructuredTask | None:
    raw = (job.task or {}).get("structured")
    if not isinstance(raw, dict):
        return None
    try:
        return StructuredTask.model_validate(raw)
    except (TypeError, ValueError):
        return None


def _resolve_sandbox(job: ContributionJob) -> Path:
    if job.source_dir is not None and Path(job.source_dir).is_dir():
        return Path(job.source_dir)
    if job.sandbox_path is not None and Path(job.sandbox_path).is_dir():
        return Path(job.sandbox_path)
    raise ContributionError("workspace backend needs a cloned source_dir")


def _require(job: ContributionJob) -> Path:
    if job.sandbox_path is None or not Path(job.sandbox_path).is_dir():
        raise ContributionError("sandbox is not prepared")
    return Path(job.sandbox_path)


def _test_env(env: dict[str, str], command: str) -> dict[str, str]:
    out = dict(env)
    if "go test" in command or command.strip().startswith("go "):
        # Fresh HOME has no module cache; deja-vu (and similar) must stay offline.
        out.setdefault("GOPROXY", "off")
        out.setdefault("GOSUMDB", "off")
    return out


def _disable_hooks(sandbox: Path) -> None:
    _git(sandbox, "config", "core.hooksPath", "/dev/null")


def _git(sandbox: Path, *args: str) -> subprocess.CompletedProcess[str]:
    verbs = [a for a in args if not a.startswith("-")]
    if "push" in verbs:
        raise RemoteWriteRefused("git push is refused")
    env = os.environ.copy()
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GH_HOST"):
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", str(sandbox), "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
