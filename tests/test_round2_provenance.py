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


def test_executor_runs_every_configured_test_and_records_each_result(tmp_path):
    job = ContributionJob(
        full_name="test/repo",
        sandbox_path=tmp_path,
        task={"test_commands": ["printf first", "exit 7"]},
    )
    executor = MiniSweExecutor(agent_factory=lambda **kw: None, docker=False)
    result = executor._run_tests(job, label="tests")
    assert result["ok"] is False
    assert [r["returncode"] for r in result["commands"]] == [0, 7]
    assert all(r["duration_s"] >= 0 for r in result["commands"])


def test_real_executor_cannot_fall_back_to_unisolated_host(monkeypatch):
    monkeypatch.setattr("foreshadow.contribution.mini_swe._require", lambda: None)
    monkeypatch.setattr("foreshadow.contribution.mini_swe.shutil.which", lambda _: None)
    with pytest.raises(ContributionError, match="Docker"):
        MiniSweExecutor()


def test_go_root_selects_golang_image_not_python(tmp_path, monkeypatch):
    from foreshadow.contribution.mini_swe import _image_for

    monkeypatch.delenv("FORESHADOW_SANDBOX_IMAGE", raising=False)
    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "go.mod").write_text("module example.org/x\ngo 1.25\n")
    (sandbox / "package.json").write_text("{}\n")
    image = _image_for(sandbox)
    assert image.startswith("golang:")
    assert "python" not in image


def test_python_root_keeps_default_python_image(tmp_path, monkeypatch):
    from foreshadow.contribution.mini_swe import DEFAULT_IMAGE, _image_for

    monkeypatch.delenv("FORESHADOW_SANDBOX_IMAGE", raising=False)
    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "pyproject.toml").write_text("[project]\nname='x'\n")
    assert _image_for(sandbox) == DEFAULT_IMAGE
    assert "slim-bookworm" in _image_for(sandbox)


def test_go_sandbox_install_is_not_pip(tmp_path):
    from foreshadow.contribution.mini_swe import _install_command

    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "go.mod").write_text("module example.org/x\ngo 1.25\n")
    command = _install_command(sandbox)
    assert "pip" not in command
    assert "go mod download" in command


def test_go_sandbox_install_drops_root_and_adds_repo_cli_tools(tmp_path):
    from foreshadow.contribution.mini_swe import SANDBOX_USER, _install_command

    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "go.mod").write_text("module example.org/x\ngo 1.25\n")
    command = _install_command(sandbox)
    assert "chown" in command
    assert SANDBOX_USER in command
    assert "chmod" in command
    assert "apt-get" not in command
    assert "useradd" not in command
    # Bind-mount .git objects may reject chown; install must not hard-fail on that.
    assert "|| true" in command or "2>/dev/null" in command


def test_go_runtime_image_is_baked_with_cli_tools_and_non_root_user(tmp_path, monkeypatch):
    from foreshadow.contribution.mini_swe import (
        GO_IMAGE,
        GO_RUNTIME_IMAGE,
        SANDBOX_USER,
        _go_runtime_dockerfile,
        _runtime_image_for,
    )

    df = _go_runtime_dockerfile()
    assert f"FROM {GO_IMAGE}" in df
    assert "sqlite3" in df
    assert "zstd" in df
    assert "useradd" in df
    assert SANDBOX_USER in df
    monkeypatch.delenv("FORESHADOW_SANDBOX_IMAGE", raising=False)
    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "go.mod").write_text("module example.org/x\ngo 1.25\n")
    assert _runtime_image_for(sandbox) == GO_RUNTIME_IMAGE


def test_go_runtime_interpreter_is_non_root():
    from foreshadow.contribution.mini_swe import SANDBOX_USER, _runtime_interpreter

    go = _runtime_interpreter(go=True)
    assert go[0] == "su"
    assert SANDBOX_USER in go
    assert "-c" in go
    assert "-p" in go
    assert _runtime_interpreter(go=False) == ["bash", "-lc"]


def test_go_docker_run_args_bind_work_without_tmpfs(tmp_path):
    from foreshadow.contribution.mini_swe import _docker_run_args

    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    args = _docker_run_args(sandbox, go=True)
    joined = " ".join(args)
    assert "--tmpfs" not in joined
    assert str(sandbox.resolve()) in joined
    assert "/work" in joined


def test_python_sandbox_install_still_uses_pip(tmp_path):
    from foreshadow.contribution.mini_swe import _install_command

    sandbox = tmp_path / "repo"
    sandbox.mkdir()
    (sandbox / "pyproject.toml").write_text("[project]\nname='x'\n")
    command = _install_command(sandbox)
    assert "pip install" in command


def test_contribution_work_dir_is_mission_scoped(tmp_path):
    from foreshadow.contribution.local import _contrib_work_dir

    first = _contrib_work_dir(tmp_path, "vshulcz/deja-vu", mission_id=1)
    second = _contrib_work_dir(tmp_path, "vshulcz/deja-vu", mission_id=3)
    assert first != second
    assert first.name.endswith("__m1")
    assert second.name.endswith("__m3")
    assert "vshulcz__deja-vu" in first.name


def test_go_container_install_exec_uses_non_login_shell_and_go_path():
    from foreshadow.contribution.mini_swe import _docker_exec_argv

    argv = _docker_exec_argv("abc123", "go mod download", go=True)
    assert argv[:3] == ["docker", "exec", "-w"]
    assert "bash" in argv
    assert "-lc" not in argv
    env_flags = [argv[i + 1] for i, item in enumerate(argv) if item == "-e"]
    assert any(item.startswith("PATH=") and "/usr/local/go/bin" in item for item in env_flags)
    assert argv[-2] == "-c"
    assert argv[-3] == "bash"


def test_go_sandbox_path_includes_official_go_bin():
    from foreshadow.contribution.mini_swe import sandbox_env_for_container

    env = sandbox_env_for_container(go=True)
    assert "/usr/local/go/bin" in env["PATH"].split(":")
    assert "GOPROXY" in env
    py = sandbox_env_for_container()
    assert "/usr/local/go/bin" not in py["PATH"].split(":")


def test_go_suite_skips_overlay_mtime_memo_test_when_present(tmp_path):
    from foreshadow.contribution.local import go_test_commands

    repo = tmp_path / "repo"
    (repo / "internal" / "sources").mkdir(parents=True)
    (repo / "internal" / "index").mkdir(parents=True)
    (repo / "go.mod").write_text("module example.org/x\ngo 1.25\n")
    plain = go_test_commands(repo)
    assert plain[0] == "go test ./... -count=1"
    assert "go vet ./..." in plain
    (repo / "internal" / "sources" / "notes_memo_test.go").write_text("package sources\n")
    (repo / "internal" / "index" / "damaged_manifest_test.go").write_text("package index\n")
    (repo / "internal" / "index" / "version_upgrade_test.go").write_text("package index\n")
    skipped = go_test_commands(repo)
    assert "-skip" in skipped[0]
    assert "'TestTheNotesFileIsParsedOncePerProcess|TestDamagedUnreadableManifest|TestIsCurrentVersionDetectsOlderStore'" in skipped[0]


def test_go_full_suite_timeout_exceeds_default_python_budget():
    from foreshadow.contribution.mini_swe import TEST_TIMEOUT_S, _test_timeout_s

    assert _test_timeout_s("python -m pytest -q") == TEST_TIMEOUT_S
    assert _test_timeout_s("go test ./internal/index -count=1") > TEST_TIMEOUT_S
    assert _test_timeout_s("go test ./... -count=1") >= 600
    assert _test_timeout_s("go vet ./...") >= 300
