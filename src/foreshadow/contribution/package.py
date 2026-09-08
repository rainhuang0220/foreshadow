"""Contribution package shown on the Board. Never pushes."""

from __future__ import annotations

from typing import Any

from foreshadow.contribution.executor import ContributionJob, PatchArtifact
from foreshadow.contribution.task import StructuredTask


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
    title = artifact.title or (structured.task if structured else "") or "Contribution"
    body_lines = [
        artifact.why or job.why or (structured.why if structured else ""),
        "",
    ]
    if structured and structured.expected_behavior:
        body_lines.append(structured.expected_behavior)
        body_lines.append("")
    if structured and structured.acceptance_criteria:
        body_lines.extend(f"- {item}" for item in structured.acceptance_criteria[:6])
        body_lines.append("")
    if issue:
        body_lines.append(f"Closes {issue}.")
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
        "pr_body": "\n".join(line for line in body_lines if line is not None).strip(),
        "related_issue": issue,
        "issue_url": structured.issue_url if structured else None,
        "maintainer_notes": list(structured.contribution_rules) if structured else [],
        "estimated_acceptance_likelihood": _likelihood(structured, qa),
        "backend": job.backend,
        "status": "WAITING_USER_APPROVAL"
        if qa and artifact.tests_passed and artifact.diff.strip()
        else "failed",
        "log": list(job.log or []),
        "remote_writes": 0,
        "remote_status": "WAITING_USER_APPROVAL",
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
