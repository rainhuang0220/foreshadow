import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from foreshadow.cli import app


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def repository(tmp_path):
    path = tmp_path / "source"
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.org")
    (path / "parser.py").write_text('def parse(value):\n    return value.get("key")\n')
    git(path, "add", ".")
    git(path, "commit", "-m", "baseline")
    return path


def test_local_observation_reads_pinned_blobs_and_does_not_launder_dirty_content(
    tmp_path,
):
    from foreshadow.decision.adapters import observe_files
    from foreshadow.decision.models import Repository

    path = repository(tmp_path)
    revision = git(path, "rev-parse", "HEAD")
    (path / "parser.py").write_text("uncommitted human work")
    repo = Repository(identity="acme/project", path=str(path), base_revision=revision)
    observed = observe_files(
        repo, ("parser.py",), now=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert len(observed) == 1
    assert "uncommitted human work" not in observed[0].summary
    assert revision in observed[0].source
    assert "sha256=" in observed[0].summary
    assert (path / "parser.py").read_text() == "uncommitted human work"
    with pytest.raises(ValueError):
        observe_files(repo, ("../outside",), now=datetime(2026, 10, 3, tzinfo=UTC))


def test_local_plan_cli_exports_canonical_json_without_source_writes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "foreshadow.decision.cli._clock", lambda: datetime(2026, 10, 3, tzinfo=UTC)
    )
    from foreshadow.work_order import loads

    path = repository(tmp_path)
    before = git(path, "status", "--porcelain")
    args = [
        "work-order",
        "plan",
        str(path),
        "--identity",
        "acme/project",
        "--title",
        "Guard parser",
        "--objective",
        "Reject nonobject input",
        "--rationale",
        "A direct value.get call has no type guard",
        "--source-file",
        "parser.py",
        "--check",
        "python3 -m unittest",
        "--acceptance",
        "Invalid input receives an error",
        "--as-of",
        "2026-10-03T00:00:00Z",
    ]
    runner = CliRunner()
    first, second = runner.invoke(app, args), runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert first.stdout == second.stdout
    order = loads(first.stdout)
    assert order["repository"]["base_revision"] == git(path, "rev-parse", "HEAD")
    assert (
        order["evidence"][0]["kind"] == "inference"
        or order["evidence"][0]["kind"] == "observation"
    )
    assert git(path, "status", "--porcelain") == before
    bad = runner.invoke(app, args + ["--check", "python3 -m unittest; curl x"])
    assert bad.exit_code == 2


def test_stored_entry_keeps_capture_time_and_rejects_refreshed_analysis_on_old_snapshot(
    tmp_home, tmp_path
):
    from fakes import seed_repo
    from foreshadow.db import connect, migrate
    from foreshadow.decision.adapters import stored_opportunity
    from foreshadow.decision.models import Repository, Validation
    from foreshadow.decision.pipeline import validate_opportunity
    from foreshadow.entry import (
        ContributionPolicy,
        EntryPlan,
        EntryStrategy,
        persist_entry,
    )

    now = datetime(2026, 10, 3, tzinfo=UTC)
    path = repository(tmp_path)
    repo = Repository(
        identity="acme/project",
        path=str(path),
        base_revision=git(path, "rev-parse", "HEAD"),
    )
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/project")
    conn.execute(
        "INSERT INTO snapshots(repo_id,snapshot_date,captured_at,stars,completeness) VALUES (?,?,?,?,1)",
        (rid, "2026-09-20", "2026-09-20T00:00:00Z", 100),
    )
    strategy = EntryStrategy(
        ContributionPolicy(False, True, None, None, None),
        EntryPlan(
            route="ISSUE",
            title="Guard parser",
            summary_zh="Reject invalid input",
            issue_number=1,
            pr_number=None,
            why=["Unsafe lookup"],
            effort="small",
            risk="low",
            confidence=0.8,
        ),
        [],
        now.isoformat(),
        (now + timedelta(days=3)).isoformat(),
    )
    persist_entry(conn, rid, strategy)
    before = conn.total_changes
    opportunity, observations = stored_opportunity(
        conn, repo, checks=(Validation(("python3", "-m", "unittest"), "Tests pass"),)
    )
    assert observations[0].observed_at == datetime(2026, 9, 20, tzinfo=UTC)
    with pytest.raises(ValueError, match="stale"):
        validate_opportunity(opportunity, observations, now=now)
    assert conn.total_changes == before
    conn.close()
