"""Two-gate contribution: mission identity, approval, mocked submit, #74 import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from foreshadow.auth import ensure_local_user
from foreshadow.contribution.approval import (
    BLOCKED_REMOTE_ACTIONS,
    compute_digest,
    create_snapshot,
    current_snapshot,
    fields_from_review,
    matches_package,
    snapshot_fields,
)
from foreshadow.contribution.board_api import execute_gate2, submit_preview
from foreshadow.contribution.executor import ContributionJob, JobStatus
from foreshadow.contribution.gates import authorize_entry, run_autonomous_local
from foreshadow.contribution.identity import pick_active_for_repo, require_mission_id
from foreshadow.contribution.import_store import (
    import_validated_contribution,
    sha256_text,
)
from foreshadow.contribution.jobs import persist_artifact, persist_job
from foreshadow.contribution.preflight import classify_delta, run_preflight
from foreshadow.contribution.reconcile import reconcile_mission
from foreshadow.contribution.review import (
    attach_review_summaries,
    contribution_for_mission,
)
from foreshadow.contribution.submit import FakeGitHub, refuse, submit_approved
from foreshadow.db import SCHEMA_VERSION, connect, migrate
from foreshadow.mission import ALLOWED, create_for_user, load_mission_plan


def _conn(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    return conn, uid


def _fields(**overrides):
    base = snapshot_fields(
        mission_id=1,
        repository="acme/toy",
        issue_number=7,
        issue_url="https://github.com/acme/toy/issues/7",
        base_repo="acme/toy",
        base_branch="main",
        validated_base_sha="aaa",
        patch_commit_sha="bbb",
        diff_sha256="ccc",
        branch_name="foreshadow/entry",
        pr_title="Fix it",
        pr_body="Closes #7",
        test_evidence_digest="ddd",
        qa_verdict="PASS",
        maintainer_output_safety="PASS",
        freshness="EXACT",
    )
    base.update(overrides)
    return base


def _mission(conn, uid, repo, issue, status="WAITING_USER_APPROVAL", title="t"):
    plan = {
        "repository": repo,
        "issue_number": issue,
        "issue_url": f"https://github.com/{repo}/issues/{issue}",
        "preferred_issue": issue,
        "cited_issue": {"number": issue, "title": title},
        "active_entry_target": {"issue_number": issue, "title": title},
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
            repo,
            status,
            "ISSUE",
            "Medium",
            "4h",
            json.dumps(plan),
            None,
            "2026-09-11T00:00:00+00:00",
            "2026-09-11T00:00:00+00:00",
        ),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _pkg(repo, issue, title, diff, body="Closes the issue."):
    return {
        "repository": repo,
        "related_issue": f"#{issue}",
        "issue_url": f"https://github.com/{repo}/issues/{issue}",
        "pr_title": title,
        "pr_body": body,
        "diff": diff,
        "diff_sha256": sha256_text(diff),
        "files_changed": ["x"],
        "files_changed_n": 1,
        "validated_base_sha": "aaa",
        "patch_commit_sha": "bbb",
        "freshness": "EXACT",
        "tests": {"ok": True, "commands": [{"command": "true", "ok": True}]},
        "qa": "PASS",
        "qa_ok": True,
        "remote_writes": 0,
        "status": "WAITING_USER_APPROVAL",
        "implementation": {"branch": "foreshadow/entry", "upstream_head": "aaa"},
    }


def _job(conn, uid, repo, pkg, mission_id=None):
    job = ContributionJob(
        user_id=uid,
        full_name=repo,
        backend="native",
        status=JobStatus.ready,
        mission_id=mission_id,
        task={"structured": {"issue_number": int(str(pkg["related_issue"]).lstrip("#"))}},
    )
    persist_job(conn, job)
    persist_artifact(conn, int(job.id), kind="package", body=json.dumps(pkg))
    return int(job.id)


def test_schema_is_nine(tmp_home):
    conn, _ = _conn(tmp_home)
    assert SCHEMA_VERSION == 9
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "approval_snapshots" in tables
    assert "submissions" in tables
    cols = [r[1] for r in conn.execute("PRAGMA table_info(contribution_jobs)")]
    assert "mission_id" in cols


def test_multiple_missions_same_repo_are_distinct(tmp_home):
    conn, uid = _conn(tmp_home)
    a = _mission(conn, uid, "vshulcz/deja-vu", 1828)
    b = _mission(conn, uid, "vshulcz/deja-vu", 1551, status="MERGED")
    items = [
        {"id": a, "full_name": "vshulcz/deja-vu", "status": "WAITING_USER_APPROVAL", "issue_number": 1828},
        {"id": b, "full_name": "vshulcz/deja-vu", "status": "MERGED", "issue_number": 1551},
    ]
    active = pick_active_for_repo(items)
    assert active["id"] == a
    found = require_mission_id(items, full_name="vshulcz/deja-vu", mission_id=b)
    assert found["id"] == b
    found = require_mission_id(items, full_name="vshulcz/deja-vu", issue_number=1828)
    assert found["id"] == a
    with pytest.raises(LookupError, match="pass --mission-id"):
        require_mission_id(items, full_name="vshulcz/deja-vu", mission_id=None)


def test_merged_sibling_does_not_hide_waiting(tmp_home):
    conn, uid = _conn(tmp_home)
    m1828 = _mission(conn, uid, "vshulcz/deja-vu", 1828)
    m1551 = _mission(conn, uid, "vshulcz/deja-vu", 1551, status="MERGED")
    _job(conn, uid, "vshulcz/deja-vu", _pkg("vshulcz/deja-vu", 1828, "old", "diff --git a/a b/a\n"), m1828)
    _job(conn, uid, "vshulcz/deja-vu", _pkg("vshulcz/deja-vu", 1551, "merged", "diff --git a/b b/b\n"), m1551)
    payload = {"candidates": []}
    attach_review_summaries(payload, conn, uid)
    issues = [q["issue_number"] for q in payload["review_queue"]]
    assert 1828 in issues
    assert 1551 not in issues


def test_gate1_starts_local_automation_without_extra_approval(tmp_home):
    conn, uid = _conn(tmp_home)
    out = authorize_entry(
        conn,
        user_id=uid,
        full_name="acme/toy",
        data_dir=tmp_home,
        issue_number=9,
        live=False,
        contribute=False,
    )
    assert out["gate"] == 1
    assert out["status"] == "WAITING_USER_APPROVAL"
    assert out["remote_writes"] == 0
    events = [
        r[0]
        for r in conn.execute(
            "SELECT event FROM contribution_events WHERE user_id=?", (uid,)
        )
    ]
    assert "draft_approved" not in events
    assert "user_submitted" not in events


def test_local_phases_do_not_require_approval(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 3, status="MISSION_READY")
    seen = run_autonomous_local(conn, user_id=uid, mission_id=mid)
    assert seen == [
        "INVESTIGATING",
        "REPRODUCING",
        "IMPLEMENTING",
        "VALIDATING",
        "PACKAGING",
        "WAITING_USER_APPROVAL",
    ]


def test_package_ends_waiting_user_approval(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 4)
    _job(conn, uid, "acme/toy", _pkg("acme/toy", 4, "fix", "diff --git a/x b/x\n"), mid)
    review = contribution_for_mission(conn, uid, mid)
    assert review["display_status"] == "READY_FOR_HUMAN_SUBMIT"
    assert review["approval_enabled"] is True
    assert review["approval_digest"]


def test_approval_snapshot_immutable_and_invalidation(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 7)
    fields = _fields(mission_id=mid)
    snap = create_snapshot(conn, user_id=uid, fields=fields)
    assert matches_package(snap, fields)
    digest = snap["approval_digest"]
    assert digest == compute_digest(fields)
    changed = dict(fields)
    changed["diff_sha256"] = "zzz"
    assert not matches_package(snap, changed)
    changed = dict(fields)
    changed["pr_body"] = "mutated"
    assert not matches_package(snap, changed)
    changed = dict(fields)
    changed["validated_base_sha"] = "other"
    assert not matches_package(snap, changed)
    changed = dict(fields)
    changed["pr_title"] = "other title"
    assert not matches_package(snap, changed)


def test_preflight_before_first_write_and_stale_upstream(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 7)
    fields = _fields(mission_id=mid)
    snap = create_snapshot(conn, user_id=uid, fields=fields)
    port = FakeGitHub()
    port.refs["main"] = "aaa"
    pre = run_preflight(port, snap, current_fields=fields)
    assert pre["ok"] is True
    assert "ensure_fork" not in "".join(port.calls)
    port.refs["main"] = "newer"
    port.files = ["queries/java/tags.scm"]
    blocked = run_preflight(port, snap, current_fields=fields)
    assert blocked["ok"] is False
    assert blocked["status"] == "NEEDS_REFRESH"
    assert blocked["remote_writes"] == 0
    port.files = ["docs/README.md"]
    docs = run_preflight(port, snap, current_fields=fields)
    assert docs["ok"] is True
    assert docs["delta_classification"] == "DOCS_ONLY"


def test_classify_delta_non_overlap():
    assert classify_delta(["present/deck.js"]) == "NON_OVERLAPPING"
    assert classify_delta([]) == "IDENTICAL"
    assert classify_delta(["src/foo.c"], patch_files=["src/foo.c"]) == "CONFLICT_SENSITIVE"


def test_import_does_not_reuse_merged(tmp_home):
    store = _mini_store(tmp_home)
    conn, uid = _conn(tmp_home)
    first = import_validated_contribution(
        conn, user_id=uid, store=store, data_dir=tmp_home
    )
    mid = first["mission_id"]
    conn.execute("UPDATE entry_missions SET status='MERGED' WHERE id=?", (mid,))
    conn.commit()
    again = import_validated_contribution(
        conn, user_id=uid, store=store, data_dir=tmp_home
    )
    assert again["mission_id"] != mid
    row = conn.execute(
        "SELECT status FROM entry_missions WHERE id=?", (again["mission_id"],)
    ).fetchone()
    assert row[0] == "WAITING_USER_APPROVAL"


def test_merged_mission_cannot_submit(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 14, status="MERGED")
    _job(conn, uid, "acme/toy", _pkg("acme/toy", 14, "Fix it", "diff --git a/x b/x\n+hi\n", body="Closes #14"), mid)
    out = execute_gate2(
        conn, user_id=uid, mission_id=mid, snapshot_id=None, confirm=True, port=FakeGitHub()
    )
    assert out["ok"] is False
    assert out["remote_writes"] == 0
    assert out["status"] == "NOT_WAITING_APPROVAL"


def test_remote_allowlist_and_blocks():
    assert "comment" in BLOCKED_REMOTE_ACTIONS
    assert "review" in BLOCKED_REMOTE_ACTIONS
    assert "merge" in BLOCKED_REMOTE_ACTIONS
    assert "force_push" in BLOCKED_REMOTE_ACTIONS
    assert refuse("comment")["remote_writes"] == 0
    assert refuse("create_pr")["status"] == "REMOTE_WRITE_REFUSED"


def test_submit_without_gate2_is_zero_writes(tmp_home):
    conn, uid = _conn(tmp_home)
    assert refuse("fork")["remote_writes"] == 0
    mid = _mission(conn, uid, "acme/toy", 8)
    _job(conn, uid, "acme/toy", _pkg("acme/toy", 8, "fix", "diff --git a/x b/x\n"), mid)
    preview = submit_preview(conn, uid, mid)
    assert preview["remote_writes"] == 0
    assert preview["confirm_required"] is True


def test_idempotent_fake_submit_no_duplicate_pr(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 11)
    pkg = _pkg("acme/toy", 11, "Fix it", "diff --git a/x b/x\n+hi\n", body="Closes #11")
    _job(conn, uid, "acme/toy", pkg, mid)
    review = contribution_for_mission(conn, uid, mid)
    fields = fields_from_review(review, mission_id=mid)
    snap = current_snapshot(conn, user_id=uid, mission_id=mid)
    assert snap is not None
    port = FakeGitHub()
    port.refs["main"] = fields["validated_base_sha"]
    first = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snap["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert first["ok"] is True
    assert port.created_prs == 1
    second = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snap["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert second["ok"] is True
    assert port.created_prs == 1
    assert second["pr"]["number"] == first["pr"]["number"]


def test_stale_package_blocks_submit(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 7)
    fields = _fields(mission_id=mid)
    snap = create_snapshot(conn, user_id=uid, fields=fields)
    port = FakeGitHub()
    out = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snap["approval_snapshot_id"]),
        current_fields={**fields, "pr_body": "changed after approval"},
        port=port,
        allow_real_remote=True,
    )
    assert out["ok"] is False
    assert out["remote_writes"] == 0
    assert port.created_prs == 0


def test_bound_pr_merged_and_1551_regression(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "vshulcz/deja-vu", 1551, status="WAITING_MAINTAINER")
    conn.execute(
        "UPDATE entry_missions SET plan_json=? WHERE id=?",
        (
            json.dumps(
                {
                    "full_name": "vshulcz/deja-vu",
                    "issue_number": 1551,
                    "bound_pr": {
                        "number": 3419,
                        "html_url": "https://github.com/vshulcz/deja-vu/pull/3419",
                    },
                }
            ),
            mid,
        ),
    )
    conn.commit()

    class Reader:
        def get_pull(self, repo, number):
            assert repo == "vshulcz/deja-vu"
            assert number == 3419
            return {"number": 3419, "merged": True, "state": "closed"}

    out = reconcile_mission(conn, user_id=uid, mission_id=mid, reader=Reader())
    assert out["changed"] is True
    row = conn.execute("SELECT status FROM entry_missions WHERE id=?", (mid,)).fetchone()
    assert row[0] == "MERGED"


def test_gate2_only_from_waiting(tmp_home):
    assert "SUBMITTED" in ALLOWED["WAITING_USER_APPROVAL"]
    for src, dests in ALLOWED.items():
        if src != "WAITING_USER_APPROVAL":
            assert "SUBMITTED" not in dests
    assert "MERGED" in ALLOWED["WAITING_MAINTAINER"]
    assert "SUBMITTED" not in ALLOWED["PAUSED"]


def test_ripwire74_import_appears_on_board(tmp_home):
    store = _mini_store(tmp_home)
    conn, uid = _conn(tmp_home)
    out = import_validated_contribution(
        conn, user_id=uid, store=store, data_dir=tmp_home
    )
    assert out["imported"] is True
    mid = out["mission_id"]
    review = contribution_for_mission(conn, uid, mid)
    assert review["repository"] == "redhat-et/ripwire"
    assert review["issue_number"] == 74
    assert review["display_status"] == "READY_FOR_HUMAN_SUBMIT"
    assert "/tmp/" not in str(review.get("persistent_store") or "")
    assert "提交到 GitHub" in review["next_action"]
    payload = {"candidates": []}
    attach_review_summaries(payload, conn, uid)
    assert any(q["issue_number"] == 74 for q in payload["review_queue"])
    again = import_validated_contribution(
        conn, user_id=uid, store=store, data_dir=tmp_home
    )
    assert again["reused"] is True
    assert again["mission_id"] == mid


def test_webapp_two_gate_chrome():
    from foreshadow.board.webapp import APP_HTML

    assert "提交到 GitHub" in APP_HTML
    assert "你审核的是这一版" in APP_HTML
    assert "将执行：" in APP_HTML
    assert "不会执行：" in APP_HTML
    assert "function confirmSubmit" in APP_HTML
    assert "Approval workflow not enabled yet" not in APP_HTML
    assert ">进入<" in APP_HTML
    assert "openCard('${esc(c.full_name)}', ${esc(c.mission_id" in APP_HTML
    assert "startContribution(name, data.mission.id)" in APP_HTML
    assert "mission_id: mid" in APP_HTML
    assert "if (state.busy) return" in APP_HTML
    assert "terminal && currentOpen" in APP_HTML


def test_ambiguous_gate1_without_issue_raises(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    conn, uid = _conn(tmp_home)
    _mission(conn, uid, "acme/toy", 1)
    mid2 = _mission(conn, uid, "acme/toy", 2)
    with pytest.raises(ValueError, match="pass issue_number"):
        create_for_user(conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home)
    reused = create_for_user(
        conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home, issue_number=2
    )
    assert reused.id == mid2
    plan = load_mission_plan(conn, int(reused.id), uid)
    assert plan is not None
    assert plan["issue_number"] == 2


def test_ai_attribution_blocks_gate2(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 12)
    pkg = _pkg(
        "acme/toy",
        12,
        "Fix it",
        "diff --git a/x b/x\n+hi\n",
        body="Closes #12. Generated by Cursor.",
    )
    _job(conn, uid, "acme/toy", pkg, mid)
    review = contribution_for_mission(conn, uid, mid)
    fields = fields_from_review(review, mission_id=mid)
    assert fields["maintainer_output_safety"] == "FAIL"
    out = execute_gate2(
        conn,
        user_id=uid,
        mission_id=mid,
        snapshot_id=None,
        confirm=True,
        port=FakeGitHub(),
    )
    assert out["ok"] is False
    assert out["remote_writes"] == 0
    assert out["status"] == "MAINTAINER_OUTPUT_UNSAFE"


def test_submit_short_circuits_when_already_submitted(tmp_home):
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "acme/toy", 13)
    pkg = _pkg("acme/toy", 13, "Fix it", "diff --git a/x b/x\n+hi\n", body="Closes #13")
    _job(conn, uid, "acme/toy", pkg, mid)
    review = contribution_for_mission(conn, uid, mid)
    fields = fields_from_review(review, mission_id=mid)
    snap = current_snapshot(conn, user_id=uid, mission_id=mid)
    port = FakeGitHub()
    port.refs["main"] = fields["validated_base_sha"]
    first = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snap["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert first["ok"] is True
    pushes = len(port.pushes)
    created = port.created_prs
    second = submit_approved(
        conn,
        user_id=uid,
        snapshot_id=int(snap["approval_snapshot_id"]),
        current_fields=fields,
        port=port,
        allow_real_remote=True,
    )
    assert second["ok"] is True
    assert second.get("resumed") is True
    assert second["remote_writes"] == 0
    assert len(port.pushes) == pushes
    assert port.created_prs == created


def test_execute_gate2_without_write_token_is_zero(tmp_home, monkeypatch):
    monkeypatch.delenv("FORESHADOW_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("FORESHADOW_SUBMIT_FAKE", raising=False)
    conn, uid = _conn(tmp_home)
    mid = _mission(conn, uid, "redhat-et/ripwire", 74)
    _job(
        conn,
        uid,
        "redhat-et/ripwire",
        _pkg("redhat-et/ripwire", 74, "fix", "diff --git a/q b/q\n"),
        mid,
    )
    out = execute_gate2(
        conn, user_id=uid, mission_id=mid, snapshot_id=None, confirm=True
    )
    assert out["remote_writes"] == 0
    assert out["ok"] is False


def _mini_store(tmp_home: Path) -> Path:
    store = tmp_home / "contributions" / "redhat-et__ripwire__74"
    pkg = store / "package"
    pkg.mkdir(parents=True)
    diff = "diff --git a/queries/java/tags.scm b/queries/java/tags.scm\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
    (pkg / "clean.diff").write_text(diff, encoding="utf-8")
    (pkg / "FILES.txt").write_text("queries/java/tags.scm\n", encoding="utf-8")
    (pkg / "PR_TITLE.txt").write_text(
        "fix(java): Type::method is a call site for --uses/--callers\n",
        encoding="utf-8",
    )
    (pkg / "PR_BODY.md").write_text("Fixes #74.\n", encoding="utf-8")
    (pkg / "VALIDATION.md").write_text("RED then GREEN\n", encoding="utf-8")
    manifest = {
        "repository": "redhat-et/ripwire",
        "issue_number": 74,
        "issue_url": "https://github.com/redhat-et/ripwire/issues/74",
        "issue_title": "Java method reference",
        "validated_base_sha": "766913d02795ca12ad93631d8f2e696eb12064fc",
        "patch_commit_sha": "7122b8352bef814837204b5714d8c0fba396c94e",
        "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "freshness": "EXACT",
        "qa": "PASS",
        "plain": {"gates": 613, "pass": 606, "skip": 5, "fail": 2},
        "environmental_failures": [
            {"gate": "attrvocabcheck", "class": "ENVIRONMENT_WORKTREE"}
        ],
        "asan": "PASS_REQUIRED_G1",
    }
    (store / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return store
