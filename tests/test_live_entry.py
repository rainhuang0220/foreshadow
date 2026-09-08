"""Human-confirmed enter: live GitHub refresh, issue lock, local contribution.

Does not write Official Top 5 ranks. Remote GitHub writes stay refused.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from foreshadow.contribution.task import from_entry
from foreshadow.db import connect, migrate
from foreshadow.entry import analyze_entry
from foreshadow.github.live_entry import (
    features_from_live,
    refresh_entry_for_repo,
)

NOW = datetime(2026, 9, 8, 3, 30, tzinfo=UTC)


def _live_payload(*, preferred=1828):
    return {
        "full_name": "vshulcz/deja-vu",
        "html_url": "https://github.com/vshulcz/deja-vu",
        "language": "Go",
        "description": "Search past AI coding sessions",
        "contributing": "PRs welcome. Run go test ./... before opening a PR.",
        "readme": "# deja-vu\nOne memory for coding agents.\n",
        "issues": [
            {
                "number": 308,
                "title": "parser: Windsurf (Cascade) session history — protobuf schema needed",
                "state": "OPEN",
                "labels": ["good first issue"],
                "assignees": [],
                "body": "Windows-only protobuf dump from Windsurf.",
                "html_url": "https://github.com/vshulcz/deja-vu/issues/308",
                "updated_at": "2026-07-28T12:41:45Z",
            },
            {
                "number": 595,
                "title": "The work records cover 2 harnesses out of 16",
                "state": "OPEN",
                "labels": ["good first issue"],
                "assignees": [],
                "body": "Cursor first. Maintainer later merged Cursor (#628) and Codex (#629).",
                "html_url": "https://github.com/vshulcz/deja-vu/issues/595",
                "updated_at": "2026-08-23T09:34:23Z",
            },
            {
                "number": preferred,
                "title": "doctor reports a stale Kimi plugin but says nothing about a stale Grok one",
                "state": "OPEN",
                "labels": ["good first issue"],
                "assignees": [],
                "body": (
                    "Mirror Kimi: grokPluginVersion constant, read installed "
                    "copy under ~/.grok/installed-plugins/*/, doctor line when "
                    "they disagree, TestGrokManifestsAgree. Must not fail when "
                    "Grok is not installed."
                ),
                "html_url": f"https://github.com/vshulcz/deja-vu/issues/{preferred}",
                "updated_at": "2026-08-25T06:00:40Z",
            },
        ],
        "prs": [
            {
                "number": 3242,
                "title": "fix(hermes): a session is titled by the person's first line",
                "body": "not related",
                "html_url": "https://github.com/vshulcz/deja-vu/pull/3242",
            }
        ],
    }


def test_windows_only_issue_is_not_plan_a():
    strat = analyze_entry(
        {
            "language": "Go",
            "full_name": "acme/x",
            "issues": [
                {
                    "number": 1,
                    "title": "crash is Windows-only",
                    "state": "OPEN",
                    "labels": ["good first issue", "bug"],
                    "assignees": [],
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "url": "https://github.com/acme/x/issues/1",
                },
                {
                    "number": 2,
                    "title": "doctor misses stale Grok plugin",
                    "state": "OPEN",
                    "labels": ["good first issue"],
                    "assignees": [],
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "url": "https://github.com/acme/x/issues/2",
                },
            ],
        },
        now=NOW,
        language="Go",
    )
    assert strat.recommended.issue_number == 2
    assert strat.recommended.issue_number != 1


def test_human_preferred_issue_locks_without_touching_official_rank():
    feat = features_from_live(_live_payload())
    strat = analyze_entry(feat, now=NOW, language="Go", preferred_issue=1828)
    assert strat.recommended.issue_number == 1828
    assert "1828" in strat.recommended.title or "Grok" in strat.recommended.title


def test_refresh_entry_persists_live_analysis_not_official_score(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    payload = _live_payload()

    def fetch(_name):
        return payload

    out = refresh_entry_for_repo(
        conn,
        "vshulcz/deja-vu",
        now=NOW,
        fetch=fetch,
        preferred_issue=1828,
        source="HUMAN_CONFIRM",
    )
    assert out["source"] == "HUMAN_CONFIRM"
    assert out["strategy"].recommended.issue_number == 1828
    row = conn.execute(
        "SELECT full_name FROM repos WHERE full_name='vshulcz/deja-vu'"
    ).fetchone()
    assert row is not None
    official = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE repo_id IN "
        "(SELECT id FROM repos WHERE full_name='vshulcz/deja-vu')"
    ).fetchone()[0]
    assert official == 0
    stored = conn.execute(
        "SELECT recommended_json FROM entry_analyses WHERE repo_id="
        "(SELECT id FROM repos WHERE full_name='vshulcz/deja-vu')"
    ).fetchone()
    assert stored is not None
    assert "1828" in stored[0]


def test_from_entry_uses_live_issue_body_not_just_title():
    extra = {
        "issue_body": (
            "Mirror what Kimi already does: grokPluginVersion constant, "
            "glob ~/.grok/installed-plugins, doctor line, TestGrokManifestsAgree. "
            "Must not fail when Grok is not installed."
        ),
        "expected_behavior": (
            "deja doctor reports a stale Grok plugin the same way it reports Kimi"
        ),
        "acceptance_criteria": [
            "grokPluginVersion matches extensions/grok plugin.json",
            "TestGrokManifestsAgree keeps the constant honest",
            "missing Grok install is silent, not an error",
        ],
        "relevant_files": ["cmd/deja/kimi_plugin.go", "cmd/deja/doctor.go"],
        "test_commands": ["go test ./cmd/deja -count=1 -run ManifestsAgree"],
    }
    task = from_entry(
        "vshulcz/deja-vu",
        {
            "recommended": {
                "title": "doctor reports a stale Kimi plugin but says nothing about a stale Grok one",
                "issue_number": 1828,
                "why": ["human-confirmed"],
                "evidence": [
                    {
                        "kind": "issue",
                        "id": 1828,
                        "url": "https://github.com/vshulcz/deja-vu/issues/1828",
                    }
                ],
            }
        },
        extra=extra,
    )
    assert task.issue_number == 1828
    assert "Grok" in task.task or "plugin" in task.task.lower()
    assert task.expected_behavior
    assert any(
        "ManifestsAgree" in x or "not installed" in x for x in task.acceptance_criteria
    )
    assert task.relevant_files
    assert task.test_commands
    assert "git push" in task.forbidden_actions
    prompt = task.to_prompt()
    assert "1828" in prompt
    assert prompt.count("Task:") == 1
    assert extra["issue_body"][:40] in prompt or extra["expected_behavior"] in prompt


def test_enter_contribute_runs_executor_not_demo_add(tmp_home, monkeypatch):
    from foreshadow.auth import ensure_local_user
    from foreshadow.contribution.executor import (
        ContributionJob,
        JobStatus,
        PatchArtifact,
    )
    from foreshadow.contribution.local import start_local_contribution
    from foreshadow.mission import create_for_user, setup_local_environment

    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    payload = _live_payload()

    def fetch(_name):
        return payload

    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload",
        fetch,
    )
    mission = create_for_user(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        issue_number=1828,
        source="HUMAN_CONFIRM",
        live=True,
    )
    assert mission.strategy.why
    assert any("1828" in str(x) for x in [*mission.why_now, *mission.strategy.why])
    setup_local_environment(conn, mission.id or 0, uid, tmp_home)

    seen: list[str] = []

    class _Exec:
        name = "recording"

        def prepare(self, job: ContributionJob) -> None:
            seen.append("prepare")
            job.work_dir = tmp_home / "work"
            job.sandbox_path = tmp_home / "work"

        def analyze(self, job: ContributionJob) -> None:
            seen.append("analyze")

        def implement(self, job: ContributionJob) -> None:
            seen.append("implement")
            assert str((job.task or {}).get("fixture") or "") != "demo_add"
            structured = (job.task or {}).get("structured") or {}
            assert structured.get("issue_number") == 1828
            assert structured.get("expected_behavior")
            (tmp_home / "work").mkdir(parents=True, exist_ok=True)
            (tmp_home / "work" / "note.txt").write_text(
                "grok doctor\n", encoding="utf-8"
            )

        def test(self, job: ContributionJob) -> None:
            seen.append("test")
            job.test_result = {
                "ok": True,
                "returncode": 0,
                "command": "go test",
                "log": "ok",
            }

        def iterate(self, job: ContributionJob) -> None:
            seen.append("iterate")

        def produce_patch(self, job: ContributionJob) -> PatchArtifact:
            seen.append("patch")
            return PatchArtifact(
                diff="diff --git a/cmd/deja/doctor.go b/cmd/deja/doctor.go\n+grok\n",
                why=job.why,
                test_log="ok",
                files=["cmd/deja/doctor.go"],
                title="doctor: report a stale Grok plugin (#1828)",
                tests_passed=True,
            )

    job = start_local_contribution(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        executor=_Exec(),
    )
    assert job.status is JobStatus.ready
    assert seen == ["prepare", "analyze", "implement", "test", "iterate", "patch"]
    assert "demo_add" not in str(job.task)
    from foreshadow.contribution.jobs import list_artifacts

    kinds = {row["kind"] for row in list_artifacts(conn, job.id)}
    assert "package" in kinds


def test_workspace_package_includes_new_untracked_files(tmp_path):
    from foreshadow.contribution.executor import ContributionJob, get_executor

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    (repo / "keep.go").write_text("package main\n", encoding="utf-8")
    subprocess.run(["git", "add", "keep.go"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "grok_plugin.go").write_text(
        'package main\nconst grokPluginVersion = "0.2.0"\n', encoding="utf-8"
    )
    exe = get_executor("workspace")
    job = ContributionJob(
        full_name="vshulcz/deja-vu",
        task={
            "why": "doctor is silent about a stale Grok plugin",
            "structured": {
                "repository": "vshulcz/deja-vu",
                "task": "doctor reports a stale Kimi plugin but says nothing about a stale Grok one",
                "why": "doctor is silent about a stale Grok plugin",
                "issue_number": 1828,
                "relevant_files": ["cmd/deja/kimi_plugin.go"],
            },
        },
        source_dir=repo,
        work_dir=tmp_path,
    )
    job.test_result = {"ok": True, "returncode": 0, "command": "go test", "log": "ok"}
    exe.prepare(job)
    artifact = exe.produce_patch(job)
    assert "grok_plugin.go" in artifact.diff
    assert artifact.title.startswith("fix(doctor):")


def test_workspace_backend_refuses_demo_add_and_empty_tree(tmp_path):
    from foreshadow.contribution.executor import (
        ContributionError,
        ContributionJob,
        get_executor,
    )

    exe = get_executor("workspace")
    assert exe.name == "workspace"
    job = ContributionJob(
        full_name="acme/x",
        task={"fixture": "demo_add"},
        source_dir=tmp_path,
    )
    try:
        exe.implement(job)
        raise AssertionError("demo_add must be refused")
    except ContributionError as exc:
        assert "demo_add" in str(exc)


def test_confirmed_contribution_uses_go_tests_when_go_mod_present(tmp_home, tmp_path):
    from foreshadow.auth import ensure_local_user
    from foreshadow.contribution.local import _extras_for
    from foreshadow.db import connect, migrate

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    repo = tmp_path / "vshulcz__deja-vu" / "repo"
    repo.mkdir(parents=True)
    (repo / "go.mod").write_text(
        "module github.com/vshulcz/deja-vu\n", encoding="utf-8"
    )
    (repo / "package.json").write_text("{}", encoding="utf-8")
    plan = {
        "full_name": "vshulcz/deja-vu",
        "local_path": str(repo.parent),
        "language": "JavaScript",
        "inspect": {
            "kind": "node",
            "language": "JavaScript",
            "tests": {"kind": "node", "command": "npm test"},
        },
    }
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, repo_id, full_name, status, entry_path, difficulty, effort,
          plan_json, local_path, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            None,
            "vshulcz/deja-vu",
            "WAITING_USER_APPROVAL",
            "PR",
            "Medium",
            "6h",
            json.dumps(plan),
            str(repo.parent),
            "2026-09-08T00:00:00+00:00",
            "2026-09-08T00:00:00+00:00",
        ),
    )
    conn.commit()
    extra = _extras_for(
        conn,
        uid,
        "vshulcz/deja-vu",
        {"recommended": {"issue_number": 1828}},
        data_dir=tmp_home,
    )
    assert extra["test_commands"][0].startswith("go test")
    assert "npm test" not in extra["test_commands"]


def test_cli_enter_accepts_issue_and_contribute_flags():
    from typer.testing import CliRunner

    from foreshadow.cli import app

    result = CliRunner().invoke(app, ["enter", "--help"])
    assert result.exit_code == 0
    assert "--issue" in result.stdout
    assert "--contribute" in result.stdout


def test_active_entry_replaces_old_mission_recommendation(tmp_home, monkeypatch):
    from pathlib import Path

    from foreshadow.auth import ensure_local_user
    from foreshadow.mission import create_for_user

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload", lambda _: _live_payload()
    )
    mission = create_for_user(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        issue_number=1828,
        source="HUMAN_CONFIRM",
        live=True,
    )
    text = (Path(mission.local_path) / "FORESHADOW.md").read_text()
    assert "#1828" in text
    assert "#308" not in text
    assert "#595" not in text
    from foreshadow.mission import list_missions

    plan = list_missions(conn, uid)[0]
    assert plan["active_entry_target"]["issue_number"] == 1828


def test_contribution_ignores_stale_cited_issue(tmp_home, monkeypatch):
    from foreshadow.contribution.local import _extras_for

    monkeypatch.setattr(
        "foreshadow.contribution.local.list_missions",
        lambda *a: [
            {
                "full_name": "vshulcz/deja-vu",
                "cited_issue": {"number": 308, "body": "STALE A"},
                "local_path": str(tmp_home / "missing"),
            }
        ],
    )
    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload", lambda _: _live_payload()
    )
    extra = _extras_for(
        None,
        1,
        "vshulcz/deja-vu",
        {"recommended": {"issue_number": 1828}},
        data_dir=tmp_home,
    )
    assert "STALE A" not in extra["issue_body"]
    assert "Grok" in extra["issue_body"]


def test_failed_live_confirmation_cannot_create_stale_mission(tmp_home, monkeypatch):
    import pytest

    from foreshadow.auth import ensure_local_user
    from foreshadow.mission import create_for_user

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)

    def unavailable(_):
        raise RuntimeError("live GET unavailable")

    monkeypatch.setattr("foreshadow.github.live_entry.fetch_live_payload", unavailable)
    with pytest.raises(RuntimeError, match="live GET unavailable"):
        create_for_user(
            conn,
            user_id=uid,
            full_name="vshulcz/deja-vu",
            data_dir=tmp_home,
            issue_number=1828,
            source="HUMAN_CONFIRM",
            live=True,
        )
    assert conn.execute("SELECT count(*) FROM entry_missions").fetchone()[0] == 0


def test_entry_revision_follows_task_and_package():
    from foreshadow.contribution.executor import ContributionJob, PatchArtifact
    from foreshadow.contribution.package import build_package

    entry = analyze_entry(
        features_from_live(_live_payload()),
        now=NOW,
        language="Go",
        preferred_issue=1828,
    ).as_dict()
    task = from_entry("vshulcz/deja-vu", entry)
    assert task.entry_revision == entry["revision"]
    package = build_package(
        ContributionJob(
            full_name="vshulcz/deja-vu", task={"structured": task.as_dict()}
        ),
        PatchArtifact(diff=""),
    )
    assert package["entry_revision"] == entry["revision"]


def test_second_confirmation_creates_separate_mission_without_touching_first(
    tmp_home, monkeypatch
):
    from pathlib import Path

    from foreshadow.auth import ensure_local_user
    from foreshadow.mission import create_for_user, list_missions

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload", lambda _: _live_payload()
    )
    a = create_for_user(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        issue_number=1828,
        live=True,
    )
    before = (Path(a.local_path) / "FORESHADOW.md").read_bytes()
    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload",
        lambda _: _live_payload(preferred=1829),
    )
    b = create_for_user(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        issue_number=1829,
        live=True,
    )
    assert b.id != a.id
    assert b.local_path != a.local_path
    assert (Path(a.local_path) / "FORESHADOW.md").read_bytes() == before
    plan = list_missions(conn, uid)[0]
    assert plan["active_entry_target"]["issue_number"] == 1829
    assert plan["historical_entry"]["recommended"]["issue_number"] == 1828
    monkeypatch.setattr(
        "foreshadow.github.live_entry.fetch_live_payload",
        lambda _: _live_payload(preferred=1830),
    )
    create_for_user(
        conn,
        user_id=uid,
        full_name="vshulcz/deja-vu",
        data_dir=tmp_home,
        issue_number=1830,
        live=True,
    )
    assert (
        list_missions(conn, uid)[0]["historical_entry"]["recommended"]["issue_number"]
        == 1828
    )

    assert (
        plan["entry_strategy"]["revision"]
        in (Path(b.local_path) / "FORESHADOW.md").read_text()
    )


def test_missing_explicit_issue_is_rejected_instead_of_falling_back(tmp_home):
    import pytest

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    with pytest.raises(ValueError, match="confirmed issue"):
        refresh_entry_for_repo(
            conn,
            "vshulcz/deja-vu",
            now=NOW,
            preferred_issue=99999,
            fetch=lambda _: _live_payload(),
        )
