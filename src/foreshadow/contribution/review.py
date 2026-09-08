"""Contribution Review snapshots. Package is authority; worktree is not."""

from __future__ import annotations

import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from foreshadow.contribution.jobs import list_artifacts, list_jobs
from foreshadow.mission import list_missions, load_mission_plan

_ISSUE_RE = re.compile(r"#(\d+)")
_GIT_DIFF_FILE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK = re.compile(r"^@@")


def escape_text(text: str) -> str:
    return html.escape(str(text), quote=True)


def parse_unified_diff(diff: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    hunk: dict[str, Any] | None = None
    added = 0
    deleted = 0
    for line in str(diff or "").splitlines():
        match = _GIT_DIFF_FILE.match(line)
        if match:
            if current is not None:
                files.append(current)
            current = {
                "path": match.group(2),
                "added": 0,
                "deleted": 0,
                "hunks": [],
            }
            hunk = None
            continue
        if current is None:
            continue
        if _HUNK.match(line):
            hunk = {"header": line, "lines": []}
            current["hunks"].append(hunk)
            continue
        if hunk is None:
            continue
        kind = "ctx"
        if line.startswith("+") and not line.startswith("+++"):
            kind = "add"
            current["added"] += 1
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            kind = "del"
            current["deleted"] += 1
            deleted += 1
        hunk["lines"].append(
            {"kind": kind, "text": line[1:] if kind != "ctx" else line}
        )
    if current is not None:
        files.append(current)
    return {"files": files, "added": added, "deleted": deleted, "raw": diff}


def issue_from_text(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    found = _ISSUE_RE.search(text)
    return int(found.group(1)) if found else None


def issue_from_mission(plan: dict[str, Any] | None) -> int | None:
    if not isinstance(plan, dict):
        return None
    for key in ("preferred_issue",):
        n = issue_from_text(plan.get(key))
        if n:
            return n
    cited = plan.get("cited_issue")
    if isinstance(cited, dict):
        n = issue_from_text(cited.get("number"))
        if n:
            return n
    active = plan.get("active_entry_target")
    if isinstance(active, dict):
        n = issue_from_text(active.get("issue_number") or active.get("number"))
        if n:
            return n
    rec = (plan.get("entry_strategy") or {}).get("recommended")
    if isinstance(rec, dict):
        return issue_from_text(rec.get("issue_number") or rec.get("number"))
    return None


def issue_from_package(pkg: dict[str, Any] | None) -> int | None:
    if not isinstance(pkg, dict):
        return None
    n = issue_from_text(pkg.get("related_issue"))
    if n:
        return n
    n = issue_from_text(pkg.get("issue_url"))
    if n:
        return n
    title = pkg.get("pr_title") or pkg.get("task") or ""
    return issue_from_text(title)


def latest_package(
    conn: sqlite3.Connection, job_id: int
) -> tuple[dict[str, Any], int] | None:
    arts = list_artifacts(conn, job_id)
    chosen: tuple[dict[str, Any], int] | None = None
    for item in arts:
        if item.get("kind") != "package" or not item.get("body"):
            continue
        try:
            payload = json.loads(item["body"])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            chosen = (payload, int(item["id"]))
    return chosen


def _same_issue(value: Any, issue: int | None) -> bool:
    return issue is not None and issue_from_text(value) == issue


def _title_from(plan: dict[str, Any], pkg: dict[str, Any], issue: int | None) -> str:
    cited = plan.get("cited_issue") or {}
    if (
        isinstance(cited, dict)
        and _same_issue(cited.get("number"), issue)
        and cited.get("title")
    ):
        return str(cited["title"])
    active = plan.get("active_entry_target") or {}
    if (
        isinstance(active, dict)
        and _same_issue(active.get("issue_number") or active.get("number"), issue)
        and active.get("title")
    ):
        return str(active["title"])
    if pkg.get("pr_title"):
        return str(pkg["pr_title"])
    rec = (plan.get("entry_strategy") or {}).get("recommended") or {}
    if (
        isinstance(rec, dict)
        and _same_issue(rec.get("issue_number") or rec.get("number"), issue)
        and rec.get("title")
    ):
        return str(rec["title"])
    return f"#{issue}" if issue else ""


def _source_label(plan: dict[str, Any]) -> str:
    raw = str(plan.get("entry_source") or "").strip()
    if raw.upper() in {"HUMAN_CONFIRM", "HUMAN_CONFIRMED", "HUMAN"}:
        return "HUMAN CONFIRMED"
    return raw or "HUMAN CONFIRMED"


def _bind_job(
    conn: sqlite3.Connection,
    uid: int,
    plan: dict[str, Any],
    full_name: str,
) -> tuple[Any, dict[str, Any], int] | None:
    issue = issue_from_mission(plan)
    jobs = [j for j in list_jobs(conn, uid) if j.full_name == full_name]
    matches: list[tuple[Any, dict[str, Any], int]] = []
    for job in jobs:
        packed = latest_package(conn, int(job.id or 0))
        if packed is None:
            continue
        pkg, art_id = packed
        pkg_issue = issue_from_package(pkg)
        if issue is not None and pkg_issue is not None and pkg_issue != issue:
            continue
        if issue is None and pkg_issue is None:
            continue
        if issue is not None and pkg_issue is None:
            task = job.task or {}
            structured = task.get("structured") if isinstance(task, dict) else {}
            task_issue = None
            if isinstance(structured, dict):
                task_issue = issue_from_text(structured.get("issue_number"))
            if task_issue != issue:
                continue
        matches.append((job, pkg, art_id))
    if not matches:
        return None
    matches.sort(key=lambda item: int(item[0].id or 0))
    return matches[-1]


def _review(
    conn: sqlite3.Connection,
    uid: int,
    plan: dict[str, Any],
    *,
    role: str,
    worktree: Path | None = None,
) -> dict[str, Any] | None:
    del worktree  # package is the snapshot; worktree must not change the review
    full_name = str(plan.get("full_name") or "")
    bound = _bind_job(conn, uid, plan, full_name)
    if bound is None:
        return None
    job, pkg, art_id = bound
    issue = issue_from_mission(plan) or issue_from_package(pkg)
    diff = str(pkg.get("diff") or "")
    parsed = parse_unified_diff(diff)
    impl = (
        pkg.get("implementation") if isinstance(pkg.get("implementation"), dict) else {}
    )
    tests = pkg.get("tests") if isinstance(pkg.get("tests"), dict) else {}
    commands = list(tests.get("commands") or [])
    return {
        "authority": "package",
        "role": role,
        "repository": full_name,
        "mission_id": plan.get("id"),
        "job_id": job.id,
        "artifact_id": art_id,
        "issue_number": issue,
        "issue_url": pkg.get("issue_url")
        or (f"https://github.com/{full_name}/issues/{issue}" if issue else None),
        "title": _title_from(plan, pkg, issue),
        "status": pkg.get("status") or job.canonical_status,
        "source": _source_label(plan),
        "package_revision": art_id,
        "executor": {
            "backend": impl.get("backend") or job.backend,
            "model": impl.get("model"),
            "mode": impl.get("mode"),
        },
        "diff": diff,
        "diff_files": parsed["files"],
        "diff_summary": {
            "files": parsed["files"]
            and len(parsed["files"])
            or int(pkg.get("files_changed_n") or 0),
            "added": parsed["added"],
            "deleted": parsed["deleted"],
        },
        "files_changed": list(
            pkg.get("files_changed") or [f["path"] for f in parsed["files"]]
        ),
        "files_changed_n": int(pkg.get("files_changed_n") or len(parsed["files"])),
        "pr_title": pkg.get("pr_title"),
        "pr_body": pkg.get("pr_body"),
        "tests": tests,
        "tests_ok": bool(tests.get("ok")),
        "qa": pkg.get("qa"),
        "qa_ok": bool(pkg.get("qa_ok")),
        "remote_writes": int(pkg.get("remote_writes") or 0),
        "remote_status": pkg.get("remote_status") or "WAITING_USER_APPROVAL",
        "implementation": impl,
        "entry_revision": pkg.get("entry_revision"),
        "upstream_head": impl.get("upstream_head"),
        "pre_tree_hash": impl.get("pre_tree_hash"),
        "executor_started": impl.get("executor_started") or impl.get("started_at"),
        "executor_finished": impl.get("executor_finished") or impl.get("finished_at"),
        "local_path": plan.get("local_path"),
        "package": pkg,
        "job_status": job.canonical_status,
        "next_action": "Review changes",
        "approval_enabled": False,
        "test_commands": commands,
    }


def history_for_repo(
    conn: sqlite3.Connection, user_id: int, full_name: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = [m for m in list_missions(conn, user_id) if m.get("full_name") == full_name]
    rows.sort(key=lambda m: int(m.get("id") or 0), reverse=True)
    first = True
    for plan in rows:
        if str(plan.get("status") or "") == "ABANDONED":
            continue
        review = _review(conn, user_id, plan, role="active" if first else "history")
        if review is None:
            continue
        role = "active" if first else "history"
        first = False
        out.append(
            {
                "role": role,
                "mission_id": review["mission_id"],
                "job_id": review["job_id"],
                "issue_number": review["issue_number"],
                "title": review["title"],
                "status": review["status"],
                "files_changed_n": review["files_changed_n"],
                "diff_summary": review["diff_summary"],
                "tests_ok": review["tests_ok"],
                "qa": review["qa"],
                "remote_writes": review["remote_writes"],
                "source": review["source"],
            }
        )
    return out


def active_contribution(
    conn: sqlite3.Connection,
    user_id: int,
    full_name: str,
    *,
    worktree: Path | None = None,
) -> dict[str, Any] | None:
    rows = [m for m in list_missions(conn, user_id) if m.get("full_name") == full_name]
    rows = [m for m in rows if str(m.get("status") or "") != "ABANDONED"]
    rows.sort(key=lambda m: int(m.get("id") or 0), reverse=True)
    if not rows:
        return None
    return _review(conn, user_id, rows[0], role="active", worktree=worktree)


def contribution_for_mission(
    conn: sqlite3.Connection,
    user_id: int,
    mission_id: int,
    *,
    worktree: Path | None = None,
) -> dict[str, Any] | None:
    plan = load_mission_plan(conn, mission_id, user_id)
    if plan is None:
        return None
    hist = history_for_repo(conn, user_id, str(plan.get("full_name") or ""))
    role = "active"
    for item in hist:
        if int(item["mission_id"] or 0) == int(mission_id):
            role = str(item["role"])
            break
    return _review(conn, user_id, plan, role=role, worktree=worktree)


def _draft_history(
    conn: sqlite3.Connection, job_id: int | None
) -> list[dict[str, Any]]:
    if job_id is None:
        return []
    out: list[dict[str, Any]] = []
    arts = [
        item
        for item in list_artifacts(conn, int(job_id))
        if item.get("kind") == "package"
    ]
    last_id = arts[-1]["id"] if arts else None
    for item in arts:
        try:
            payload = json.loads(item["body"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        gate = payload.get("maintainer_output_gate")
        out.append(
            {
                "artifact_id": item["id"],
                "created_at": item.get("created_at"),
                "draft_status": "current" if item["id"] == last_id else "superseded",
                "pr_title": payload.get("pr_title"),
                "safety_ok": gate.get("ok") if isinstance(gate, dict) else None,
            }
        )
    return out


def _context_for_review(review: dict[str, Any], plan: dict[str, Any] | None):
    from foreshadow.contribution.maintainer import project_maintainer_context

    pkg = review.get("package") if isinstance(review.get("package"), dict) else {}
    cited = (plan or {}).get("cited_issue") if isinstance(plan, dict) else {}
    if not isinstance(cited, dict):
        cited = {}
    tests = review.get("tests") if isinstance(review.get("tests"), dict) else {}
    commands: list[str] = []
    for item in tests.get("commands") or []:
        if isinstance(item, dict) and item.get("command"):
            commands.append(str(item["command"]))
        elif isinstance(item, str):
            commands.append(item)
    return project_maintainer_context(
        repository=str(review.get("repository") or ""),
        diff=str(review.get("diff") or ""),
        files=list(review.get("files_changed") or []),
        test_commands=commands,
        tests_ok=bool(review.get("tests_ok")),
        issue_title=str(pkg.get("issue_title") or cited.get("title") or ""),
        issue_body=str(pkg.get("issue_body") or cited.get("body") or ""),
        issue_number=review.get("issue_number"),
    )


def pr_draft(conn: sqlite3.Connection, user_id: int, mission_id: int) -> dict[str, Any]:
    from foreshadow.contribution.maintainer import evaluate_maintainer_output

    review = contribution_for_mission(conn, user_id, mission_id)
    if review is None:
        raise KeyError("contribution not found")
    plan = load_mission_plan(conn, mission_id, user_id)
    impl = review.get("implementation") or {}
    title = str(review.get("pr_title") or "")
    body = str(review.get("pr_body") or "")
    ctx = _context_for_review(review, plan)
    gate = evaluate_maintainer_output(title, body, ctx)
    return {
        "title": review.get("pr_title"),
        "body": review.get("pr_body"),
        "body_html": render_pr_markdown(str(review.get("pr_body") or "")),
        "repository": review.get("repository"),
        "base": "main",
        "head": impl.get("branch") or "foreshadow/entry",
        "issue": review.get("issue_number"),
        "closes": f"#{review['issue_number']}" if review.get("issue_number") else None,
        "tests_ok": review.get("tests_ok"),
        "remote_writes": review.get("remote_writes"),
        "submitted": False,
        "status": "NOT SUBMITTED" if gate.ok else "MAINTAINER_OUTPUT_UNSAFE",
        "entry_revision": review.get("entry_revision"),
        "source": "package",
        "safety": {
            "ok": gate.ok,
            "verdict": gate.verdict,
            "summary": list(gate.summary),
            "checks": dict(gate.checks),
        },
        "draft_history": _draft_history(conn, review.get("job_id")),
    }


def checks_view(
    conn: sqlite3.Connection, user_id: int, mission_id: int
) -> dict[str, Any]:
    review = contribution_for_mission(conn, user_id, mission_id)
    if review is None:
        raise KeyError("contribution not found")
    impl = review.get("implementation") or {}
    tests = [
        {
            "label": cmd.get("command") or cmd.get("label") or "test",
            "command": cmd.get("command"),
            "ok": bool(cmd.get("ok")),
            "returncode": cmd.get("returncode"),
            "duration_s": cmd.get("duration_s"),
            "log": cmd.get("log") or "",
        }
        for cmd in review.get("test_commands") or []
    ]
    return {
        "live": {
            "issue_number": review.get("issue_number"),
            "issue_recorded": review.get("issue_number") is not None,
            "unassigned": None,
            "no_overlap": None,
            "recertified_at_package": bool(review.get("entry_revision")),
            "source": "package",
        },
        "provenance": {
            "fresh_clone": bool(impl.get("clean_before")),
            "clean_before": bool(impl.get("clean_before")),
            "mode": impl.get("mode"),
            "autonomous": impl.get("mode") == "autonomous_executor",
        },
        "tests": tests,
        "qa": {
            "verdict": review.get("qa"),
            "ok": review.get("qa_ok"),
        },
        "remote": {
            "push": "blocked",
            "pr": "blocked",
            "comments": 0,
            "remote_writes": review.get("remote_writes") or 0,
        },
        "maintainer_output": (review.get("package") or {}).get("maintainer_output_gate")
        if isinstance(review.get("package"), dict)
        else None,
        "timeline": [
            {"id": "entry", "label": "Entry", "done": True},
            {"id": "recertify", "label": "Live recertification", "done": True},
            {
                "id": "clone",
                "label": "Clean clone",
                "done": bool(impl.get("clean_before")),
            },
            {"id": "analyze", "label": "Analyze", "done": True},
            {"id": "implement", "label": "Implement", "done": bool(review.get("diff"))},
            {"id": "tests", "label": "Tests", "done": bool(review.get("tests_ok"))},
            {"id": "qa", "label": "QA", "done": bool(review.get("qa_ok"))},
            {"id": "package", "label": "Package", "done": True},
            {
                "id": "review",
                "label": "Waiting user review",
                "done": False,
                "current": True,
            },
        ],
    }


def render_pr_markdown(text: str) -> str:
    """Escape first, then apply a tiny safe subset of Markdown."""
    escaped = escape_text(text)
    lines = escaped.splitlines()
    out: list[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(line)
            continue
        if line.startswith("### "):
            out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif not line.strip():
            out.append("")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def _rewrite_stale_discovery(card: dict[str, Any], active: dict[str, Any]) -> None:
    rec = card.get("entry") if isinstance(card.get("entry"), dict) else {}
    recommended = rec.get("recommended") if isinstance(rec, dict) else None
    if not isinstance(recommended, dict):
        return
    disc = issue_from_text(recommended.get("issue_number"))
    if disc and disc != active.get("issue_number"):
        card["discovery_recommendation"] = recommended
        card["entry"] = {
            **rec,
            "recommended": {
                "issue_number": active.get("issue_number"),
                "title": active.get("title"),
                "route": "ISSUE",
            },
        }
        card["active_entry_target"] = card["entry"]["recommended"]


def attach_review_summaries(
    payload: dict[str, Any], conn: sqlite3.Connection, user_id: int
) -> dict[str, Any]:
    queue: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_name: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    for plan in list_missions(conn, user_id):
        name = str(plan.get("full_name") or "")
        if not name or name in seen or str(plan.get("status") or "") == "ABANDONED":
            continue
        hist = history_for_repo(conn, user_id, name)
        if not hist:
            continue
        active = next((h for h in hist if h["role"] == "active"), hist[0])
        seen.add(name)
        by_name[name] = (hist, active)
        queue.append(
            {
                "full_name": name,
                "html_url": f"https://github.com/{name}",
                "review": active,
                "review_history": hist,
            }
        )
    for card in payload.get("candidates") or []:
        name = str(card.get("full_name") or "")
        if name not in by_name:
            continue
        hist, active = by_name[name]
        card["review"] = active
        card["review_history"] = hist
        _rewrite_stale_discovery(card, active)
    payload["review_queue"] = queue
    return payload


def public_review(
    review: dict[str, Any] | None, *, include_package: bool = False
) -> dict[str, Any] | None:
    if review is None:
        return None
    out = dict(review)
    pkg = out.pop("package", None)
    if include_package and pkg is not None:
        out["raw_package"] = pkg
    return out
