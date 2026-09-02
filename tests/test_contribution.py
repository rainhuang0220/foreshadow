from __future__ import annotations

import inspect
import shutil
import subprocess
from pathlib import Path

import pytest

from foreshadow.contribution.executor import (
    BackendNotInstalled,
    ContributionExecutor,
    ContributionJob,
    JobStatus,
    PatchArtifact,
    get_executor,
    refuse_remote,
    run_contribution,
)
from foreshadow.contribution.jobs import list_artifacts, load_job
from foreshadow.contribution.native import (
    NativeExecutor,
    docker_run_argv,
    sandbox_env,
    write_fixture_repo,
)
from foreshadow.contribution.qa import gate
from foreshadow.db import connect, migrate
from foreshadow.mission import REMOTE_ACTIONS

CONTRIB = Path(__file__).resolve().parents[1] / "src" / "foreshadow" / "contribution"


def _local_user(tmp_home: Path) -> tuple:
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    return conn, uid


def test_native_is_contribution_executor():
    executor = NativeExecutor()
    assert isinstance(executor, ContributionExecutor)
    assert executor.name == "native"
    assert get_executor("native").name == "native"


def test_native_happy_path_fixture_bug_to_ready(tmp_home, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.setenv("GH_TOKEN", "gho_other_secret")
    monkeypatch.delenv("FORESHADOW_SANDBOX", raising=False)
    conn, uid = _local_user(tmp_home)
    src = write_fixture_repo(tmp_path / "src")
    job = ContributionJob(
        user_id=uid,
        full_name="acme/toy",
        task={
            "prompt": "Fix add() so it returns a + b",
            "why": "test_add fails because add() subtracts",
        },
        source_dir=src,
        work_dir=tmp_path / "work",
    )
    executor = NativeExecutor()
    artifact = run_contribution(job, executor=executor, conn=conn)
    assert job.status is JobStatus.ready
    assert artifact.tests_passed is True
    assert artifact.qa_ok is True
    assert artifact.diff.strip()
    assert "return a + b" in artifact.diff
    assert "return a - b" in artifact.diff
    assert artifact.why
    cfg = (Path(job.sandbox_path) / ".git" / "config").read_text(encoding="utf-8")
    assert "hooksPath" in cfg
    assert "/dev/null" in cfg
    env = executor.last_sandbox_env or {}
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "ghp_testtoken_not_a_real_secret" not in " ".join(env.values())
    stored = load_job(conn, job.id, user_id=uid)
    assert stored is not None
    assert stored.status is JobStatus.ready
    assert stored.backend == "native"
    kinds = {row["kind"] for row in list_artifacts(conn, job.id)}
    assert {"diff", "test_log", "qa"} <= kinds
    bodies = [row["body"] or "" for row in list_artifacts(conn, job.id)]
    assert any("return a + b" in body for body in bodies)


def test_quality_gate_rejects_empty_diff():
    job = ContributionJob(
        full_name="acme/toy",
        task={"prompt": "Fix add()", "why": "tests fail on add()"},
    )
    artifact = PatchArtifact(
        diff="",
        why="tests fail on add()",
        tests_passed=True,
        files=[],
    )
    result = gate(job, artifact)
    assert result.ok is False
    assert any("empty" in reason for reason in result.reasons)


def test_quality_gate_rejects_readme_space_spam():
    job = ContributionJob(
        full_name="acme/toy",
        task={"prompt": "add a space in README", "why": "formatting"},
    )
    diff = (
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-# toy\n"
        "+# toy \n"
    )
    artifact = PatchArtifact(
        diff=diff,
        why="formatting",
        tests_passed=True,
        files=["README.md"],
    )
    result = gate(job, artifact)
    assert result.ok is False
    assert result.reasons


def test_remote_write_refused():
    for action in sorted(REMOTE_ACTIONS | {"git_push", "push_branch"}):
        out = refuse_remote(action)
        assert out["blocked"] is True
        assert out["ok"] is False
        assert out["status"] == JobStatus.refused_remote.value
        assert "远程" in out["error"]


def test_token_not_in_sandbox_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.setenv("GH_TOKEN", "gho_other_secret")
    monkeypatch.setenv("GH_HOST", "github.example")
    env = sandbox_env(home=tmp_path / "home")
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GH_HOST"):
        assert key not in env
    blob = " ".join(env.values())
    assert "ghp_testtoken_not_a_real_secret" not in blob
    assert "gho_other_secret" not in blob
    argv = docker_run_argv(tmp_path / "repo", ["python", "-m", "pytest"])
    joined = " ".join(argv)
    assert "--network=none" in argv
    assert "--rm" in argv
    assert "GITHUB_TOKEN" not in joined
    assert "GH_TOKEN" not in joined
    assert "docker.sock" not in joined
    assert "ghp_testtoken_not_a_real_secret" not in joined


def test_openhands_stub_errors_if_missing(monkeypatch):
    from foreshadow.contribution import openhands as mod

    monkeypatch.setattr(mod, "_extra_available", lambda: False)
    with pytest.raises(BackendNotInstalled, match="not installed"):
        mod.OpenHandsExecutor()


def test_mini_swe_stub_errors_if_missing(monkeypatch):
    from foreshadow.contribution import mini_swe as mod

    monkeypatch.setattr(mod, "_extra_available", lambda: False)
    with pytest.raises(BackendNotInstalled, match="not installed"):
        mod.MiniSweExecutor()


def test_contribution_package_never_mutates_github():
    from foreshadow.contribution.native import _git

    for path in sorted(CONTRIB.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "api.github.com" not in text
        assert "GitHubClient" not in text
        assert "ghp_" not in text
        assert "create_pr" not in text
    assert "create_pr" not in inspect.getsource(NativeExecutor)
    git_src = inspect.getsource(_git)
    assert '"push"' in git_src
    assert "RemoteWriteRefused" in git_src


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_docker_sandbox_optional(tmp_path, monkeypatch):
    inspect = subprocess.run(
        ["docker", "image", "inspect", "python:3.12-alpine"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode != 0:
        pytest.skip("python:3.12-alpine image not present")
    monkeypatch.setenv("FORESHADOW_SANDBOX", "docker")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    src = write_fixture_repo(tmp_path / "src")
    job = ContributionJob(
        full_name="acme/toy",
        task={
            "prompt": "Fix add() so it returns a + b",
            "why": "test_add fails because add() subtracts",
        },
        source_dir=src,
        work_dir=tmp_path / "work",
    )
    executor = NativeExecutor()
    try:
        artifact = run_contribution(job, executor=executor)
    except Exception as exc:
        msg = str(exc).lower()
        if "cannot connect" in msg or "docker daemon" in msg:
            pytest.skip(str(exc))
        raise
    log = (artifact.test_log or "").lower()
    if "cannot connect" in log or "docker daemon" in log:
        pytest.skip(artifact.test_log)
    argv = executor.last_test_argv or []
    assert "--network=none" in argv
    assert "GITHUB_TOKEN" not in argv
    assert job.status is JobStatus.ready
    assert artifact.tests_passed is True
    assert artifact.diff.strip()
