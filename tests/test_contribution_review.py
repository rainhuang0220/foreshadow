"""Contribution Review authority: active vs history, package snapshot, escaping."""

from __future__ import annotations

import json

from foreshadow.auth import ensure_local_user
from foreshadow.contribution.executor import ContributionJob, JobStatus
from foreshadow.contribution.jobs import persist_artifact, persist_job
from foreshadow.db import connect, migrate


def _pkg(
    *,
    issue: int,
    title: str,
    diff: str,
    files: list[str],
    added: int = 4,
    deleted: int = 0,
    body: str = "Closes the issue.",
) -> dict:
    return {
        "repository": "vshulcz/deja-vu",
        "related_issue": f"#{issue}",
        "issue_url": f"https://github.com/vshulcz/deja-vu/issues/{issue}",
        "pr_title": title,
        "pr_body": body,
        "diff": diff,
        "files_changed": files,
        "files_changed_n": len(files),
        "tests": {
            "ok": True,
            "commands": [
                {
                    "command": "go test ./internal/index -count=1",
                    "ok": True,
                    "returncode": 0,
                    "duration_s": 1.2,
                    "log": "ok",
                }
            ],
            "duration_s": 1.2,
            "exit_code": 0,
            "command": "go test ./internal/index -count=1",
            "log": "ok",
        },
        "qa": "PASS",
        "qa_ok": True,
        "qa_reasons": [],
        "remote_writes": 0,
        "remote_status": "WAITING_USER_APPROVAL",
        "status": "WAITING_USER_APPROVAL",
        "implementation": {
            "mode": "autonomous_executor",
            "backend": "mini_swe_agent",
            "clean_before": True,
            "model": "openai/deepseek-v4-pro",
            "pre_tree_hash": "abc",
            "upstream_head": "def",
        },
        "entry_revision": "rev-1",
        "diff_stat_hint": {"added": added, "deleted": deleted},
    }


DIFF_1551 = """diff --git a/internal/index/friction.go b/internal/index/friction.go
--- a/internal/index/friction.go
+++ b/internal/index/friction.go
@@ -1,2 +1,3 @@
 keep
+undefined symbol
diff --git a/internal/index/friction_phrases_test.go b/internal/index/friction_phrases_test.go
--- a/internal/index/friction_phrases_test.go
+++ b/internal/index/friction_phrases_test.go
@@ -1,1 +1,2 @@
 keep
+ld: undefined symbol
"""

DIFF_1828 = """diff --git a/cmd/deja/doctor.go b/cmd/deja/doctor.go
--- a/cmd/deja/doctor.go
+++ b/cmd/deja/doctor.go
@@ -1,1 +1,2 @@
 keep
+grok plugin
"""


def _mission(conn, uid, full_name, issue, title, *, now="2026-09-08T00:00:00+00:00"):
    plan = {
        "preferred_issue": issue,
        "cited_issue": {"number": issue, "title": title},
        "entry_source": "HUMAN_CONFIRM",
        "active_entry_target": {"issue_number": issue, "title": title},
        "entry_strategy": {"recommended": {"issue_number": issue, "title": title}},
        "historical_entry": None,
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
            full_name,
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Medium",
            "4h",
            json.dumps(plan),
            None,
            now,
            now,
        ),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _job_pkg(
    conn, uid, full_name, pkg, *, backend="mini_swe_agent", status=JobStatus.ready
):
    job = ContributionJob(
        user_id=uid,
        full_name=full_name,
        backend=backend,
        status=status,
        task={
            "structured": {"issue_number": int(str(pkg["related_issue"]).lstrip("#"))}
        },
    )
    persist_job(conn, job)
    persist_artifact(conn, int(job.id), kind="package", body=json.dumps(pkg))
    return int(job.id)


