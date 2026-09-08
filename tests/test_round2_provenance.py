import subprocess

import pytest

from foreshadow.contribution.executor import (
    ContributionError,
    ContributionJob,
    PatchArtifact,
)
from foreshadow.contribution.mini_swe import MiniSweExecutor
from foreshadow.contribution.package import build_package


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True)


def repository(tmp_path):
    p = tmp_path / "source"
    p.mkdir()
    git(p, "init")
    git(p, "config", "user.email", "test@example.org")
    git(p, "config", "user.name", "Test")
    (p / "file.txt").write_text("baseline\n")
    git(p, "add", ".")
    git(p, "commit", "-m", "baseline")
    return p


def test_dirty_source_cannot_be_laundered_into_autonomous_baseline(tmp_path):
    source = repository(tmp_path)
    (source / "file.txt").write_text("preexisting patch\n")
    job = ContributionJob(
        full_name="test/repo", source_dir=source, work_dir=tmp_path / "run"
    )
    executor = MiniSweExecutor(agent_factory=lambda **kw: None, docker=False)
    with pytest.raises(ContributionError, match="PREEXISTING_WORKTREE_CONTAMINATION"):
        executor.prepare(job)


def test_clean_source_preserves_upstream_commit(tmp_path):
    source = repository(tmp_path)
    head = git(source, "rev-parse", "HEAD").strip()
    job = ContributionJob(
        full_name="test/repo", source_dir=source, work_dir=tmp_path / "run"
    )
    MiniSweExecutor(agent_factory=lambda **kw: None, docker=False).prepare(job)
    assert git(job.sandbox_path, "rev-parse", "HEAD").strip() == head
    assert git(job.sandbox_path, "status", "--porcelain") == ""


def test_existing_workspace_package_does_not_claim_autonomous():
    job = ContributionJob(full_name="test/repo", backend="workspace")
    package = build_package(
        job, PatchArtifact(diff="patch", tests_passed=True, qa_ok=True)
    )
    assert package["implementation"]["mode"] == "existing_worktree"
    assert package["implementation"]["capability"] == "EXISTING_WORKTREE_VALIDATED"
    assert package["status"] == "WAITING_USER_APPROVAL"


def test_provenance_records_clean_tree_and_executor_window(tmp_path):
    from foreshadow.contribution.provenance import begin, finish

    source = repository(tmp_path)
    job = ContributionJob(
        full_name="test/repo", backend="mini_swe_agent", sandbox_path=source
    )
    begin(job)
    (source / "new.txt").write_text("executor output\n")
    finish(job)
    proof = job.task["implementation"]
    assert proof["pre_status"] == ""
    assert proof["clean_before"] is True
    assert len(proof["pre_tree_hash"]) == 40
    assert proof["executor_started"] <= proof["executor_finished"]
    assert "+executor output" in proof["post_diff"]
    assert "new.txt" in proof["diff_stat"]


@pytest.mark.parametrize("status", ["ready", "waiting_approval"])
def test_internal_ready_has_one_user_state(status):
    from foreshadow.board.server import _job_view

    job = ContributionJob(full_name="test/repo", status=status)
    assert _job_view(job)["status"] == "WAITING_USER_APPROVAL"


@pytest.mark.parametrize(
    "layout,kind",
    [
        (["go.mod"], "go"),
        (["package.json"], "node"),
        (["go.mod", "docs/package.json"], "go"),
        (["go.mod", "package.json"], "go"),
    ],
)
def test_primary_toolchain_is_not_overridden_by_frontend_files(tmp_path, layout, kind):
    from foreshadow.mission import detect_local_tests

    for name in layout:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}" if name.endswith(".json") else "module example.org/test\n")
    assert detect_local_tests(tmp_path)["kind"] == kind


def test_packaging_includes_new_files_without_inventing_ignore_file(tmp_path):
    from foreshadow.contribution.mini_swe import _git_diff

    source = repository(tmp_path)
    (source / "new.txt").write_text("new content\n")
    diff = _git_diff(source)
    assert "+new content" in diff
    assert ".gitignore" not in diff
    assert not (source / ".gitignore").exists()


def test_missing_coding_backend_never_silently_selects_existing_workspace(monkeypatch):
    from foreshadow.contribution.local import _default_backend

    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    assert _default_backend() == "mini_swe_agent"
