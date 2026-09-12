from __future__ import annotations

import json
import sqlite3
import threading
import time

import httpx
import pytest

from foreshadow.contribution import board_api
from foreshadow.contribution.approval import (
    create_snapshot,
    snapshot_fields,
)
from foreshadow.contribution.submit import (
    FakeGitHub,
    RemoteWriteRefused,
    persist_submission,
    submit_approved,
)
from foreshadow.github.approved_write import ApprovedGitHubPort, assert_action_allowed


def _fields() -> dict:
    return snapshot_fields(
        mission_id=1,
        repository="upstream/toy",
        issue_number=7,
        issue_url="https://github.com/upstream/toy/issues/7",
        base_repo="upstream/toy",
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


def test_ready_requires_transport_credential_snapshot_and_exact_upstream():
    assert hasattr(board_api, "assess_submission_readiness")
    assess_submission_readiness = board_api.assess_submission_readiness
    fields = _fields()
    snapshot = {**fields, "status": "current", "approval_digest": ""}
    from foreshadow.contribution.approval import compute_digest

    snapshot["approval_digest"] = compute_digest(fields)
    port = FakeGitHub()
    port.refs["main"] = "base"

    ready = assess_submission_readiness(
        review={"status": "WAITING_USER_APPROVAL", "package": {}},
        fields=fields,
        snapshot=snapshot,
        port=port,
    )
    assert ready["display_status"] == "READY_FOR_HUMAN_SUBMIT"
    assert ready["approval_enabled"] is True
    assert ready["checks"] == {
        "write_transport_ready": True,
        "credential_ready": True,
        "snapshot_current": True,
        "upstream_fresh": True,
        "package_complete": True,
    }

    port.refs["main"] = "new-base"
    port.files = ["docs/README.md"]
    stale = assess_submission_readiness(
        review={"status": "WAITING_USER_APPROVAL", "package": {}},
        fields=fields,
        snapshot=snapshot,
        port=port,
    )
    assert stale["display_status"] == "NEEDS_REFRESH"
    assert stale["checks"]["upstream_fresh"] is False


def test_missing_write_credential_never_displays_ready():
    fields = _fields()
    from foreshadow.contribution.approval import compute_digest

    snapshot = {
        **fields,
        "status": "current",
        "approval_digest": compute_digest(fields),
    }

    class NoCredential(FakeGitHub):
        is_fake = False

        def transport_ready(self, sha):
            return True

        def credential_ready(self, repo):
            return False

    result = board_api.assess_submission_readiness(
        review={"status": "WAITING_USER_APPROVAL", "package": {}},
        fields=fields,
        snapshot=snapshot,
        port=NoCredential(),
    )
    assert result["display_status"] == "CREDENTIAL_REQUIRED"
    assert result["approval_enabled"] is False


def test_review_ui_uses_computed_readiness_and_disables_submit():
    from foreshadow.board.webapp import APP_HTML
    from foreshadow.contribution.identity import display_status

    assert display_status("WAITING_USER_APPROVAL") == "SUBMISSION_CHECK_REQUIRED"
    assert '${esc(r.display_status || "SUBMISSION_CHECK_REQUIRED")}' in APP_HTML
    assert '${r.approval_enabled?"":"disabled"}' in APP_HTML
    assert 'r.display_status === "NEEDS_REFRESH"' in APP_HTML
    assert 'status ${esc(r.display_status || "SUBMISSION_CHECK_REQUIRED")}' in APP_HTML


def test_review_ui_distinguishes_refresh_from_intentional_editing():
    from foreshadow.board.webapp import APP_HTML

    assert 'r.display_status === "NEEDS_REFRESH" ? "刷新并重新验证" : "继续修改"' in APP_HTML
    assert 'r.display_status === "NEEDS_REFRESH" ? "refreshContribution" : "continueContribution"' in APP_HTML


def test_approval_snapshot_binds_package_revision():
    from foreshadow.contribution.approval import compute_digest, matches_package

    fields = {**_fields(), "package_revision": 19}
    snapshot = {
        **fields,
        "status": "current",
        "approval_digest": compute_digest(fields),
    }
    assert matches_package(snapshot, fields)
    assert not matches_package(snapshot, {**fields, "package_revision": 20})


def test_one_submission_record_per_approval_snapshot(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    snap = create_snapshot(conn, user_id=uid, fields={**_fields(), "mission_id": mid})
    values = (
        uid,
        mid,
        snap["approval_snapshot_id"],
        "PREFLIGHT",
        "{}",
        "{}",
        "now",
        "now",
    )
    conn.execute(
        "INSERT INTO submissions(user_id, mission_id, approval_snapshot_id, status, steps_json, result_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        values,
    )
    with pytest.raises(Exception, match="UNIQUE"):
        conn.execute(
            "INSERT INTO submissions(user_id, mission_id, approval_snapshot_id, status, steps_json, result_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            values,
        )


def test_concurrent_submit_reuses_one_submission_record(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate

    path = tmp_home / "foreshadow.sqlite3"
    setup = connect(path)
    migrate(setup)
    uid = ensure_local_user(setup)
    setup.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(setup.execute("SELECT last_insert_rowid()").fetchone()[0])
    snap = create_snapshot(setup, user_id=uid, fields={**_fields(), "mission_id": mid})
    setup.close()
    barrier = threading.Barrier(2)
    ids: list[int] = []
    errors: list[BaseException] = []

    class PausedSelect:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, params=()):
            result = self.connection.execute(sql, params)
            if "SELECT id FROM submissions" in sql:
                row = result.fetchone()
                barrier.wait(timeout=5)
                return type("OneRow", (), {"fetchone": lambda self: row})()
            return result

        def commit(self):
            self.connection.commit()

    def run():
        connection = connect(path)
        try:
            ids.append(
                persist_submission(
                    PausedSelect(connection),
                    user_id=uid,
                    mission_id=mid,
                    snapshot_id=int(snap["approval_snapshot_id"]),
                )
            )
        except (sqlite3.Error, RuntimeError) as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert len(ids) == 2
    assert ids[0] == ids[1]


def test_real_port_reuses_fork_and_only_pushes_exact_commit(tmp_path):
    bundle = tmp_path / "patch.bundle"
    bundle.write_bytes(b"bundle")
    requests: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path == "/user":
            return httpx.Response(
                200,
                json={"login": "operator"},
                headers={"x-oauth-scopes": "public_repo"},
            )
        if request.url.path == "/repos/upstream/toy":
            return httpx.Response(200, json={"permissions": {"push": False}})
        if request.url.path == "/repos/operator/toy":
            return httpx.Response(
                200,
                json={
                    "full_name": "operator/toy",
                    "fork": True,
                    "parent": {"full_name": "upstream/toy"},
                    "permissions": {"push": True},
                },
            )
        if request.url.path.endswith("/git/ref/heads/foreshadow/entry-7"):
            return httpx.Response(404, json={"message": "Not Found"})
        if request.url.path == "/repos/upstream/toy/pulls" and request.method == "POST":
            return httpx.Response(
                201, json={"number": 9, "html_url": "https://example/pr/9"}
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    commands: list[list[str]] = []

    def run_git(args: list[str], **_kwargs):
        commands.append(args)
        stdout = (
            "patch HEAD\n"
            if "list-heads" in args
            else "base\n"
            if "rev-parse" in args
            else ""
        )
        return type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    port = ApprovedGitHubPort(
        token="test-token",
        client=client,
        bundle_path=bundle,
        validated_base_sha="base",
        git_runner=run_git,
    )

    assert port.credential_ready("upstream/toy") is True
    assert port.transport_ready("patch") is True
    fork = port.ensure_fork("upstream/toy")
    assert fork == "operator/toy"
    assert port.ensure_branch(fork, "foreshadow/entry-7", "patch") == "patch"
    assert port.push_commit(fork, "foreshadow/entry-7", "patch") == "patch"
    pr = port.create_pr(
        "upstream/toy",
        title="Fix seven",
        body="Fixes #7",
        head="operator:foreshadow/entry-7",
        base="main",
    )
    assert pr["number"] == 9
    flat = " ".join(part for command in commands for part in command)
    assert "patch:refs/heads/foreshadow/entry-7" in flat
    assert "--force" not in flat
    assert not any(
        "comments" in path or "reviews" in path or "merge" in path
        for _, path, _ in requests
    )


def test_real_port_accepts_exact_commit_from_local_repository(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    commands: list[list[str]] = []

    def run_git(args: list[str], **_kwargs):
        commands.append(args)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    port = ApprovedGitHubPort(
        token="test-token",
        repo_path=repo_path,
        validated_base_sha="base",
        source_repo="upstream/toy",
        git_runner=run_git,
    )
    assert port.transport_ready("patch") is True
    assert any("cat-file" in command for command in commands)


def test_real_port_falls_back_to_bundle_when_checkout_lacks_commit(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    bundle = tmp_path / "patch.bundle"
    bundle.write_bytes(b"bundle")

    def run_git(args: list[str], **_kwargs):
        if "cat-file" in args:
            return type(
                "Result", (), {"returncode": 1, "stdout": "", "stderr": "missing"}
            )()
        if "list-heads" in args:
            return type(
                "Result", (), {"returncode": 0, "stdout": "patch HEAD\n", "stderr": ""}
            )()
        return type("Result", (), {"returncode": 0, "stdout": "base\n", "stderr": ""})()

    port = ApprovedGitHubPort(
        token="test-token",
        repo_path=repo_path,
        bundle_path=bundle,
        validated_base_sha="base",
        source_repo="upstream/toy",
        git_runner=run_git,
    )
    assert port.transport_ready("patch") is True


def test_create_pr_recovers_when_post_response_is_lost():
    post_attempted = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_attempted
        if request.method == "POST":
            post_attempted = True
            raise httpx.ReadTimeout("response lost", request=request)
        if request.url.path == "/repos/upstream/toy/pulls" and post_attempted:
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 9,
                        "html_url": "https://example/pr/9",
                        "head": {
                            "ref": "foreshadow/entry-7",
                            "sha": "patch",
                            "label": "operator:foreshadow/entry-7",
                        },
                        "base": {"ref": "main"},
                    }
                ],
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    pr = port.create_pr(
        "upstream/toy",
        title="Fix seven",
        body="Fixes #7",
        head="operator:foreshadow/entry-7",
        base="main",
    )
    assert pr["number"] == 9


def test_ensure_fork_recovers_when_post_response_is_lost():
    post_attempted = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_attempted
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "operator"})
        if request.url.path == "/repos/upstream/toy":
            return httpx.Response(200, json={"permissions": {"push": False}})
        if request.url.path == "/repos/operator/toy":
            if post_attempted:
                return httpx.Response(
                    200,
                    json={
                        "parent": {"full_name": "upstream/toy"},
                        "permissions": {"push": True},
                    },
                )
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path.endswith("/forks"):
            post_attempted = True
            raise httpx.ReadTimeout("response lost", request=request)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    assert port.ensure_fork("upstream/toy") == "operator/toy"


def test_concurrent_gate2_clicks_create_only_one_pr(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate

    path = tmp_home / "foreshadow.sqlite3"
    setup = connect(path)
    migrate(setup)
    uid = ensure_local_user(setup)
    setup.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(setup.execute("SELECT last_insert_rowid()").fetchone()[0])
    fields = {**_fields(), "mission_id": mid}
    snapshot = create_snapshot(setup, user_id=uid, fields=fields)
    setup.close()

    class SlowPort(FakeGitHub):
        def __init__(self):
            super().__init__()
            self.active_forks = 0
            self.max_active_forks = 0
            self.counter_lock = threading.Lock()

        def ensure_fork(self, repo):
            with self.counter_lock:
                self.active_forks += 1
                self.max_active_forks = max(self.max_active_forks, self.active_forks)
            try:
                time.sleep(0.1)
                return super().ensure_fork(repo)
            finally:
                with self.counter_lock:
                    self.active_forks -= 1

    port = SlowPort()
    port.refs["main"] = "base"
    results: list[dict] = []
    errors: list[BaseException] = []

    def run():
        connection = connect(path)
        try:
            results.append(
                submit_approved(
                    connection,
                    user_id=uid,
                    snapshot_id=int(snapshot["approval_snapshot_id"]),
                    current_fields=fields,
                    port=port,
                    allow_real_remote=True,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert len(results) == 2
    assert all(result["status"] == "SUBMITTED" for result in results)
    assert port.created_prs == 1
    assert port.max_active_forks == 1


def test_submit_uses_qualified_fork_head_for_create_pr(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    fields = {**_fields(), "mission_id": mid}
    snapshot = create_snapshot(conn, user_id=uid, fields=fields)

    class Port(FakeGitHub):
        def create_pr(self, repo, *, title, body, head, base):
            assert head == "tester:foreshadow/entry-7"
            return super().create_pr(repo, title=title, body=body, head=head, base=base)

    port = Port()
    port.refs["main"] = "base"
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out["status"] == "SUBMITTED"


def test_retry_after_persisted_pr_binds_mission_before_return(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate
    from foreshadow.mission import load_mission_plan

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    fields = {**_fields(), "mission_id": mid}
    snapshot = create_snapshot(conn, user_id=uid, fields=fields)
    sid = persist_submission(
        conn,
        user_id=uid,
        mission_id=mid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
    )
    pr = {"number": 9, "html_url": "https://example/pr/9"}
    conn.execute(
        "UPDATE submissions SET status='SUBMITTED', result_json=? WHERE id=?",
        (json.dumps({"pr": pr}), sid),
    )
    conn.commit()

    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=FakeGitHub(),
        allow_real_remote=True,
    )
    plan = load_mission_plan(conn, mid, uid)
    assert out["resumed"] is True
    assert plan["status"] == "SUBMITTED"
    assert plan["bound_pr"]["number"] == 9


def _waiting_mission(tmp_home):
    from foreshadow.auth import ensure_local_user
    from foreshadow.db import connect, migrate

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, full_name, status, entry_path, difficulty, effort,
          plan_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            uid,
            "upstream/toy",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Easy",
            "1h",
            "{}",
            "now",
            "now",
        ),
    )
    mid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    fields = {**_fields(), "mission_id": mid}
    snapshot = create_snapshot(conn, user_id=uid, fields=fields)
    return conn, uid, mid, fields, snapshot


def _exact_port() -> FakeGitHub:
    port = FakeGitHub()
    port.refs["main"] = "base"
    return port


def test_submit_refuses_non_exact_upstream_with_zero_writes(tmp_home):
    conn, uid, _mid, fields, snapshot = _waiting_mission(tmp_home)
    port = _exact_port()
    port.refs["main"] = "moved"
    port.files = ["docs/README.md"]
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out["ok"] is False
    assert out["remote_writes"] == 0
    assert port.created_prs == 0
    assert port.pushes == []
    assert out["status"] != "SUBMITTED"


def test_submit_re_preflights_when_create_pr_not_finished(tmp_home):
    conn, uid, mid, fields, snapshot = _waiting_mission(tmp_home)
    sid = persist_submission(
        conn,
        user_id=uid,
        mission_id=mid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
    )
    conn.execute(
        "UPDATE submissions SET status='PUSH', steps_json=?, result_json=? WHERE id=?",
        (
            json.dumps(
                {
                    "PREFLIGHT": "DONE",
                    "FORK": "DONE",
                    "BRANCH": "DONE",
                    "PUSH": "DONE",
                    "CREATE_PR": "NOT_STARTED",
                    "PERSIST_RESULT": "NOT_STARTED",
                }
            ),
            json.dumps({"fork": "tester/toy", "preflight": {"ok": True, "status": "EXACT"}}),
            sid,
        ),
    )
    conn.commit()
    port = _exact_port()
    port.refs["main"] = "moved"
    port.files = ["queries/java/tags.scm"]
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out["ok"] is False
    assert out["remote_writes"] == 0
    assert port.created_prs == 0


def test_wrong_branch_sha_refuses_without_force_or_push(tmp_path):
    requests: list[tuple[str, str]] = []
    commands: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/git/ref/heads/foreshadow/entry-7"):
            return httpx.Response(
                200, json={"object": {"sha": "someone-elses-commit"}}
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def run_git(args: list[str], **_kwargs):
        commands.append(args)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
        git_runner=run_git,
    )
    with pytest.raises(RemoteWriteRefused, match="force-push is forbidden"):
        port.ensure_branch("operator/toy", "foreshadow/entry-7", "patch")
    assert commands == []
    assert not any(method != "GET" for method, _path in requests)


def test_approved_port_refuses_forbidden_http_mutations():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    forbidden = [
        ("POST", "/repos/upstream/toy/issues/1/comments"),
        ("POST", "/repos/upstream/toy/pulls/1/reviews"),
        ("POST", "/repos/upstream/toy/issues/1/reactions"),
        ("PUT", "/repos/upstream/toy/pulls/1/merge"),
        ("PATCH", "/repos/upstream/toy/git/refs/heads/x"),
        ("POST", "/graphql"),
        ("POST", "/evil/pulls"),
        ("DELETE", "/repos/upstream/toy/pulls/1"),
        ("POST", "/repos/upstream/toy/pulls/1/comments"),
    ]
    for method, path in forbidden:
        with pytest.raises(RemoteWriteRefused):
            port._api(method, path, json={})
    assert seen == []
    with pytest.raises(RemoteWriteRefused):
        assert_action_allowed("force_push")
    with pytest.raises(RemoteWriteRefused):
        assert_action_allowed("comment")
    with pytest.raises(RemoteWriteRefused):
        assert_action_allowed("review")
    with pytest.raises(RemoteWriteRefused):
        assert_action_allowed("reaction")
    with pytest.raises(RemoteWriteRefused):
        assert_action_allowed("merge")


def test_push_commit_does_not_inherit_radar_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "radar-token")
    monkeypatch.setenv("GH_TOKEN", "gh-token")
    captured: dict[str, object] = {}

    def run_git(args: list[str], **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env") or {}
        stdout = "base\n" if "rev-parse" in args else "patch HEAD\n"
        return type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    bundle = tmp_path / "patch.bundle"
    bundle.write_bytes(b"bundle")
    port = ApprovedGitHubPort(
        token="write-token",
        bundle_path=bundle,
        validated_base_sha="base",
        source_repo="upstream/toy",
        git_runner=run_git,
    )
    port.push_commit("operator/toy", "foreshadow/entry-7", "patch")
    env = captured["env"]
    assert isinstance(env, dict)
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert env.get("FORESHADOW_GIT_TOKEN") == "write-token"
    argv = " ".join(str(part) for part in captured["args"])
    assert "write-token" not in argv
    assert "radar-token" not in argv
    assert "--force" not in argv
    assert "https://github.com/operator/toy.git" in argv


def test_readiness_false_when_any_required_fact_is_false():
    from foreshadow.contribution.approval import compute_digest

    fields = _fields()
    snapshot = {**fields, "status": "current", "approval_digest": compute_digest(fields)}

    class ReadyPort(FakeGitHub):
        is_fake = False

        def transport_ready(self, sha):
            return True

        def credential_ready(self, repo):
            return True

    def assess(**overrides):
        review = {"status": "WAITING_USER_APPROVAL", "package": {}, **overrides}
        return board_api.assess_submission_readiness(
            review=review,
            fields=overrides.get("fields", fields),
            snapshot=overrides.get("snapshot", snapshot),
            port=overrides.get("port", ReadyPort()),
        )

    class NoTransport(ReadyPort):
        def transport_ready(self, sha):
            return False

    class NoCred(ReadyPort):
        def credential_ready(self, repo):
            return False

    class Boom(ReadyPort):
        def get_issue(self, repo, number):
            raise OSError("github unavailable")

    missing_transport = assess(port=NoTransport())
    assert missing_transport["approval_enabled"] is False
    assert missing_transport["display_status"] != "READY_FOR_HUMAN_SUBMIT"
    assert missing_transport["display_status"] == "WRITE_TRANSPORT_UNAVAILABLE"

    missing_cred = assess(port=NoCred())
    assert missing_cred["approval_enabled"] is False
    assert missing_cred["display_status"] == "CREDENTIAL_REQUIRED"

    unavailable = assess(port=Boom())
    assert unavailable["approval_enabled"] is False
    assert unavailable["display_status"] == "PREFLIGHT_UNAVAILABLE"

    unsafe = assess(
        fields={**fields, "maintainer_output_safety": "FAIL"},
        snapshot={
            **fields,
            "maintainer_output_safety": "FAIL",
            "status": "current",
            "approval_digest": compute_digest(
                {**fields, "maintainer_output_safety": "FAIL"}
            ),
        },
    )
    assert unsafe["approval_enabled"] is False
    assert unsafe["display_status"] != "READY_FOR_HUMAN_SUBMIT"

    not_waiting = assess(status="IMPLEMENTING")
    assert not_waiting["approval_enabled"] is False
    assert not_waiting["display_status"] != "READY_FOR_HUMAN_SUBMIT"

    incomplete = _fields()
    incomplete["patch_commit_sha"] = ""
    incomplete_snap = {
        **incomplete,
        "status": "current",
        "approval_digest": compute_digest(incomplete),
    }
    empty_sha = board_api.assess_submission_readiness(
        review={"status": "WAITING_USER_APPROVAL", "package": {}},
        fields=incomplete,
        snapshot=incomplete_snap,
        port=ReadyPort(),
    )
    assert empty_sha["approval_enabled"] is False
    assert empty_sha["display_status"] != "READY_FOR_HUMAN_SUBMIT"


def test_existing_pr_is_resumed_without_second_create(tmp_home):
    conn, uid, mid, fields, snapshot = _waiting_mission(tmp_home)
    sid = persist_submission(
        conn,
        user_id=uid,
        mission_id=mid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
    )
    conn.execute(
        "UPDATE submissions SET status='PUSH', steps_json=?, result_json=? WHERE id=?",
        (
            json.dumps(
                {
                    "PREFLIGHT": "DONE",
                    "FORK": "DONE",
                    "BRANCH": "DONE",
                    "PUSH": "DONE",
                    "CREATE_PR": "NOT_STARTED",
                    "PERSIST_RESULT": "NOT_STARTED",
                }
            ),
            json.dumps({"fork": "tester/toy"}),
            sid,
        ),
    )
    conn.commit()
    port = _exact_port()
    port.prs.append(
        {
            "number": 9,
            "html_url": "https://github.com/upstream/toy/pull/9",
            "head": "tester:foreshadow/entry-7",
            "base": "main",
        }
    )
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out["ok"] is True
    assert port.created_prs == 0
    assert out["pr"]["number"] == 9


def test_db_failure_after_pr_create_retries_without_second_pr(tmp_home, monkeypatch):
    from foreshadow.contribution import submit as submit_mod
    from foreshadow.mission import load_mission_plan

    conn, uid, mid, fields, snapshot = _waiting_mission(tmp_home)
    port = _exact_port()
    real_save = submit_mod._save
    failed = {"once": False}

    def flaky_save(connection, rec):
        if (
            rec["steps"].get("CREATE_PR") == "DONE"
            and rec["status"] == "CREATE_PR"
            and not failed["once"]
        ):
            failed["once"] = True
            raise sqlite3.OperationalError("disk I/O error")
        return real_save(connection, rec)

    monkeypatch.setattr(submit_mod, "_save", flaky_save)
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        submit_approved(
            conn,
            user_id=uid,
            snapshot_id=int(snapshot["approval_snapshot_id"]),
            current_fields=fields,
            port=port,
            allow_real_remote=True,
        )
    assert port.created_prs == 1
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    plan = load_mission_plan(conn, mid, uid)
    assert out["ok"] is True
    assert port.created_prs == 1
    assert plan["bound_pr"]["number"] == 99


def test_branch_already_at_approved_sha_does_not_force(tmp_path):
    commands: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/git/ref/heads/foreshadow/entry-7"):
            return httpx.Response(200, json={"object": {"sha": "patch"}})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def run_git(args: list[str], **_kwargs):
        commands.append(args)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
        git_runner=run_git,
    )
    assert port.ensure_branch("operator/toy", "foreshadow/entry-7", "patch") == "patch"
    assert commands == []
    assert "--force" not in " ".join(part for command in commands for part in command)


def test_find_pr_qualifies_head_and_ignores_unrelated_open_pr():
    """GitHub only filters pulls when head is owner:branch. An unqualified
    branch must not bind whatever open PR happens to be first."""
    queries: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/repos/upstream/toy/pulls":
            queries.append({k: v for k, v in request.url.params.multi_items()})
            head = request.url.params.get("head")
            unrelated = {
                "number": 1,
                "html_url": "https://github.com/upstream/toy/pull/1",
                "head": {
                    "ref": "other-branch",
                    "sha": "not-the-approved-sha",
                    "label": "upstream:other-branch",
                },
                "base": {"ref": "main"},
            }
            approved = {
                "number": 9,
                "html_url": "https://github.com/upstream/toy/pull/9",
                "head": {
                    "ref": "foreshadow/entry-7",
                    "sha": "patch",
                    "label": "upstream:foreshadow/entry-7",
                },
                "base": {"ref": "main"},
            }
            if head == "upstream:foreshadow/entry-7":
                return httpx.Response(200, json=[approved])
            return httpx.Response(200, json=[unrelated, approved])
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    port = ApprovedGitHubPort(
        token="test-token",
        client=httpx.Client(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    found = port.find_pr(
        "upstream/toy", head="foreshadow/entry-7", base="main"
    )
    assert found is not None
    assert found["number"] == 9
    assert queries and queries[0].get("head") == "upstream:foreshadow/entry-7"


def test_same_owner_submit_does_not_bind_unrelated_open_pr(tmp_home):
    conn, uid, _mid, fields, snapshot = _waiting_mission(tmp_home)

    class SameOwner(FakeGitHub):
        def ensure_fork(self, repo):
            self.calls.append(f"ensure_fork:{repo}")
            return repo

        def find_pr(self, repo, *, head, base):
            self.calls.append(f"find_pr:{head}")
            assert head == "upstream:foreshadow/entry-7"
            return super().find_pr(repo, head=head, base=base)

    port = SameOwner()
    port.refs["main"] = "base"
    port.prs.append(
        {
            "number": 1,
            "html_url": "https://github.com/upstream/toy/pull/1",
            "head": "upstream:other-branch",
            "base": "main",
            "head_sha": "not-the-approved-sha",
        }
    )
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snapshot["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert out["ok"] is True
    assert out["pr"]["number"] == 99
    assert port.created_prs == 1
    assert "find_pr:upstream:foreshadow/entry-7" in port.calls
