"""Contribution package shown on the Board. Never pushes."""

from __future__ import annotations

from typing import Any

from foreshadow.contribution.executor import ContributionJob, PatchArtifact
from foreshadow.contribution.maintainer import (
    compose_and_gate,
    project_maintainer_context,
)
from foreshadow.contribution.task import StructuredTask


def _test_commands(
    job: ContributionJob, structured: StructuredTask | None
) -> list[str]:
    tests = job.test_result or {}
    out: list[str] = []
    raw = tests.get("commands") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("command"):
                out.append(str(item["command"]))
            elif isinstance(item, str) and item.strip():
                out.append(item)
    if not out and tests.get("command"):
        out.append(str(tests["command"]))
    if not out and structured is not None:
        out = list(structured.test_commands or [])
    return out


def build_package(
    job: ContributionJob,
    artifact: PatchArtifact,
    *,
    structured: StructuredTask | None = None,
    baseline: dict[str, Any] | None = None,
    qa_ok: bool | None = None,
) -> dict[str, Any]:
    task = job.task or {}
    structured = structured or _task_from_mapping(task.get("structured"))
    files = list(artifact.files or [])
    tests = job.test_result or {}
    qa = True if qa_ok is None else bool(qa_ok)
    issue = None
    if structured and structured.issue_number is not None:
        issue = f"#{structured.issue_number}"
    elif task.get("issue_number") is not None:
        issue = f"#{task.get('issue_number')}"
    contributing = ""
    if isinstance(task.get("entry"), dict):
        contributing = str(task["entry"].get("contributing") or "")
    ctx = project_maintainer_context(
        repository=job.full_name,
        structured=structured,
        diff=artifact.diff or "",
        files=files,
        test_commands=_test_commands(job, structured),
        tests_ok=bool(artifact.tests_passed),
        contributing=contributing,
    )
    draft, gate = compose_and_gate(ctx)
    title = draft.title or artifact.title or "Contribution"
    implementation = dict(task.get("implementation") or {})
    if job.backend == "workspace":
        implementation = {
            "mode": "existing_worktree",
            "clean_before": False,
            "capability": "EXISTING_WORKTREE_VALIDATED",
        }
    return {
        "repository": job.full_name,
        "entry_revision": structured.entry_revision if structured else None,
        "implementation": implementation,
        "task": structured.task if structured else str(task.get("prompt") or title),
        "why": artifact.why or job.why,
        "evidence": list(structured.evidence) if structured else [],
        "files_changed": files,
        "files_changed_n": len(files),
        "diff": artifact.diff,
        "tests": {
            "ok": bool(artifact.tests_passed),
            "commands": tests.get("commands") or [],
            "duration_s": tests.get("duration_s"),
            "exit_code": tests.get("returncode"),
            "command": tests.get("command") or tests.get("argv"),
            "log": artifact.test_log or tests.get("log") or "",
        },
        "baseline": baseline
        if baseline is not None
        else ((job.task or {}).get("baseline") if isinstance(job.task, dict) else None),
        "qa": "PASS"
        if qa and artifact.tests_passed and artifact.diff.strip()
        else "FAIL",
        "qa_ok": bool(qa and artifact.qa_ok),
        "qa_reasons": list(artifact.qa_reasons or []),
        "risk": artifact.risk,
        "pr_title": title,
        "pr_body": draft.body,
        "related_issue": issue,
        "issue_url": structured.issue_url if structured else None,
        "issue_title": ctx.issue_title,
        "issue_body": ctx.issue_body,
        "maintainer_notes": list(structured.contribution_rules) if structured else [],
        "estimated_acceptance_likelihood": _likelihood(structured, qa),
        "backend": job.backend,
        "status": "WAITING_USER_APPROVAL"
        if qa and artifact.tests_passed and artifact.diff.strip()
        else "failed",
        "log": list(job.log or []),
        "remote_writes": 0,
        "remote_status": "WAITING_USER_APPROVAL"
        if gate.ok
        else "MAINTAINER_OUTPUT_UNSAFE",
        "maintainer_output_gate": gate.as_dict(),
        "pr_draft_revision": 1,
        "draft_status": "current",
    }


def _task_from_mapping(raw: Any) -> StructuredTask | None:
    if not isinstance(raw, dict):
        return None
    try:
        return StructuredTask.model_validate(raw)
    except (TypeError, ValueError):
        return None


def _likelihood(structured: StructuredTask | None, qa_ok: bool) -> str:
    if not qa_ok:
        return "low"
    if structured and structured.issue_number is not None:
        return "medium-high"
    return "medium"
