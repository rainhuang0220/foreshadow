"""One-shot approved remote submission. Default: refuse. Mocks in tests only."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any, Protocol

from foreshadow.contribution.approval import (
    ALLOWED_REMOTE_ACTIONS,
    BLOCKED_REMOTE_ACTIONS,
    load_snapshot,
    matches_package,
)
from foreshadow.contribution.preflight import GitHubReader, run_preflight

STEPS = ("PREFLIGHT", "FORK", "BRANCH", "PUSH", "CREATE_PR", "PERSIST_RESULT")


class GitHubWriter(GitHubReader, Protocol):
    def ensure_fork(self, repo: str) -> str: ...
    def ensure_branch(self, repo: str, branch: str, sha: str) -> str: ...
    def push_commit(self, repo: str, branch: str, sha: str) -> str: ...
    def find_pr(self, repo: str, *, head: str, base: str) -> dict[str, Any] | None: ...
    def create_pr(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]: ...


class RemoteWriteRefused(RuntimeError):
    pass


def refuse(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "blocked": True,
        "action": action,
        "status": "REMOTE_WRITE_REFUSED",
        "remote_writes": 0,
        "error": "no current Gate-2 approval snapshot",
    }


def assert_action_allowed(action: str) -> None:
    if action in BLOCKED_REMOTE_ACTIONS or action not in ALLOWED_REMOTE_ACTIONS:
        raise RemoteWriteRefused(action)


def _empty_steps() -> dict[str, str]:
    return {name: "NOT_STARTED" for name in STEPS}


def persist_submission(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int,
    snapshot_id: int,
) -> int:
    now = datetime.now(UTC).isoformat()
    existing = conn.execute(
        """
        SELECT id FROM submissions
        WHERE user_id=? AND approval_snapshot_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, snapshot_id),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """
        INSERT INTO submissions(
          user_id, mission_id, approval_snapshot_id, status, steps_json,
          result_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            mission_id,
            snapshot_id,
            "PREFLIGHT",
            json.dumps(_empty_steps()),
            "{}",
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _load(conn: sqlite3.Connection, submission_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, mission_id, approval_snapshot_id, status, steps_json, result_json
        FROM submissions WHERE id=?
        """,
        (submission_id,),
    ).fetchone()
    if row is None:
        raise LookupError("submission not found")
    return {
        "id": row[0],
        "mission_id": row[1],
        "approval_snapshot_id": row[2],
        "status": row[3],
        "steps": json.loads(row[4] or "{}"),
        "result": json.loads(row[5] or "{}"),
    }


