"""The local registry is an explicit address book, never a work executor."""

from __future__ import annotations

import subprocess
import tomllib

from typer.testing import CliRunner

from foreshadow.cli import app
from foreshadow.db import connect, migrate


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _checkout(workspace, name="project"):
    repo = workspace / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    return repo


def test_enroll_list_and_validate_existing_checkout(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace)
    _git(repo, "remote", "add", "origin", "git@github.com:acme/project.git")
    runner = CliRunner()

    enrolled = runner.invoke(
        app,
        [
            "repos",
            "enroll",
            "acme/project",
            "--workspace-root",
            str(workspace),
            "--path",
            "project",
        ],
    )
    assert enrolled.exit_code == 0, enrolled.output
    data = tomllib.loads((tmp_home / "repositories.toml").read_text())
    assert data == {
        "version": 1,
        "workspace_root": str(workspace),
        "repository": [{"upstream": "acme/project", "path": "project"}],
    }
    listed = runner.invoke(app, ["repos", "list"])
    assert listed.exit_code == 0, listed.output
    assert "acme/project" in listed.output
    validated = runner.invoke(app, ["repos", "validate", "acme/project"])
    assert validated.exit_code == 0, validated.output
    assert "ok" in validated.output


def test_missing_checkout_and_remote_only_are_valid(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    runner = CliRunner()
    first = runner.invoke(
        app,
        [
            "repos",
            "enroll",
            "acme/missing",
            "--workspace-root",
            str(workspace),
            "--path",
            "missing",
        ],
    )
    second = runner.invoke(app, ["repos", "enroll", "acme/remote"])
    assert first.exit_code == second.exit_code == 0
    result = runner.invoke(app, ["repos", "validate"])
    assert result.exit_code == 0, result.output
    assert "acme/missing" in result.output and "missing" in result.output
    assert "acme/remote" in result.output and "remote-only" in result.output
    assert not (workspace / "missing").exists()


def test_rejects_traversal_absolute_and_symlink_escape(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    (workspace / "loop").symlink_to("loop", target_is_directory=True)
    runner = CliRunner()
    for path in ("../outside", str(outside), "escape", "loop"):
        result = runner.invoke(
            app,
            [
                "repos",
                "enroll",
                "acme/project",
                "--workspace-root",
                str(workspace),
                "--path",
                path,
            ],
        )
        assert result.exit_code == 2, (path, result.output)
        assert "path" in result.output.lower()
    assert not (tmp_home / "repositories.toml").exists()


def test_fork_origin_and_upstream_are_distinguished_without_writes(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace)
    _git(repo, "remote", "add", "origin", "git@github.com:me/project.git")
    _git(repo, "remote", "add", "upstream", "https://github.com/acme/project.git")
    runner = CliRunner()
    assert (
        runner.invoke(
            app,
            [
                "repos",
                "enroll",
                "acme/project",
                "--workspace-root",
                str(workspace),
                "--path",
                "project",
            ],
        ).exit_code
        == 0
    )
    before = (repo / ".git" / "config").read_bytes()
    before_status = _git(repo, "status", "--porcelain")
    result = runner.invoke(app, ["repos", "validate", "acme/project"])
    assert result.exit_code == 0, result.output
    assert "fork" in result.output and "me/project" in result.output
    assert (repo / ".git" / "config").read_bytes() == before
    assert _git(repo, "status", "--porcelain") == before_status


def test_duplicate_upstream_and_path_are_rejected(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    runner = CliRunner()
    assert (
        runner.invoke(
            app,
            [
                "repos",
                "enroll",
                "acme/project",
                "--workspace-root",
                str(workspace),
                "--path",
                "project",
            ],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["repos", "enroll", "ACME/PROJECT"]).exit_code == 2
    assert (
        runner.invoke(
            app, ["repos", "enroll", "other/project", "--path", "project"]
        ).exit_code
        == 2
    )
    assert (
        len(tomllib.loads((tmp_home / "repositories.toml").read_text())["repository"])
        == 1
    )


def test_invalid_toml_and_unsupported_version_are_reported(tmp_home):
    registry = tmp_home / "repositories.toml"
    runner = CliRunner()
    registry.write_text("version = [\n")
    assert runner.invoke(app, ["repos", "list"]).exit_code == 2
    registry.write_text('version = 2\nworkspace_root = "/tmp"\n')
    result = runner.invoke(app, ["repos", "list"])
    assert result.exit_code == 2
    assert "version" in result.output.lower()


def test_alias_uses_existing_sqlite_identity_without_creating_rows(tmp_home, tmp_path):
    db_path = tmp_home / "foreshadow.sqlite3"
    conn = connect(db_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("R_stable", "acme/new", "acme", "new", "2026-01-01", "2026-01-01"),
    )
    repo_id = conn.execute("SELECT id FROM repos WHERE node_id='R_stable'").fetchone()[
        0
    ]
    conn.execute(
        "INSERT INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?, ?, ?)",
        (repo_id, "acme/old", "2026-01-01"),
    )
    conn.commit()
    conn.close()
    workspace = tmp_path / "open-source"
    workspace.mkdir()
    runner = CliRunner()
    assert (
        runner.invoke(
            app, ["repos", "enroll", "acme/old", "--workspace-root", str(workspace)]
        ).exit_code
        == 0
    )
    saved = tomllib.loads((tmp_home / "repositories.toml").read_text())
    assert saved["repository"][0]["upstream"] == "acme/new"
    listed = runner.invoke(app, ["repos", "list"])
    assert listed.exit_code == 0
    assert "acme/new" in listed.output and "R_stable" in listed.output
    assert runner.invoke(app, ["repos", "enroll", "acme/new"]).exit_code == 2
    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM repo_aliases").fetchone()[0] == 1
    conn.close()


def test_saved_old_name_validates_against_current_sqlite_name(tmp_home, tmp_path):
    workspace = tmp_path / "open-source"
    repo = _checkout(workspace)
    _git(repo, "remote", "add", "origin", "https://github.com/acme/new.git")
    (tmp_home / "repositories.toml").write_text(
        f'version = 1\nworkspace_root = "{workspace}"\n\n[[repository]]\nupstream = "acme/old"\npath = "project"\n'
    )
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute(
        "INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("R_stable", "acme/new", "acme", "new", "2026-01-01", "2026-01-01"),
    )
    repo_id = conn.execute("SELECT id FROM repos WHERE node_id='R_stable'").fetchone()[
        0
    ]
    conn.execute(
        "INSERT INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?, ?, ?)",
        (repo_id, "acme/old", "2026-01-01"),
    )
    conn.commit()
    conn.close()
    result = CliRunner().invoke(app, ["repos", "validate", "acme/old"])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output
    assert "acme/new" in result.output