def _seed_deja(conn, uid):
    m1 = _mission(conn, uid, "vshulcz/deja-vu", 1828, "stale Grok plugin")
    j1 = _job_pkg(
        conn,
        uid,
        "vshulcz/deja-vu",
        _pkg(
            issue=1828,
            title="fix(doctor): report a stale Grok plugin (#1828)",
            diff=DIFF_1828,
            files=["cmd/deja/doctor.go"],
            added=1,
        ),
        backend="workspace",
    )
    m2 = _mission(conn, uid, "vshulcz/deja-vu", 1551, "undefined symbol")
    j2 = _job_pkg(
        conn,
        uid,
        "vshulcz/deja-vu",
        _pkg(
            issue=1551,
            title="Fix undefined symbol (#1551)",
            diff=DIFF_1551,
            files=[
                "internal/index/friction.go",
                "internal/index/friction_phrases_test.go",
            ],
        ),
    )
    return m1, j1, m2, j2


def test_active_contribution_is_latest_mission_not_discovery(tmp_home):
    from foreshadow.contribution.review import active_contribution, history_for_repo

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    _seed_deja(conn, uid)
    conn.execute(
        "INSERT INTO repos(full_name) VALUES ('vshulcz/deja-vu')"
        if False
        else "SELECT 1"
    )
    active = active_contribution(conn, uid, "vshulcz/deja-vu")
    assert active is not None
    assert active["issue_number"] == 1551
    assert active["mission_id"] > 0
    assert "#308" not in str(active.get("title") or "")
    assert active["issue_number"] != 308
    hist = history_for_repo(conn, uid, "vshulcz/deja-vu")
    issues = [h["issue_number"] for h in hist]
    assert 1551 in issues and 1828 in issues
    assert issues[0] == 1551
    assert 308 not in issues


def test_historical_mission_does_not_leak_active_diff(tmp_home):
    from foreshadow.contribution.review import contribution_for_mission

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    m1, _, m2, _ = _seed_deja(conn, uid)
    old = contribution_for_mission(conn, uid, m1)
    new = contribution_for_mission(conn, uid, m2)
    assert old["issue_number"] == 1828
    assert new["issue_number"] == 1551
    assert "friction.go" not in old["diff"]
    assert "doctor.go" not in new["diff"]
    assert "friction.go" in new["diff"]


def test_package_snapshot_ignores_later_worktree_edits(tmp_home):
    from foreshadow.contribution.review import contribution_for_mission

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    _, _, m2, _ = _seed_deja(conn, uid)
    work = tmp_home / "dirty-worktree"
    work.mkdir()
    (work / "internal").mkdir()
    (work / "internal" / "index").mkdir(parents=True)
    (work / "internal" / "index" / "friction.go").write_text(
        "CHANGED IN WORKTREE after package\n", encoding="utf-8"
    )
    review = contribution_for_mission(conn, uid, m2, worktree=work)
    assert "CHANGED IN WORKTREE" not in review["diff"]
    assert "undefined symbol" in review["diff"]
    assert review["authority"] == "package"


def test_latest_package_artifact_wins(tmp_home):
    from foreshadow.contribution.review import contribution_for_mission

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    m2 = _mission(conn, uid, "vshulcz/deja-vu", 1551, "undefined symbol")
    job = ContributionJob(
        user_id=uid,
        full_name="vshulcz/deja-vu",
        backend="mini_swe_agent",
        status=JobStatus.ready,
        task={"structured": {"issue_number": 1551}},
    )
    persist_job(conn, job)
    persist_artifact(
        conn,
        int(job.id),
        kind="package",
        body=json.dumps(_pkg(issue=1551, title="OLD", diff="OLD_DIFF", files=["a.go"])),
    )
    persist_artifact(
        conn,
        int(job.id),
        kind="package",
        body=json.dumps(
            _pkg(
                issue=1551,
                title="NEW",
                diff=DIFF_1551,
                files=["internal/index/friction.go"],
            )
        ),
    )
    review = contribution_for_mission(conn, uid, m2)
    assert review["pr_title"] == "NEW"
    assert "OLD_DIFF" not in review["diff"]