def _save(conn: sqlite3.Connection, rec: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE submissions
        SET status=?, steps_json=?, result_json=?, updated_at=?
        WHERE id=?
        """,
        (
            rec["status"],
            json.dumps(rec["steps"]),
            json.dumps(rec["result"]),
            datetime.now(UTC).isoformat(),
            rec["id"],
        ),
    )
    conn.commit()


def submit_approved(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    snapshot_id: int,
    current_fields: dict[str, Any],
    port: GitHubWriter,
    allow_real_remote: bool = False,
) -> dict[str, Any]:
    """Execute the approved allowlist. Tests pass a fake port.

    `allow_real_remote` must stay False for third-party repos during unattended
    work. The Board may set it only after an explicit human Gate-2 click.
    """
    snapshot = load_snapshot(conn, snapshot_id, user_id=user_id)
    from foreshadow.mission import load_mission_plan

    plan = load_mission_plan(conn, int(snapshot["mission_id"]), user_id) or {}
    mission_status = str(plan.get("status") or "")
    if mission_status == "SUBMITTED" and plan.get("bound_pr"):
        return {
            "ok": True,
            "status": "SUBMITTED",
            "pr": plan.get("bound_pr"),
            "remote_writes": 0,
            "resumed": True,
        }
    if mission_status and mission_status != "WAITING_USER_APPROVAL":
        return {
            "ok": False,
            "blocked": True,
            "status": "NOT_WAITING_APPROVAL",
            "remote_writes": 0,
            "error": f"Gate 2 only from WAITING_USER_APPROVAL, not {mission_status}",
        }
    if not matches_package(snapshot, current_fields):
        return {
            "ok": False,
            "status": "APPROVAL_STALE",
            "remote_writes": 0,
        }
    if str(current_fields.get("maintainer_output_safety") or snapshot.get("maintainer_output_safety") or "").upper() != "PASS":
        return {
            "ok": False,
            "blocked": True,
            "status": "MAINTAINER_OUTPUT_UNSAFE",
            "remote_writes": 0,
            "error": "Maintainer-facing draft failed the output safety gate.",
        }
    if not allow_real_remote and not getattr(port, "is_fake", False):
        return {
            "ok": False,
            "blocked": True,
            "status": "REAL_REMOTE_HELD",
            "remote_writes": 0,
            "error": "real third-party writes require an interactive Gate-2 click",
        }
    sid = persist_submission(
        conn,
        user_id=user_id,
        mission_id=int(snapshot["mission_id"]),
        snapshot_id=snapshot_id,
    )
    rec = _load(conn, sid)
    if rec["status"] == "SUBMITTED" and rec["result"].get("pr"):
        return {
            "ok": True,
            "status": "SUBMITTED",
            "submission_id": sid,
            "pr": rec["result"]["pr"],
            "remote_writes": 0,
            "resumed": True,
        }
    if rec["steps"].get("PREFLIGHT") != "DONE":
        pre = run_preflight(port, snapshot, current_fields=current_fields)
        rec["steps"]["PREFLIGHT"] = "DONE" if pre.get("ok") else "FAILED"
        rec["result"]["preflight"] = pre
        if not pre.get("ok"):
            rec["status"] = str(pre.get("status") or "PREFLIGHT_FAILED")
            _save(conn, rec)
            return {**pre, "submission_id": sid, "remote_writes": 0}
        _save(conn, rec)
    elif not (rec["result"].get("preflight") or {}).get("ok", True):
        return {
            **(rec["result"].get("preflight") or {}),
            "submission_id": sid,
            "remote_writes": 0,
        }

    fork = rec["result"].get("fork")
    if rec["steps"].get("FORK") != "DONE" or not fork:
        fork = port.ensure_fork(str(snapshot["repository"]))
        rec["steps"]["FORK"] = "DONE"
        rec["result"]["fork"] = fork
        rec["status"] = "FORK"
        _save(conn, rec)
    branch = str(snapshot["branch_name"])
    sha = str(snapshot["patch_commit_sha"])
    if rec["steps"].get("BRANCH") != "DONE":
        rec["result"]["branch"] = port.ensure_branch(fork, branch, sha)
        rec["steps"]["BRANCH"] = "DONE"
        rec["status"] = "BRANCH"
        _save(conn, rec)
    if rec["steps"].get("PUSH") != "DONE":
        rec["result"]["pushed"] = port.push_commit(fork, branch, sha)
        rec["steps"]["PUSH"] = "DONE"
        rec["status"] = "PUSH"
        _save(conn, rec)
    existing = rec["result"].get("pr")
    if rec["steps"].get("CREATE_PR") != "DONE" or not existing:
        head_candidates = [branch]
        if "/" in fork:
            head_candidates.append(f"{fork.split('/')[0]}:{branch}")
        existing = None
        for head in head_candidates:
            existing = port.find_pr(
                str(snapshot["repository"]),
                head=head,
                base=str(snapshot["base_branch"]),
            )
            if existing is not None:
                break
        if existing is None:
            existing = port.create_pr(
                str(snapshot["repository"]),
                title=str(snapshot["pr_title"]),
                body=str(snapshot["pr_body"]),
                head=branch,
                base=str(snapshot["base_branch"]),
            )
        rec["steps"]["CREATE_PR"] = "DONE"
        rec["result"]["pr"] = existing
        rec["status"] = "CREATE_PR"
        _save(conn, rec)
    rec["steps"]["PERSIST_RESULT"] = "DONE"
    rec["status"] = "SUBMITTED"
    _save(conn, rec)
    from foreshadow.mission import patch_mission_plan, set_status

    plan = {
        "bound_pr": {
            "number": existing.get("number"),
            "html_url": existing.get("html_url"),
            "head_sha": sha,
        },
        "submission_id": sid,
        "approval_snapshot_id": snapshot_id,
    }
    patch_mission_plan(conn, int(snapshot["mission_id"]), user_id, plan)
    set_status(conn, int(snapshot["mission_id"]), user_id, "SUBMITTED")
    return {
        "ok": True,
        "status": "SUBMITTED",
        "submission_id": sid,
        "pr": existing,
        "remote_writes": 1,
        "actions": list(ALLOWED_REMOTE_ACTIONS),
    }


class FakeGitHub:
    """In-memory GitHub for tests. Never talks to the network."""

    is_fake = True

    def __init__(self) -> None:
        self.issue: dict[str, Any] = {
            "state": "open",
            "assignee": None,
            "title": "issue",
            "labels": ["help wanted"],
        }
        self.prs: list[dict[str, Any]] = []
        self.refs: dict[str, str] = {"main": "base"}
        self.files: list[str] = []
        self.forks: list[str] = []
        self.pushes: list[tuple[str, str, str]] = []
        self.created_prs = 0
        self.calls: list[str] = []

    def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        self.calls.append(f"get_issue:{repo}:{number}")
        return dict(self.issue)

    def list_open_prs(self, repo: str) -> list[dict[str, Any]]:
        self.calls.append(f"list_open_prs:{repo}")
        return list(self.prs)

    def get_ref(self, repo: str, ref: str) -> str:
        self.calls.append(f"get_ref:{repo}:{ref}")
        return self.refs.get(ref, self.refs.get("main", "base"))

    def diff_names(self, repo: str, base: str, head: str) -> list[str]:
        self.calls.append(f"diff_names:{base}:{head}")
        return list(self.files)

    def ensure_fork(self, repo: str) -> str:
        self.calls.append(f"ensure_fork:{repo}")
        fork = f"tester/{repo.split('/', 1)[1]}"
        if fork not in self.forks:
            self.forks.append(fork)
        return fork

    def ensure_branch(self, repo: str, branch: str, sha: str) -> str:
        self.calls.append(f"ensure_branch:{repo}:{branch}")
        return sha

    def push_commit(self, repo: str, branch: str, sha: str) -> str:
        self.calls.append(f"push:{repo}:{branch}")
        self.pushes.append((repo, branch, sha))
        return sha

    def find_pr(self, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
        self.calls.append(f"find_pr:{repo}:{head}")
        want = str(head).split(":")[-1]
        for pr in self.prs:
            got = str(pr.get("head") or "").split(":")[-1]
            if got == want and pr.get("base") == base:
                return pr
        return None

    def create_pr(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        self.calls.append(f"create_pr:{repo}")
        self.created_prs += 1
        pr = {
            "number": 99,
            "html_url": f"https://github.com/{repo}/pull/99",
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }
        self.prs.append(pr)
        return pr
