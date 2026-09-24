"""Read-only navigation to an enrolled checkout. Never mutates Git."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from foreshadow.cli import app

ROOT = Path(__file__).resolve().parents[1]
CFO = ROOT / "contrib" / "zsh" / "cfo.zsh"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _checkout(workspace, name="project"):
    repo = workspace / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    return repo


def _enroll(runner, workspace, upstream, path):
    result = runner.invoke(
        app,
        [
            "repos",
            "enroll",
            upstream,
            "--workspace-root",
            str(workspace),
            "--path",
            path,
        ],
    )
    assert result.exit_code == 0, result.output
    return result


def test_path_accepts_canonical_and_unique_short_name(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace, "ripwire")
    _git(repo, "remote", "add", "origin", "git@github.com:me/ripwire.git")
    runner = CliRunner()
    _enroll(runner, workspace, "redhat-et/ripwire", "ripwire")

    for query in ("redhat-et/ripwire", "RedHat-ET/Ripwire", "ripwire", "RIPWIRE"):
        result = runner.invoke(app, ["repos", "path", query])
        assert result.exit_code == 0, (query, result.output)
        assert result.stdout == f"{repo.resolve()}\n"
        assert result.stderr == ""


def test_nested_name_resolves_and_short_name_is_ambiguous(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    core = _checkout(workspace, "moonbitlang/core")
    other = _checkout(workspace, "other/core")
    runner = CliRunner()
    _enroll(runner, workspace, "moonbitlang/core", "moonbitlang/core")
    _enroll(runner, workspace, "other/core", "other/core")

    exact = runner.invoke(app, ["repos", "path", "moonbitlang/core"])
    assert exact.exit_code == 0, exact.output
    assert exact.stdout == f"{core.resolve()}\n"
    assert exact.stderr == ""

    ambiguous = runner.invoke(app, ["repos", "path", "core"])
    assert ambiguous.exit_code != 0
    assert ambiguous.stdout == ""
    assert "ambiguous" in ambiguous.stderr.lower()
    assert "moonbitlang/core" in ambiguous.stderr and "other/core" in ambiguous.stderr
    assert other.is_dir()


def test_missing_remote_only_and_invalid_directory_fail(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    (workspace / "notes").write_text("not a repo")
    runner = CliRunner()
    _enroll(runner, workspace, "acme/missing", "missing")
    assert runner.invoke(app, ["repos", "enroll", "acme/remote"]).exit_code == 0
    (tmp_home / "repositories.toml").write_text(
        (tmp_home / "repositories.toml").read_text()
        + '[[repository]]\nupstream = "acme/notes"\npath = "notes"\n'
    )

    missing = runner.invoke(app, ["repos", "path", "acme/missing"])
    remote = runner.invoke(app, ["repos", "path", "acme/remote"])
    notes = runner.invoke(app, ["repos", "path", "acme/notes"])
    unknown = runner.invoke(app, ["repos", "path", "nope"])
    for result in (missing, remote, notes, unknown):
        assert result.exit_code != 0
        assert result.stdout == ""
        assert result.stderr.strip()
    assert "missing" in missing.stderr.lower()
    assert "remote-only" in remote.stderr.lower()
    assert "invalid" in notes.stderr.lower()


def test_unsafe_symlink_and_traversal_are_rejected(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    (workspace / "loop").symlink_to("loop", target_is_directory=True)
    root = str(workspace).replace("\\", "\\\\")
    (tmp_home / "repositories.toml").write_text(
        f'version = 1\nworkspace_root = "{root}"\n\n'
        '[[repository]]\nupstream = "acme/escape"\npath = "escape"\n\n'
        '[[repository]]\nupstream = "acme/loop"\npath = "loop"\n\n'
        '[[repository]]\nupstream = "acme/up"\npath = "../outside"\n'
    )
    runner = CliRunner()
    for query in ("acme/escape", "escape", "acme/loop", "acme/up"):
        result = runner.invoke(app, ["repos", "path", query])
        assert result.exit_code != 0, (query, result.output)
        assert result.stdout == ""
        assert any(
            phrase in result.stderr.lower()
            for phrase in ("escapes", "traversal", "invalid path")
        )


def test_unverified_fork_is_navigable_without_remote_changes(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace)
    _git(repo, "remote", "add", "origin", "git@github.com:me/project.git")
    runner = CliRunner()
    _enroll(runner, workspace, "acme/project", "project")
    before = (repo / ".git" / "config").read_bytes()
    calls = []
    real = subprocess.run

    def record(argv, *args, **kwargs):
        calls.append(list(argv))
        return real(argv, *args, **kwargs)

    subprocess.run = record
    try:
        result = runner.invoke(app, ["repos", "path", "project"])
    finally:
        subprocess.run = real
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{repo.resolve()}\n"
    assert (repo / ".git" / "config").read_bytes() == before
    git_calls = [cmd for cmd in calls if cmd and cmd[0] == "git"]
    assert git_calls
    assert all(cmd[1:4] == ["-C", str(repo), "rev-parse"] for cmd in git_calls)


def test_cfo_relative_source_still_resolves_after_cd(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace, "ripwire")
    runner = CliRunner()
    _enroll(runner, workspace, "redhat-et/ripwire", "ripwire")
    env = os.environ.copy()
    env["FORESHADOW_HOME"] = str(tmp_home)
    result = subprocess.run(
        [
            "zsh",
            "-f",
            "-c",
            (
                "source contrib/zsh/cfo.zsh\n"
                "cfo ripwire\n"
                "cfo nope || lookup_status=$?\n"
                'print -r -- "AFTER:$PWD"\n'
                'print -r -- "STATUS:${lookup_status:-0}"\n'
            ),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "not enrolled: nope" in result.stderr
    assert "cannot find" not in result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == f"AFTER:{repo.resolve()}"
    assert lines[1] != "STATUS:0"


def test_cfo_enters_nested_path_with_spaces_and_stays_on_failure(tmp_home, tmp_path):
    workspace = tmp_path / "open source"
    repo = _checkout(workspace, "moonbitlang/core")
    _git(repo, "remote", "add", "origin", "git@github.com:moonbitlang/core.git")
    runner = CliRunner()
    _enroll(runner, workspace, "moonbitlang/core", "moonbitlang/core")
    stay = tmp_path / "stay here"
    stay.mkdir()
    env = os.environ.copy()
    env["FORESHADOW_HOME"] = str(tmp_home)

    def run(script: str):
        return subprocess.run(
            ["zsh", "-f", "-c", script],
            cwd=stay,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    quoted_script = str(CFO)
    quoted_stay = str(stay)
    success = run(
        "source "
        + _zsh_quote(quoted_script)
        + "\n"
        + "cfo moonbitlang/core\n"
        + 'print -r -- "NOW:$PWD"\n'
        + "cfo definitely-missing || lookup_status=$?\n"
        + 'print -r -- "AFTER:$PWD"\n'
        + 'print -r -- "STATUS:${lookup_status:-0}"\n'
    )
    assert success.returncode == 0, success.stderr
    lines = success.stdout.splitlines()
    assert lines[0] == f"NOW:{repo.resolve()}"
    assert lines[1] == f"AFTER:{repo.resolve()}"
    assert lines[2] != "STATUS:0"
    assert (
        "definitely-missing" in success.stderr.lower()
        or "not enrolled" in success.stderr.lower()
    )

    failure = run(
        "cd "
        + _zsh_quote(quoted_stay)
        + "\n"
        + "source "
        + _zsh_quote(quoted_script)
        + "\n"
        + "cfo nope || true\n"
        + 'print -r -- "STAY:$PWD"\n'
    )
    assert failure.returncode == 0, failure.stderr
    assert failure.stdout.strip() == f"STAY:{stay.resolve()}"


def _zsh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
