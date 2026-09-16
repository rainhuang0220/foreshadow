"""Gate-2 safety contract shared by CLI, Board, and submission internals."""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from typer.testing import CliRunner

from foreshadow.auth import ensure_local_user
from foreshadow.cli import app
from foreshadow.contribution.approval import (
    create_snapshot,
    current_snapshot,
    invalidate_snapshot,
    snapshot_fields,
)
from foreshadow.contribution.board_api import execute_gate2
from foreshadow.contribution.executor import ContributionJob, JobStatus
from foreshadow.contribution.jobs import persist_artifact, persist_job
from foreshadow.contribution.review import contribution_for_mission
from foreshadow.contribution.submit import FakeGitHub, submit_approved
from foreshadow.db import connect, migrate
from foreshadow.mission import load_mission_plan


def _fields(mission_id: int) -> dict:
    return snapshot_fields(
        mission_id=mission_id,
        repository="acme/toy",
        issue_number=7,
        issue_url="https://github.com/acme/toy/issues/7",
        base_repo="acme/toy",
        base_branch="main",
        validated_base_sha="base",
        patch_commit_sha="patch",
        diff_sha256="diff",
        branch_name="foreshadow/entry-7",
        pr_title="Fix seven",
        pr_body="Fixes #7",
        test_evidence_digest="tests",
        qa_verdict="PASS",
        maintainer_output_safety="PASS",
        freshness="EXACT",
    )


def _mission(conn, user_id: int) -> int:
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            "acme/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _exact_port() -> FakeGitHub:
    port = FakeGitHub()
    port.refs["main"] = "base"
    return port