def test_diff_parser_and_html_escape_script_tags():
    from foreshadow.contribution.review import escape_text, parse_unified_diff

    raw = """diff --git a/evil.go b/evil.go
--- a/evil.go
+++ b/evil.go
@@ -1,1 +1,2 @@
 keep
+<script>alert(1)</script>
"""
    parsed = parse_unified_diff(raw)
    assert parsed["files"][0]["path"] == "evil.go"
    assert parsed["added"] == 1
    html = escape_text(raw)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_no_active_mission_returns_none(tmp_home):
    from foreshadow.contribution.review import active_contribution

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    assert active_contribution(conn, uid, "acme/none") is None


def test_pr_and_checks_come_from_package(tmp_home):
    from foreshadow.contribution.review import checks_view, pr_draft

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    _, _, m2, _ = _seed_deja(conn, uid)
    pr = pr_draft(conn, uid, m2)
    assert pr["title"].startswith("Fix undefined symbol")
    assert "Closes" in pr["body"]
    assert pr["submitted"] is False
    assert pr["remote_writes"] == 0
    checks = checks_view(conn, uid, m2)
    assert checks["tests"][0]["ok"] is True
    assert checks["qa"]["verdict"] == "PASS"
    assert checks["remote"]["remote_writes"] == 0
    assert checks["provenance"]["mode"] == "autonomous_executor"


def test_webapp_has_review_workspace_chrome():
    from foreshadow.board.webapp import APP_HTML

    assert "WAITING FOR YOUR REVIEW" in APP_HTML
    assert "reviewTab" in APP_HTML
    assert "function reviewWorkspace" in APP_HTML
    assert "function renderUnifiedDiff" in APP_HTML
    assert "function reviewQueueView" in APP_HTML
    assert "review_queue" in APP_HTML
    assert "Approval workflow not enabled yet" in APP_HTML
    assert "max-width: 320px" in APP_HTML
    assert "Raw patch" in APP_HTML


def test_discovery_recommendation_is_not_active_title(tmp_home):
    from foreshadow.contribution.review import (
        active_contribution,
        attach_review_summaries,
    )

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    plan = {
        "preferred_issue": 1551,
        "cited_issue": {"number": 1551, "title": "undefined symbol is not friction"},
        "entry_source": "HUMAN_CONFIRM",
        "active_entry_target": {
            "issue_number": 1551,
            "title": "undefined symbol is not friction",
        },
        "entry_strategy": {
            "recommended": {"issue_number": 308, "title": "stale discovery docs #308"}
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
            "ISSUE",
            "Medium",
            "4h",
            json.dumps(plan),
            None,
            "2026-09-08T00:00:00+00:00",
            "2026-09-08T00:00:00+00:00",
        ),
    )
    conn.commit()
    _job_pkg(
        conn,
        uid,
        "vshulcz/deja-vu",
        _pkg(
            issue=1551,
            title="Fix undefined symbol (#1551)",
            diff=DIFF_1551,
            files=[
                "internal/index/friction.go",
                "internal/index/friction_phrases_test.go",
            ],
        ),
    )
    active = active_contribution(conn, uid, "vshulcz/deja-vu")
    assert active["issue_number"] == 1551
    assert "308" not in str(active["title"])
    assert "undefined symbol" in active["title"]
    payload = {
        "candidates": [
            {
                "full_name": "vshulcz/deja-vu",
                "entry": {"recommended": {"issue_number": 308, "title": "docs pass"}},
            }
        ]
    }
    attach_review_summaries(payload, conn, uid)
    assert payload["candidates"][0]["review"]["issue_number"] == 1551
    assert payload["candidates"][0]["entry"]["recommended"]["issue_number"] == 1551
    assert payload["review_queue"][0]["review"]["issue_number"] == 1551
    assert 308 not in [
        item["review"]["issue_number"] for item in payload["review_queue"]
    ]


def test_review_queue_includes_repo_absent_from_shortlist(tmp_home):
    from foreshadow.contribution.review import attach_review_summaries

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    _seed_deja(conn, uid)
    payload = {"candidates": [{"full_name": "acme/other"}]}
    attach_review_summaries(payload, conn, uid)
    assert "review" not in payload["candidates"][0]
    assert payload["review_queue"][0]["full_name"] == "vshulcz/deja-vu"
    assert payload["review_queue"][0]["review"]["issue_number"] == 1551


