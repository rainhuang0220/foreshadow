"""Native contribution backend: isolated sandbox, tests, unified diff.

Docker when ``FORESHADOW_SANDBOX=docker`` and docker is on PATH; otherwise a
tight local temp dir (tests). GitHub tokens never enter the sandbox env.
Git hooks are disabled. The backend never pushes and never talks to GitHub.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from foreshadow.contribution.executor import (
    ContributionError,
    ContributionJob,
    PatchArtifact,
    RemoteWriteRefused,
)
from foreshadow.contribution.qa import diff_files

DOCKER_IMAGE = os.environ.get("FORESHADOW_SANDBOX_IMAGE", "python:3.12-alpine")
GIT_TIMEOUT_S = 30
TEST_TIMEOUT_S = 60
DOCKER_TIMEOUT_S = 120
_SECRET_PARTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "ASKPASS",
    "CREDENTIAL",
    "AUTHORIZATION",
    "API_KEY",
)
_ENV_KEEP = frozenset(
    {
        "PATH",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "TZ",
        "TERM",
        "TMPDIR",
        "TMP",
        "TEMP",
    }
)
_SKIP_ADD_NAMES = frozenset(
    {".env", ".git-credentials", "credentials", "secrets.txt", "id_rsa"}
)
_SKIP_DIR_NAMES = frozenset(
    {".git", "__pycache__", ".venv", "venv", "node_modules", "dist", "build"}
)

_BUGGY_TOY = "def add(a, b):\n    return a - b\n"
_TEST_TOY = "from toy import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
_README = "# toy\n\nAdd numbers.\n"

# Stdlib runner for docker images that do not ship pytest.
_STDLIB_RUNNER = r"""
from __future__ import annotations
import importlib.util
import sys
import traceback
from pathlib import Path