def _connection(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    return conn, ensure_local_user(conn)


def _package() -> dict:
    return {
        "repository": "acme/toy",
        "related_issue": "#7",
        "issue_url": "https://github.com/acme/toy/issues/7",
        "pr_title": "Fix seven",
        "pr_body": "Fixes #7",
        "diff": "diff --git a/a b/a\n+fix\n",
        "files_changed": ["a"],
        "validated_base_sha": "base",
        "patch_commit_sha": "patch",
        "freshness": "EXACT",
        "tests": {"ok": True},
        "qa": "PASS",
        "qa_ok": True,
        "implementation": {"branch": "foreshadow/entry-7", "upstream_head": "base"},
    }


def _review(conn, user_id: int, mission_id: int) -> tuple[dict, int]:
    job = ContributionJob(
        user_id=user_id,
        full_name="acme/toy",
        backend="native",
        status=JobStatus.ready,
        mission_id=mission_id,
        task={"structured": {"issue_number": 7}},
    )
    job_id = persist_job(conn, job)
    persist_artifact(conn, job_id, kind="package", body=json.dumps(_package()))
    review = contribution_for_mission(conn, user_id, mission_id)
    assert review is not None
    return review, job_id


def test_internal_submit_binds_only_the_approved_payload_and_provenance(tmp_home):
    conn, user_id = _connection(tmp_home)
    mission_id = _mission(conn, user_id)
    fields = _fields(mission_id)
    snapshot = create_snapshot(conn, user_id=user_id, fields=fields)

    class CapturingPort(FakeGitHub):
        def create_pr(self, repo, *, title, body, head, base):
            self.create_args = (repo, title, body, head, base)
            return super().create_pr(repo, title=title, body=body, head=head, base=base)

    port = CapturingPort()
    port.refs["main"] = "base"
    out = submit_approved(
        conn,
        user_id=user_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )

    assert out["status"] == "SUBMITTED"
    assert port.create_args == (
        "acme/toy",
        fields["pr_title"],
        fields["pr_body"],
        "tester:foreshadow/entry-7",
        fields["base_branch"],
    )
    assert port.pushes == [
        ("tester/toy", fields["branch_name"], fields["patch_commit_sha"])
    ]
    plan = load_mission_plan(conn, mission_id, user_id)
    row = conn.execute(
        "SELECT mission_id, approval_snapshot_id FROM submissions WHERE id=?",
        (out["submission_id"],),
    ).fetchone()
    assert plan["approval_snapshot_id"] == snapshot["approval_snapshot_id"]
    assert plan["submission_id"] == out["submission_id"]
    assert row == (mission_id, snapshot["approval_snapshot_id"])


@pytest.mark.parametrize("case", ["missing", "invalidated", "mission", "payload"])
def test_internal_submit_blocks_every_invalid_gate2_grant(tmp_home, case):
    conn, user_id = _connection(tmp_home)
    mission_id = _mission(conn, user_id)
    fields = _fields(mission_id)
    snapshot = create_snapshot(conn, user_id=user_id, fields=fields)
    port = _exact_port()

    if case == "missing":
        with pytest.raises(LookupError, match="approval snapshot not found"):
            submit_approved(
                conn,
                user_id=user_id,
                snapshot_id=int(snapshot["approval_snapshot_id"]) + 99,
                current_fields=fields,
                port=port,
                allow_real_remote=True,
            )
    else:
        if case == "invalidated":
            invalidate_snapshot(
                conn, int(snapshot["approval_snapshot_id"]), user_id=user_id
            )
            current_fields = fields
        elif case == "mission":
            current_fields = {**fields, "mission_id": mission_id + 1}
        else:
            current_fields = {**fields, "pr_body": "Changed after approval"}
        out = submit_approved(
            conn,
            user_id=user_id,
            snapshot_id=int(snapshot["approval_snapshot_id"]),
            current_fields=current_fields,
            port=port,
            allow_real_remote=True,
        )
        assert out["status"] == "APPROVAL_STALE"
        assert out["remote_writes"] == 0

    assert port.created_prs == 0
    assert port.pushes == []


def test_duplicate_submit_is_resumed_without_another_remote_write(tmp_home):
    conn, user_id = _connection(tmp_home)
    mission_id = _mission(conn, user_id)
    fields = _fields(mission_id)
    snapshot = create_snapshot(conn, user_id=user_id, fields=fields)
    port = _exact_port()
    first = submit_approved(
        conn,
        user_id=user_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    second = submit_approved(
        conn,
        user_id=user_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )

    assert first["status"] == "SUBMITTED"
    assert second["ok"] is True
    assert second["status"] == "SUBMITTED"
    assert second["resumed"] is True
    assert second["remote_writes"] == 0
    assert second["pr"]["number"] == first["pr"]["number"]
    assert second["pr"]["head_sha"] == "patch"
    assert port.created_prs == 1


def test_invalidated_approval_cannot_resume_a_previous_submission(tmp_home):
    conn, user_id = _connection(tmp_home)
    mission_id = _mission(conn, user_id)
    fields = _fields(mission_id)
    snapshot = create_snapshot(conn, user_id=user_id, fields=fields)
    port = _exact_port()
    submit_approved(
        conn,
        user_id=user_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    invalidate_snapshot(conn, int(snapshot["approval_snapshot_id"]), user_id=user_id)

    out = submit_approved(
        conn,
        user_id=user_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out == {"ok": False, "status": "APPROVAL_STALE", "remote_writes": 0}
    assert port.created_prs == 1


def test_board_api_uses_the_review_snapshot_and_rejects_changed_package(tmp_home):
    conn, user_id = _connection(tmp_home)
    mission_id = _mission(conn, user_id)
    review, job_id = _review(conn, user_id, mission_id)
    snapshot = current_snapshot(conn, user_id=user_id, mission_id=mission_id)
    assert snapshot is not None
    original = _package()
    changed = {**original, "pr_body": "Changed after approval"}
    conn.execute(
        "UPDATE contribution_artifacts SET body=? WHERE job_id=? AND kind='package'",
        (json.dumps(changed), job_id),
    )
    conn.commit()

    out = execute_gate2(
        conn,
        user_id=user_id,
        mission_id=mission_id,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        confirm=True,
        port=_exact_port(),
    )
    refreshed = contribution_for_mission(conn, user_id, mission_id)
    assert review["approval_snapshot_id"] == snapshot["approval_snapshot_id"]
    assert refreshed["approval"]["status"] == "stale"
    assert out["status"] == "APPROVAL_STALE"
    assert out["remote_writes"] == 0


def test_cli_submit_and_board_http_submit_share_idempotent_gate2_behavior(
    tmp_home, monkeypatch
):
    monkeypatch.setenv("FORESHADOW_SUBMIT_FAKE", "1")
    conn, user_id = _connection(tmp_home)
    cli_mission_id = _mission(conn, user_id)
    _review(conn, user_id, cli_mission_id)
    runner = CliRunner()
    first_cli = runner.invoke(
        app, ["submit", "--mission-id", str(cli_mission_id), "--confirm"]
    )
    second_cli = runner.invoke(
        app, ["submit", "--mission-id", str(cli_mission_id), "--confirm"]
    )

    assert first_cli.exit_code == 0, first_cli.output
    assert second_cli.exit_code == 0, second_cli.output
    assert json.loads(first_cli.output)["status"] == "SUBMITTED"
    assert json.loads(second_cli.output)["remote_writes"] == 0

    from foreshadow.board.server import make_server

    httpd = make_server(host="127.0.0.1", port=0, preview=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    client = httpx.Client()
    try:
        registered = client.post(
            f"{base}/api/register",
            json={
                "username": "gate2-operator",
                "email": "gate2@example.com",
                "password": "password1",
            },
        )
        assert registered.status_code == 200
        user_row = conn.execute(
            "SELECT id FROM users WHERE username=?", ("gate2-operator",)
        ).fetchone()
        assert user_row is not None
        api_mission_id = _mission(conn, int(user_row[0]))
        _review(conn, int(user_row[0]), api_mission_id)

        first_api = client.post(
            f"{base}/api/contribution/submit",
            json={"mission_id": api_mission_id, "confirm": True},
        )
        second_api = client.post(
            f"{base}/api/contribution/submit",
            json={"mission_id": api_mission_id, "confirm": True},
        )
        assert first_api.status_code == 200
        assert second_api.status_code == 200
        assert first_api.json()["status"] == "SUBMITTED"
        assert second_api.json()["remote_writes"] == 0
    finally:
        client.close()
        httpd.shutdown()
        httpd.server_close()