def test_later_job_package_wins_over_older_failed_same_issue(tmp_home):
    from foreshadow.contribution.executor import JobStatus
    from foreshadow.contribution.review import contribution_for_mission

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    mid = _mission(conn, uid, "vshulcz/deja-vu", 1551, "undefined symbol")
    _job_pkg(
        conn,
        uid,
        "vshulcz/deja-vu",
        _pkg(
            issue=1551,
            title="OLD FAIL",
            diff="OLD_FAIL_DIFF",
            files=["internal/index/friction.go"],
        ),
        backend="mini_swe_agent",
        status=JobStatus.failed,
    )
    j2 = _job_pkg(
        conn,
        uid,
        "vshulcz/deja-vu",
        _pkg(
            issue=1551,
            title="NEW PASS",
            diff=DIFF_1551,
            files=[
                "internal/index/friction.go",
                "internal/index/friction_phrases_test.go",
            ],
        ),
    )
    review = contribution_for_mission(conn, uid, mid)
    assert review["job_id"] == j2
    assert review["pr_title"] == "NEW PASS"
    assert "OLD_FAIL_DIFF" not in review["diff"]


def test_pr_markdown_escapes_html():
    from foreshadow.contribution.review import render_pr_markdown

    html = render_pr_markdown("Hi <script>alert(1)</script>\n\n## Title")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<h2>Title</h2>" in html


def test_review_http_endpoints_and_board_priority(tmp_home, frozen_clock):
    import httpx

    from test_board_server import _run_server

    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        anon = httpx.get(f"{base}/api/contribution/review?full_name=vshulcz/deja-vu")
        assert anon.status_code == 401
        client = httpx.Client()
        reg = client.post(
            f"{base}/api/register",
            json={
                "username": "reviewer",
                "email": "reviewer@example.com",
                "password": "password1",
            },
        )
        assert reg.status_code == 200
        uid = int(client.get(f"{base}/api/me").json()["user"]["id"])
        conn = connect(tmp_home / "foreshadow.sqlite3")
        migrate(conn)
        m1, _, m2, _ = _seed_deja(conn, uid)
        board = client.get(f"{base}/api/board").json()
        queue = board["review_queue"]
        assert queue[0]["full_name"] == "vshulcz/deja-vu"
        assert queue[0]["review"]["issue_number"] == 1551
        acme = next(c for c in board["candidates"] if c["full_name"] == "acme/x")
        assert not acme.get("review")
        missing = client.get(f"{base}/api/contribution/review?full_name=acme/x")
        assert missing.status_code == 404
        assert missing.json().get("review") is None
        active = client.get(
            f"{base}/api/contribution/review?full_name=vshulcz/deja-vu"
        ).json()
        assert active["review"]["issue_number"] == 1551
        assert "package" not in active["review"]
        assert active["review"].get("raw_package")
        hist_1828 = client.get(f"{base}/api/contribution/diff?mission_id={m1}").json()
        hist_1551 = client.get(f"{base}/api/contribution/diff?mission_id={m2}").json()
        assert "doctor.go" in hist_1828["diff"]
        assert "friction.go" not in hist_1828["diff"]
        assert "friction.go" in hist_1551["diff"]
        assert "doctor.go" not in hist_1551["diff"]
        pr = client.get(f"{base}/api/contribution/pr?mission_id={m2}").json()
        assert pr["title"].startswith("Fix undefined symbol")
        assert pr["remote_writes"] == 0
        checks = client.get(f"{base}/api/contribution/checks?mission_id={m2}").json()
        assert checks["qa"]["verdict"] == "PASS"
        assert checks["remote"]["remote_writes"] == 0
        assert checks["remote"]["push"] == "blocked"
        assert checks["remote"]["pr"] == "blocked"
    finally:
        httpd.shutdown()