root = Path.cwd().resolve()
sys.path.insert(0, str(root))
failed = 0
ran = 0
paths = sorted(
    p
    for p in root.rglob("test_*.py")
    if ".git" not in p.parts and "__pycache__" not in p.parts
)
for path in paths:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        continue
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        failed += 1
        ran += 1
        traceback.print_exc()
        continue
    for name, fn in sorted(vars(mod).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        ran += 1
        try:
            fn()
            print(f"PASSED {path.name}::{name}")
        except Exception:
            failed += 1
            print(f"FAILED {path.name}::{name}")
            traceback.print_exc()
print(f"{ran - failed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
"""


def write_fixture_repo(dest: Path) -> Path:
    """Tiny Python repo: ``add()`` subtracts; ``test_add`` expects a sum."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "toy.py").write_text(_BUGGY_TOY, encoding="utf-8")
    (dest / "test_toy.py").write_text(_TEST_TOY, encoding="utf-8")
    (dest / "README.md").write_text(_README, encoding="utf-8")
    return dest


def uses_docker() -> bool:
    return (
        os.environ.get("FORESHADOW_SANDBOX") == "docker"
        and shutil.which("docker") is not None
    )


def secret_env_key(key: str) -> bool:
    upper = key.upper()
    if upper in {"GITHUB_TOKEN", "GH_TOKEN", "GH_HOST"}:
        return True
    return any(part in upper for part in _SECRET_PARTS)


def sandbox_env(*, home: Path) -> dict[str, str]:
    """Minimal env for sandbox processes. GitHub tokens never go in."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    env: dict[str, str] = {}
    for key, val in os.environ.items():
        if key not in _ENV_KEEP and not key.startswith("LC_"):
            continue
        if secret_env_key(key):
            continue
        env[key] = val
    env["HOME"] = str(home)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["http_proxy"] = "http://127.0.0.1:9"
    env["https_proxy"] = "http://127.0.0.1:9"
    env["HTTP_PROXY"] = "http://127.0.0.1:9"
    env["HTTPS_PROXY"] = "http://127.0.0.1:9"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    return env


def docker_run_argv(
    sandbox: Path,
    command: list[str],
    *,
    image: str = DOCKER_IMAGE,
    runner: Path | None = None,
) -> list[str]:
    """``docker run --network=none --rm -v sandbox:/work``. No tokens, no sock."""
    argv = [
        "docker",
        "run",
        "--network=none",
        "--rm",
        "-v",
        f"{Path(sandbox).resolve()}:/work",
        "-w",
        "/work",
        "-e",
        "HOME=/tmp",
        "-e",
        "GIT_TERMINAL_PROMPT=0",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "PYTHONNOUSERSITE=1",
        "-e",
        "GIT_CONFIG_NOSYSTEM=1",
        "-e",
        "GIT_CONFIG_GLOBAL=/dev/null",
    ]
    if runner is not None:
        argv.extend(["-v", f"{Path(runner).resolve()}:/runner.py:ro"])
    argv.append(image)
    argv.extend(command)
    return argv


class NativeExecutor:
    name = "native"

    def __init__(self) -> None:
        self.last_sandbox_env: dict[str, str] | None = None
        self.last_test_argv: list[str] | None = None

    def prepare(self, job: ContributionJob) -> None:
        work = (
            Path(job.work_dir)
            if job.work_dir
            else Path(tempfile.mkdtemp(prefix="foreshadow-sandbox-"))
        )
        work.mkdir(parents=True, exist_ok=True)
        job.work_dir = work
        sandbox = work / "repo"
        if sandbox.exists():
            shutil.rmtree(sandbox)
        if job.source_dir is not None:
            _copy_source(Path(job.source_dir), sandbox)
        elif str((job.task or {}).get("fixture") or "") == "demo_add":
            write_fixture_repo(sandbox)
        else:
            raise ContributionError(
                "native backend needs source_dir or task.fixture=demo_add"
            )
        job.sandbox_path = sandbox
        _git_init(sandbox)
        job.log.append(
            {
                "step": "prepare",
                "sandbox": str(sandbox),
                "docker": uses_docker(),
                "hooksPath": "/dev/null",
            }
        )

    def analyze(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        files = sorted(
            p.name for p in sandbox.iterdir() if p.is_file() and p.name != ".git"
        )
        job.log.append({"step": "analyze", "files": files})

    def implement(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        task = job.task or {}
        via = ""
        changed: list[str] = []
        edits = task.get("edits")
        if isinstance(edits, list) and edits:
            changed = _apply_edits(sandbox, edits)
            via = "edits"
        if not changed:
            changed = _repair_demo_add(sandbox)
            if changed:
                via = "demo_add"
        if not job.why:
            job.why = str(task.get("why") or "")
        if not job.why and changed:
            job.why = "Fix add() so it returns a sum; the fixture subtracted."
        job.log.append({"step": "implement", "via": via, "changed": changed})

    def test(self, job: ContributionJob) -> None:
        sandbox = _require_sandbox(job)
        home = (job.work_dir or sandbox.parent) / "home"
        env = sandbox_env(home=home)
        self.last_sandbox_env = dict(env)
        result = _run_tests(sandbox, env=env, work_dir=job.work_dir)
        self.last_test_argv = list(result.get("argv") or [])
        job.test_result = result
        job.log.append(
            {
                "step": "test",
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
                "docker": bool(result.get("docker")),
            }
        )

    def iterate(self, job: ContributionJob) -> None:
        if job.test_result and job.test_result.get("ok"):
            return
        sandbox = _require_sandbox(job)
        changed = _repair_demo_add(sandbox)
        job.log.append({"step": "iterate", "changed": changed})
        self.test(job)

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        sandbox = _require_sandbox(job)
        paths = _safe_relpaths(sandbox)
        if paths:
            _git(sandbox, "add", "--", *paths)
        diff_proc = _git(sandbox, "diff", "--cached", "--no-ext-diff", "HEAD")
        diff = (diff_proc.stdout or "").strip("\n") + ("\n" if diff_proc.stdout else "")
        files = diff_files(diff)
        tests = job.test_result or {}
        why = (job.why or str((job.task or {}).get("why") or "")).strip()
        title = str((job.task or {}).get("title") or "")
        if not title and files:
            title = f"Fix {files[0]}"
        artifact = PatchArtifact(
            diff=diff,
            why=why,
            test_log=str(tests.get("log") or ""),
            files=files,
            title=title,
            body=why,
            tests_passed=bool(tests.get("ok")),
        )
        job.log.append(
            {
                "step": "produce_patch",
                "files": files,
                "diff_bytes": len(diff.encode("utf-8")),
            }
        )
        return artifact


def _require_sandbox(job: ContributionJob) -> Path:
    if job.sandbox_path is None or not Path(job.sandbox_path).is_dir():
        raise ContributionError("sandbox is not prepared")
    return Path(job.sandbox_path)


def _copy_source(src: Path, dest: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git",
        "__pycache__",
        "*.pyc",
        ".venv",
        "venv",
        "node_modules",
        ".env",
    )
    shutil.copytree(src, dest, ignore=ignore, dirs_exist_ok=True)


def _git_init(sandbox: Path) -> None:
    _git(sandbox, "init", "-b", "main")
    _git(sandbox, "config", "core.hooksPath", "/dev/null")
    _git(sandbox, "config", "commit.gpgsign", "false")
    paths = _safe_relpaths(sandbox)
    if paths:
        _git(sandbox, "add", "--", *paths)
    _git(
        sandbox,
        "-c",
        "user.email=foreshadow@sandbox.local",
        "-c",
        "user.name=Foreshadow",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--allow-empty",
        "-m",
        "baseline",
    )


def _git(sandbox: Path, *args: str) -> subprocess.CompletedProcess[str]:
    verbs = [a for a in args if not a.startswith("-")]
    if "push" in verbs:
        raise RemoteWriteRefused("git push is refused")
    cmd = ["git", "-C", str(sandbox), "-c", "core.hooksPath=/dev/null", *args]
    env = sandbox_env(home=sandbox.parent / "home")
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise ContributionError("git is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ContributionError("git timed out") from exc


def _safe_relpaths(root: Path) -> list[str]:
    out: list[str] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for name in filenames:
            if name in _SKIP_ADD_NAMES or name.startswith(".env"):
                continue
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(dirpath) / name
            try:
                rel = path.resolve().relative_to(root)
            except ValueError:
                continue
            if ".git" in rel.parts:
                continue
            out.append(str(rel).replace("\\", "/"))
    return out


def _apply_edits(sandbox: Path, edits: list[Any]) -> list[str]:
    changed: list[str] = []
    root = sandbox.resolve()
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        rel = str(edit.get("path") or "")
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            continue
        path = (sandbox / rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        old = edit.get("old")
        new = edit.get("new")
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        text = path.read_text(encoding="utf-8")
        if old not in text:
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        changed.append(rel.replace("\\", "/"))
    return changed


def _repair_demo_add(sandbox: Path) -> list[str]:
    changed: list[str] = []
    for path in sandbox.rglob("*.py"):
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "return a - b" not in text:
            continue
        path.write_text(text.replace("return a - b", "return a + b"), encoding="utf-8")
        changed.append(str(path.relative_to(sandbox)).replace("\\", "/"))
    return changed


def _run_tests(
    sandbox: Path,
    *,
    env: dict[str, str],
    work_dir: Path | None,
) -> dict[str, Any]:
    if uses_docker():
        return _run_tests_docker(sandbox, work_dir=work_dir)
    return _run_tests_local(sandbox, env=env)


def _run_tests_local(sandbox: Path, *, env: dict[str, str]) -> dict[str, Any]:
    argv = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    try:
        completed = subprocess.run(
            argv,
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_S,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return _run_stdlib_local(sandbox, env=env)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "log": "pytest timed out",
            "argv": argv,
            "docker": False,
        }
    log = ((completed.stdout or "") + (completed.stderr or ""))[-8000:]
    if completed.returncode == 0:
        return {
            "ok": True,
            "returncode": 0,
            "log": log,
            "argv": argv,
            "docker": False,
        }
    if "No module named pytest" in (completed.stderr or ""):
        return _run_stdlib_local(sandbox, env=env)
    return {
        "ok": False,
        "returncode": completed.returncode,
        "log": log,
        "argv": argv,
        "docker": False,
    }


def _run_stdlib_local(sandbox: Path, *, env: dict[str, str]) -> dict[str, Any]:
    runner = sandbox.parent / "run_tests.py"
    runner.write_text(_STDLIB_RUNNER.lstrip(), encoding="utf-8")
    argv = [sys.executable, str(runner)]
    try:
        completed = subprocess.run(
            argv,
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_S,
            check=False,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": None,
            "log": str(exc),
            "argv": argv,
            "docker": False,
        }
    log = ((completed.stdout or "") + (completed.stderr or ""))[-8000:]
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "log": log,
        "argv": argv,
        "docker": False,
    }


def _run_tests_docker(sandbox: Path, *, work_dir: Path | None) -> dict[str, Any]:
    work = Path(work_dir) if work_dir is not None else sandbox.parent
    runner = work / "run_tests.py"
    runner.write_text(_STDLIB_RUNNER.lstrip(), encoding="utf-8")
    argv = docker_run_argv(sandbox, ["python", "/runner.py"], runner=runner)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ContributionError("docker is not installed") from exc
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "log": "docker timed out",
            "argv": argv,
            "docker": True,
        }
    log = ((completed.stdout or "") + (completed.stderr or ""))[-8000:]
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "log": log,
        "argv": argv,
        "docker": True,
    }
