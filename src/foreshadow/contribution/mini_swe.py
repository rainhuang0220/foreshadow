"""mini-SWE-agent backend. Optional extra. Host holds the model key; sandbox does not."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
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
INSTALL_TIMEOUT_S = 300
TEST_TIMEOUT_S = 180
AGENT_TIMEOUT_S = 900
DEFAULT_IMAGE = os.environ.get("FORESHADOW_SANDBOX_IMAGE", "python:3.12-slim-bookworm")


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
        on_event: Callable[[ContributionJob], None] | None = None,
    ) -> None:
        if agent_factory is None:
            _require()
        self.agent_factory = agent_factory
        self.use_docker = bool(shutil.which("docker")) if docker is None else docker
        self.on_event = on_event
        self.last_sandbox_env: dict[str, str] | None = None
        self.last_network_note: dict[str, str] | None = None
        self.last_cost: float | None = None
        self.last_steps: int | None = None
        self.container_id: str | None = None
        self._env: Any = None

    def _emit(self, job: ContributionJob, event: dict[str, Any]) -> None:
        job.log.append(event)
        if self.on_event is not None:
            self.on_event(job)

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
        self._emit(
            job,
            {
                "step": "preparing_sandbox",
                "sandbox": str(sandbox),
                "docker": self.use_docker,
                "remotes": _remotes(sandbox),
            },
        )

    def analyze(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        structured = _structured(job)
        self._emit(
            job,
            {
                "step": "analyzing_repository",
                "repository": job.full_name,
                "tree": sorted(p.name for p in sandbox.iterdir() if p.name != ".git")[
                    :24
                ],
            },
        )
        self._emit(
            job,
            {
                "step": "selected_task",
                "repository": job.full_name,
                "issue": structured.issue_number if structured else None,
                "task": structured.task if structured else job.why,
                "files": list(structured.relevant_files) if structured else [],
            },
        )
        commands = list(structured.test_commands) if structured else []
        if not commands:
            commands = ["python -m pytest -o addopts= -q"]
        job.task = dict(job.task or {})
        job.task["test_commands"] = commands
        self._ensure_env(job)
        baseline = self._run_tests(job, label="baseline")
        job.task["baseline"] = baseline
        self._emit(
            job,
            {
                "step": "baseline_tests",
                **{k: baseline.get(k) for k in ("ok", "returncode", "command")},
                "note": "pre-existing failures are not counted as agent failures",
            },
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
        self._emit(job, {"step": "implementing", "backend": self.name})
        result = self._run_agent(job, prompt)
        self.last_cost = result.get("cost")
        self.last_steps = result.get("steps")
        self._emit(
            job,
            {
                "step": "agent_finished",
                "exit_status": result.get("exit_status"),
                "steps": result.get("steps"),
                "cost": result.get("cost"),
            },
        )

    def test(self, job: ContributionJob) -> None:
        result = self._run_tests(job, label="tests")
        job.test_result = result
        self._emit(
            job,
            {
                "step": "tests",
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
                "command": result.get("command"),
            },
        )

    def iterate(self, job: ContributionJob) -> None:
        if job.test_result and job.test_result.get("ok"):
            return
        self._retry(job, label="iteration_1", step_limit=12)
        if job.test_result and job.test_result.get("ok"):
            return
        self._retry(job, label="iteration_2", step_limit=8)

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        sandbox = _require_sandbox(job)
        diff = _git_diff(sandbox)
        files = _diff_files(diff)
        tests = job.test_result or {}
        structured = _structured(job)
        title = ""
        if structured:
            task_text = structured.task
            for sep in ("：", ": "):
                if sep in task_text:
                    task_text = task_text.split(sep, 1)[-1]
                    break
            if structured.issue_number is not None:
                title = f"Fix {task_text} (#{structured.issue_number})"
            else:
                title = task_text[:72]
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
        self._emit(
            job,
            {"step": "produce_patch", "files": files, "diff_bytes": len(diff)},
        )
        self._cleanup_env()
        return artifact

    def _retry(self, job: ContributionJob, *, label: str, step_limit: int) -> None:
        log = str((job.test_result or {}).get("log") or "")[-2000:]
        structured = _structured(job)
        prompt = (
            "The tests failed after the previous attempt. Fix the remaining "
            "failures without unrelated edits.\n"
            f"{structured.to_prompt() if structured else ''}\n\nTEST OUTPUT:\n{log}"
        )
        self._emit(job, {"step": label, "reason": "tests failed"})
        self._run_agent(job, prompt, step_limit=step_limit)
        result = self._run_tests(job, label=f"tests_after_{label}")
        job.test_result = result
        self._emit(
            job,
            {
                "step": f"{label}_tests",
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
            },
        )

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
        from minisweagent.models.litellm_model import LitellmModel

        env = self._ensure_env(job)
        traced = _TracingEnv(env, job, self._emit)
        model_name, model_kwargs = _model_setup()
        work = Path(job.work_dir) if job.work_dir else Path(job.sandbox_path or ".")
        agent = DefaultAgent(
            LitellmModel(
                model_name=model_name,
                model_kwargs=model_kwargs,
                cost_tracking="ignore_errors",
                format_error_template=_FORMAT_ERROR,
            ),
            traced,
            system_template=_SYSTEM,
            instance_template=_INSTANCE,
            step_limit=step_limit,
            cost_limit=8.0,
            wall_time_limit_seconds=AGENT_TIMEOUT_S,
            output_path=work / "mini-swe-trace.json",
        )
        result = agent.run(prompt)
        extra = result if isinstance(result, dict) else {}
        return {
            "exit_status": extra.get("exit_status")
            or extra.get("info", {}).get("exit_status"),
            "steps": getattr(agent, "n_calls", None),
            "cost": getattr(agent, "cost", None),
            "raw": extra,
        }

    def _ensure_env(self, job: ContributionJob) -> Any:
        if self._env is not None:
            return self._env
        if self.agent_factory is not None:
            # CI / fake agent: do not import minisweagent.
            self._install_on_host(job)
            return None
        sandbox = _require_sandbox(job)
        if self.use_docker:
            from minisweagent.environments.docker import DockerEnvironment

            self.last_network_note = {
                "network_enabled": "during dependency install only",
                "why": "pip install of the cloned repo plus pytest",
            }
            self._env = DockerEnvironment(
                image=DEFAULT_IMAGE,
                cwd="/work",
                env=sandbox_env_for_container(),
                forward_env=[],
                run_args=["--rm", "-v", f"{sandbox.resolve()}:/work"],
                timeout=TEST_TIMEOUT_S,
            )
            self.container_id = self._env.container_id
            self._install_in_container(job)
            self._disconnect_network()
        else:
            from minisweagent.environments.local import LocalEnvironment

            self.last_network_note = {
                "network_enabled": "host pip install",
                "why": "docker not used (tests or operator override)",
            }
            bindir = str(Path(sys.executable).parent)
            host_path = os.environ.get("PATH", "/usr/bin:/bin")
            path = (
                host_path
                if bindir in host_path.split(os.pathsep)
                else os.pathsep.join([bindir, host_path])
            )
            self._env = LocalEnvironment(
                cwd=str(sandbox),
                env={
                    **sandbox_env_for_container(),
                    "PATH": path,
                },
                timeout=TEST_TIMEOUT_S,
            )
            self._install_on_host(job)
        return self._env

    def _install_in_container(self, job: ContributionJob) -> None:
        if not self.container_id:
            return
        extras = "pytest pytest-asyncio"
        cmd = (
            "python -m pip install -q --upgrade pip && "
            f"python -m pip install -q -e . {extras}"
        )
        proc = subprocess.run(
            ["docker", "exec", "-w", "/work", self.container_id, "bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
        )
        self._emit(
            job,
            {
                "step": "install",
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "network": self.last_network_note,
                "log": (proc.stdout + proc.stderr)[-1500:],
            },
        )
        if proc.returncode != 0:
            raise ContributionError(
                f"sandbox pip install failed: {(proc.stderr or proc.stdout)[-400:]}"
            )

    def _install_on_host(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        if (
            not (sandbox / "pyproject.toml").exists()
            and not (sandbox / "setup.py").exists()
        ):
            self._emit(job, {"step": "install", "ok": True, "skipped": "no pyproject"})
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
        self._emit(
            job,
            {
                "step": "install",
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "network": self.last_network_note,
            },
        )

    def _disconnect_network(self) -> None:
        if not self.container_id:
            return
        subprocess.run(
            ["docker", "network", "disconnect", "bridge", self.container_id],
            capture_output=True,
            check=False,
        )

    def _cleanup_env(self) -> None:
        env = self._env
        self._env = None
        self.container_id = None
        if env is None:
            return
        closer = getattr(env, "cleanup", None)
        if callable(closer):
            try:
                closer()
            except (OSError, RuntimeError, TypeError):
                pass

    def _run_tests(self, job: ContributionJob, *, label: str) -> dict[str, Any]:
        commands = list(
            (job.task or {}).get("test_commands") or ["python -m pytest -o addopts= -q"]
        )
        command = commands[0]
        if self._env is not None:
            try:
                out = self._env.execute({"command": command}, timeout=TEST_TIMEOUT_S)
            except (OSError, RuntimeError, TypeError, ValueError, TimeoutError) as exc:
                return {
                    "ok": False,
                    "returncode": -1,
                    "command": command,
                    "log": f"{type(exc).__name__}: {exc}",
                    "label": label,
                }
            log = str(out.get("output") or "")
            code = int(out.get("returncode") or 0)
            return {
                "ok": code == 0,
                "returncode": code,
                "command": command,
                "log": log[-8000:],
                "label": label,
            }
        sandbox = _require_sandbox(job)
        env = git_env_without_tokens()
        bindir = str(Path(sys.executable).parent)
        path = env.get("PATH", "")
        if bindir not in path.split(os.pathsep):
            env["PATH"] = os.pathsep.join([bindir, path])
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_S,
            check=False,
            env=env,
        )
        log = (proc.stdout or "") + (proc.stderr or "")
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "command": command,
            "log": log[-8000:],
            "label": label,
        }


class _TracingEnv:
    """Forward execute() to the real env and record command/result on the job."""

    def __init__(
        self,
        inner: Any,
        job: ContributionJob,
        emit: Callable[[ContributionJob, dict[str, Any]], None],
    ) -> None:
        self._inner = inner
        self._job = job
        self._emit = emit
        self._n = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def execute(self, action: dict, **kwargs: Any) -> dict[str, Any]:
        self._n += 1
        command = str(action.get("command") or "")
        self._emit(
            self._job,
            {
                "step": "agent_action",
                "n": self._n,
                "command": command[:800],
            },
        )
        try:
            out = self._inner.execute(action, **kwargs)
        except (OSError, RuntimeError, TypeError, ValueError, TimeoutError) as exc:
            self._emit(
                self._job,
                {
                    "step": "agent_result",
                    "n": self._n,
                    "ok": False,
                    "error": type(exc).__name__,
                },
            )
            raise
        except BaseException as exc:
            self._emit(
                self._job,
                {
                    "step": "agent_result",
                    "n": self._n,
                    "ok": type(exc).__name__ in {"Submitted", "InterruptAgentFlow"},
                    "error": type(exc).__name__,
                },
            )
            raise
        log = str(out.get("output") or "")
        self._emit(
            self._job,
            {
                "step": "agent_result",
                "n": self._n,
                "returncode": out.get("returncode"),
                "output": log[-800:],
            },
        )
        return out


def _model_setup() -> tuple[str, dict[str, Any]]:
    name = (
        os.environ.get("MSWEA_MODEL_NAME")
        or os.environ.get("FORESHADOW_MINISWE_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or "anthropic/claude-sonnet-4-5"
    )
    kwargs: dict[str, Any] = {"drop_params": True}
    base = os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get(
        "FORESHADOW_MINISWE_API_BASE"
    )
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = key
    if base and "deepseek.com" in base:
        # DeepSeek's Anthropic-compat endpoint rejects custom tools (only
        # web_search). mini-SWE needs a bash tool, so use OpenAI-compat.
        core = name.split("/", 1)[-1]
        name = f"openai/{core}"
        kwargs["api_base"] = "https://api.deepseek.com"
        if key:
            kwargs["api_key"] = key
    elif base:
        kwargs["api_base"] = base
        if "/" not in name:
            name = f"anthropic/{name}"
    return name, kwargs


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
    extra = "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n*.egg-info/\n"
    if not ignore.exists():
        ignore.write_text(extra, encoding="utf-8")
    else:
        text = ignore.read_text(encoding="utf-8")
        if "*.egg-info/" not in text:
            ignore.write_text(text.rstrip() + "\n" + extra, encoding="utf-8")
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
    extra = "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n*.egg-info/\n"
    if not ignore.exists():
        ignore.write_text(extra, encoding="utf-8")
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
Every response MUST include reasoning text and at least one bash tool call.
Do not push. Do not use the gh CLI. Do not read host secrets or SSH keys.
Do not print environment variables.
When the acceptance criteria are met, run exactly:
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
Do not combine that command with any other command.
"""

_INSTANCE = """Please solve this issue:

{{task}}

Work in the current directory. Edit source, add a regression test if one is
missing, and run the listed test commands.

<system_information>
{{system}} {{release}} {{version}} {{machine}}
</system_information>
"""

_FORMAT_ERROR = """Tool call error:

<error>
{{error}}
</error>

Every response needs to use the bash tool at least once.
Call bash with {"command": "your_command_here"}.
To finish, run: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
"""
