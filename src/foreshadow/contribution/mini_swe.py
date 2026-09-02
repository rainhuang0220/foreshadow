"""mini-SWE-agent backend. Optional extra. Host holds the model key; sandbox does not."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from foreshadow.contribution.clone import clone_public_github, git_env_without_tokens
from foreshadow.contribution.executor import (
    BackendNotInstalled,
    ContributionError,
    ContributionJob,
    PatchArtifact,
)
from foreshadow.contribution.task import StructuredTask

_EXTRA_NAMES = ("minisweagent",)
STEP_LIMIT = 24
INSTALL_TIMEOUT_S = 240
TEST_TIMEOUT_S = 180
AGENT_TIMEOUT_S = 900
DEFAULT_IMAGE = os.environ.get("FORESHADOW_SANDBOX_IMAGE", "python:3.12-bookworm-slim")


def _extra_available() -> bool:
    return any(importlib.util.find_spec(name) is not None for name in _EXTRA_NAMES)


def _require() -> None:
    if _extra_available():
        return
    raise BackendNotInstalled(
        "mini_swe_agent backend is not installed. "
        "Install mini-swe-agent in the environment; Foreshadow does not vendor it."
    )


def sandbox_env_for_container() -> dict[str, str]:
    """Env forwarded into the coding sandbox. No tokens, no host secrets."""
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp/foreshadow-home",
        "PYTHONUNBUFFERED": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "PAGER": "cat",
    }


class MiniSweExecutor:
    name = "mini_swe_agent"

    def __init__(
        self,
        *,
        agent_factory: Callable[..., Any] | None = None,
        docker: bool | None = None,
    ) -> None:
        if agent_factory is None:
            _require()
        self.agent_factory = agent_factory
        self.use_docker = bool(shutil.which("docker")) if docker is None else docker
        self.last_sandbox_env: dict[str, str] | None = None
        self.last_network_note: dict[str, str] | None = None
        self.last_cost: float | None = None
        self.last_steps: int | None = None
        self.container_id: str | None = None

    def prepare(self, job: ContributionJob) -> None:
        work = (
            Path(job.work_dir)
            if job.work_dir
            else Path(tempfile.mkdtemp(prefix="foreshadow-miniswe-"))
        )
        work.mkdir(parents=True, exist_ok=True)
        job.work_dir = work
        sandbox = work / "repo"
        if job.source_dir is not None:
            if sandbox.exists():
                shutil.rmtree(sandbox)
            shutil.copytree(
                job.source_dir,
                sandbox,
                ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git"),
                dirs_exist_ok=False,
            )
            _git_reinit(sandbox)
        else:
            if sandbox.exists():
                shutil.rmtree(sandbox)
            clone_public_github(job.full_name, sandbox)
        job.sandbox_path = sandbox
        self.last_sandbox_env = sandbox_env_for_container()
        job.log.append(
            {
                "step": "preparing_sandbox",
                "sandbox": str(sandbox),
                "docker": self.use_docker,
                "remotes": _remotes(sandbox),
            }
        )

    def analyze(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        structured = _structured(job)
        job.log.append(
            {
                "step": "selected_task",
                "repository": job.full_name,
                "issue": structured.issue_number if structured else None,
                "task": structured.task if structured else job.why,
                "files": list(structured.relevant_files) if structured else [],
            }
        )
        commands = list(structured.test_commands) if structured else []
        if not commands:
            commands = ["python -m pytest -o addopts= -q"]
        job.task = dict(job.task or {})
        job.task["test_commands"] = commands
        if self.use_docker and (sandbox / "pyproject.toml").exists():
            self._start_container(sandbox)
            self._install_in_container(job)
        else:
            self._install_on_host(job)
        baseline = self._run_tests(job, label="baseline")
        job.task["baseline"] = baseline
        job.log.append(
            {
                "step": "baseline_tests",
                **{k: baseline.get(k) for k in ("ok", "returncode", "command")},
            }
        )

    def implement(self, job: ContributionJob) -> None:
        structured = _structured(job)
        prompt = (
            structured.to_prompt()
            if structured
            else str((job.task or {}).get("prompt") or job.why)
        )
        if not prompt.strip():
            raise ContributionError(
                "mini_swe_agent needs a structured task, not 'fix repo'"
            )
        job.log.append({"step": "implementing", "backend": self.name})
        result = self._run_agent(job, prompt)
        job.log.append(
            {
                "step": "agent_finished",
                "exit_status": result.get("exit_status"),
                "steps": result.get("steps"),
                "cost": result.get("cost"),
            }
        )
        self.last_cost = result.get("cost")
        self.last_steps = result.get("steps")

    def test(self, job: ContributionJob) -> None:
        result = self._run_tests(job, label="tests")
        job.test_result = result
        job.log.append(
            {
                "step": "tests",
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
                "command": result.get("command"),
            }
        )

    def iterate(self, job: ContributionJob) -> None:
        if job.test_result and job.test_result.get("ok"):
            return
        log = str((job.test_result or {}).get("log") or "")[-2000:]
        structured = _structured(job)
        prompt = (
            "The tests failed after the first attempt. Fix the remaining failures.\n"
            f"{structured.to_prompt() if structured else ''}\n\nTEST OUTPUT:\n{log}"
        )
        job.log.append({"step": "iteration_1", "reason": "tests failed"})
        self._run_agent(job, prompt, step_limit=12)
        result = self._run_tests(job, label="tests_after_iteration")
        job.test_result = result
        job.log.append(
            {
                "step": "iteration_1_tests",
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
            }
        )

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        sandbox = _require_sandbox(job)
        self._stop_container()
        diff = _git_diff(sandbox)
        files = _diff_files(diff)
        tests = job.test_result or {}
        structured = _structured(job)
        title = ""
        if structured and structured.issue_number is not None:
            title = f"Fix {structured.task} (#{structured.issue_number})"
        elif structured:
            title = structured.task[:72]
        artifact = PatchArtifact(
            diff=diff,
            why=job.why or (structured.why if structured else ""),
            test_log=str(tests.get("log") or ""),
            files=files,
            title=title,
            body=structured.to_prompt() if structured else job.why,
            tests_passed=bool(tests.get("ok")),
            risk="local sandbox only; remote GitHub writes are refused",
        )
        job.log.append(
            {"step": "produce_patch", "files": files, "diff_bytes": len(diff)}
        )
        return artifact

    def _run_agent(
        self, job: ContributionJob, prompt: str, *, step_limit: int = STEP_LIMIT
    ) -> dict[str, Any]:
        sandbox = _require_sandbox(job)
        factory = self.agent_factory
        if factory is not None:
            agent = factory(job=job, sandbox=sandbox)
            out = agent.run(prompt)
            return (
                out
                if isinstance(out, dict)
                else {"exit_status": "submitted", "steps": 1, "cost": 0}
            )
        return self._run_real_agent(job, prompt, step_limit=step_limit)

    def _run_real_agent(
        self, job: ContributionJob, prompt: str, *, step_limit: int
    ) -> dict[str, Any]:
        _require()
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.environments.docker import DockerEnvironment
        from minisweagent.environments.local import LocalEnvironment
        from minisweagent.models.litellm_model import LitellmModel

        sandbox = _require_sandbox(job)
        model_name = (
            os.environ.get("MSWEA_MODEL_NAME")
            or os.environ.get("FORESHADOW_MINISWE_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or "anthropic/claude-sonnet-4-5"
        )
        model_kwargs: dict[str, Any] = {}
        if os.environ.get("ANTHROPIC_BASE_URL"):
            model_kwargs["api_base"] = os.environ["ANTHROPIC_BASE_URL"]
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "ANTHROPIC_AUTH_TOKEN"
        )
        if key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = key
        if self.use_docker:
            if not self.container_id:
                self._start_container(sandbox)
            env = DockerEnvironment(
                image=DEFAULT_IMAGE,
                cwd="/work",
                env=sandbox_env_for_container(),
                forward_env=[],
                run_args=["--rm", "-v", f"{sandbox.resolve()}:/work"],
                timeout=60,
            )
            # DockerEnvironment starts its own container; stop ours if we started one
            # and use the agent's, then exec install there if needed.
            self._stop_container()
            self.container_id = env.container_id
            self._install_in_container(job)
            self._disconnect_network()
        else:
            env = LocalEnvironment(
                cwd=str(sandbox), env=sandbox_env_for_container(), timeout=60
            )
        agent = DefaultAgent(
            LitellmModel(model_name=model_name, model_kwargs=model_kwargs),
            env,
            system_template=_SYSTEM,
            instance_template=_INSTANCE,
            step_limit=step_limit,
            cost_limit=8.0,
        )
        try:
            result = agent.run(prompt)
        finally:
            closer = getattr(env, "cleanup", None) or getattr(env, "close", None)
            if callable(closer):
                try:
                    closer()
                except (OSError, RuntimeError, TypeError):
                    pass
            self.container_id = None
        extra = result if isinstance(result, dict) else {}
        return {
            "exit_status": extra.get("exit_status")
            or extra.get("info", {}).get("exit_status"),
            "steps": getattr(agent, "n_calls", None),
            "cost": getattr(agent, "cost", None),
            "raw": extra,
        }

    def _start_container(self, sandbox: Path) -> None:
        if not self.use_docker:
            return
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "-w",
            "/work",
            "-v",
            f"{sandbox.resolve()}:/work",
            "-e",
            "PIP_DISABLE_PIP_VERSION_CHECK=1",
            DEFAULT_IMAGE,
            "sleep",
            "2h",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=180
        )
        self.container_id = proc.stdout.strip()
        self.last_network_note = {
            "network_enabled": "during dependency install only",
            "why": "pip install of the cloned repo's test extra",
        }

    def _install_in_container(self, job: ContributionJob) -> None:
        if not self.container_id:
            return
        cmd = (
            "python -m pip install -q -e . pytest && "
            "python -c 'import pathlib; print(pathlib.Path(\".\").resolve())'"
        )
        proc = subprocess.run(
            ["docker", "exec", "-w", "/work", self.container_id, "bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
        )
        job.log.append(
            {
                "step": "install",
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "network": self.last_network_note,
                "log": (proc.stdout + proc.stderr)[-1500:],
            }
        )
        if proc.returncode != 0:
            raise ContributionError(
                f"sandbox pip install failed: {(proc.stderr or proc.stdout)[-400:]}"
            )
        self._disconnect_network()

    def _install_on_host(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        if (
            not (sandbox / "pyproject.toml").exists()
            and not (sandbox / "setup.py").exists()
        ):
            job.log.append({"step": "install", "ok": True, "skipped": "no pyproject"})
            return
        venv = sandbox / ".venv"
        if not venv.exists():
            subprocess.run(
                ["uv", "venv", str(venv), "--python", "python3.12"],
                check=False,
                capture_output=True,
            )
        py = venv / "bin" / "python"
        if not py.exists():
            py = Path("python3")
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "-q", "-e", ".", "pytest"],
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
            env={
                **git_env_without_tokens(),
                **sandbox_env_for_container(),
                "PATH": os.environ.get("PATH", ""),
            },
        )
        job.log.append(
            {
                "step": "install",
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "network": {
                    "network_enabled": "host pip install",
                    "why": "docker not used",
                },
            }
        )

    def _disconnect_network(self) -> None:
        if not self.container_id:
            return
        subprocess.run(
            ["docker", "network", "disconnect", "bridge", self.container_id],
            capture_output=True,
            check=False,
        )

    def _stop_container(self) -> None:
        if not self.container_id:
            return
        subprocess.run(
            ["docker", "rm", "-f", self.container_id], capture_output=True, check=False
        )
        self.container_id = None

    def _run_tests(self, job: ContributionJob, *, label: str) -> dict[str, Any]:
        sandbox = _require_sandbox(job)
        commands = list(
            (job.task or {}).get("test_commands") or ["python -m pytest -o addopts= -q"]
        )
        command = commands[0]
        if self.container_id:
            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-w",
                    "/work",
                    self.container_id,
                    "bash",
                    "-lc",
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_S,
                check=False,
            )
        else:
            proc = subprocess.run(
                ["bash", "-lc", command],
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_S,
                check=False,
                env=git_env_without_tokens(),
            )
        log = (proc.stdout or "") + (proc.stderr or "")
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "command": command,
            "log": log[-8000:],
            "label": label,
        }


def _structured(job: ContributionJob) -> StructuredTask | None:
    raw = (job.task or {}).get("structured")
    if isinstance(raw, StructuredTask):
        return raw
    if isinstance(raw, dict):
        try:
            return StructuredTask.model_validate(raw)
        except (TypeError, ValueError):
            return None
    return None


def _require_sandbox(job: ContributionJob) -> Path:
    if job.sandbox_path is None or not Path(job.sandbox_path).is_dir():
        raise ContributionError("sandbox is not prepared")
    return Path(job.sandbox_path)


def _git_reinit(dest: Path) -> None:
    env = git_env_without_tokens()
    ignore = dest / ".gitignore"
    if not ignore.exists():
        ignore.write_text(
            "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n", encoding="utf-8"
        )
    subprocess.run(["git", "init"], cwd=dest, env=env, capture_output=True, check=False)
    subprocess.run(
        ["git", "config", "core.hooksPath", "/dev/null"],
        cwd=dest,
        env=env,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "add", "-A"], cwd=dest, env=env, capture_output=True, check=False
    )
    subprocess.run(
        ["git", "commit", "-m", "sandbox snapshot", "--allow-empty"],
        cwd=dest,
        env={
            **env,
            "GIT_AUTHOR_NAME": "foreshadow",
            "GIT_AUTHOR_EMAIL": "foreshadow@local",
            "GIT_COMMITTER_NAME": "foreshadow",
            "GIT_COMMITTER_EMAIL": "foreshadow@local",
        },
        capture_output=True,
        check=False,
    )


def _remotes(dest: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(dest), "remote"],
        capture_output=True,
        text=True,
        env=git_env_without_tokens(),
        check=False,
    )
    return [line for line in (proc.stdout or "").splitlines() if line.strip()]


def _git_diff(dest: Path) -> str:
    ignore = dest / ".gitignore"
    if not ignore.exists():
        ignore.write_text("__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(dest), "add", "-A"],
        capture_output=True,
        env=git_env_without_tokens(),
        check=False,
    )
    proc = subprocess.run(
        ["git", "-C", str(dest), "diff", "--cached", "--no-ext-diff"],
        capture_output=True,
        text=True,
        env=git_env_without_tokens(),
        check=False,
    )
    return proc.stdout or ""


def _diff_files(diff: str) -> list[str]:
    from foreshadow.contribution.qa import diff_files

    return diff_files(diff)


_SYSTEM = """You are a software engineering agent working in an isolated clone.
Respond with exactly ONE bash command in a ```mswea_bash_command block.
Do not push, do not use gh, do not read host secrets.
When the acceptance criteria are met, run: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
"""

_INSTANCE = """Please solve this issue:

{{task}}

Work in the current directory. Edit source, add regression tests, run the listed test commands.
"""
