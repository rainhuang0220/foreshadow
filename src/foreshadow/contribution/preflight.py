"""GET-only recertification before the first approved remote write."""

from __future__ import annotations

from typing import Any, Protocol

CONFLICT_PATH_PREFIXES = (
    "queries/java/",
    "src/ingest",
    "src/quality.h",
    "test/regression.sh",
    "test/qschemetrip",
    "test/qextraction",
    "test/callformcheck",
    "test/pargates",
)


def _own_approved_pr(pr: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    head = pr.get("head")
    if isinstance(head, dict):
        head = head.get("ref") or head.get("label")
    head_s = str(head or "")
    branch = str(snapshot.get("branch_name") or "")
    return bool(branch and (head_s == branch or head_s.endswith(":" + branch)))


class GitHubReader(Protocol):
    def get_issue(self, repo: str, number: int) -> dict[str, Any]: ...
    def list_open_prs(self, repo: str) -> list[dict[str, Any]]: ...
    def get_ref(self, repo: str, ref: str) -> str: ...
    def diff_names(self, repo: str, base: str, head: str) -> list[str]: ...


def classify_delta(names: list[str], *, patch_files: list[str] | None = None) -> str:
    if not names:
        return "IDENTICAL"
    if all(
        n.startswith("docs/")
        or n.endswith(".md")
        or "captures/" in n
        for n in names
    ):
        return "DOCS_ONLY"
    patch = {str(p) for p in (patch_files or []) if p}
    if patch and any(n in patch for n in names):
        return "CONFLICT_SENSITIVE"
    if any(
        n.startswith(p) or n == p.rstrip("/")
        for n in names
        for p in CONFLICT_PATH_PREFIXES
    ):
        return "CONFLICT_SENSITIVE"
    return "NON_OVERLAPPING"


def run_preflight(
    reader: GitHubReader,
    snapshot: dict[str, Any],
    *,
    current_fields: dict[str, Any],
) -> dict[str, Any]:
    from foreshadow.contribution.approval import matches_package

    if not matches_package(snapshot, current_fields):
        return {
            "ok": False,
            "status": "APPROVAL_STALE",
            "reason": "diff, title, body, or base changed; Gate 2 required again",
            "remote_writes": 0,
        }
    issue = reader.get_issue(str(snapshot["repository"]), int(snapshot["issue_number"]))
    if str(issue.get("state") or "").lower() != "open":
        return {"ok": False, "status": "ISSUE_CLOSED", "remote_writes": 0, "issue": issue}
    if issue.get("assignee") and str(issue.get("assignee")) not in {
        "",
        "none",
        None,
        snapshot.get("operator"),
    }:
        login = (
            issue["assignee"].get("login")
            if isinstance(issue.get("assignee"), dict)
            else issue.get("assignee")
        )
        if login:
            return {
                "ok": False,
                "status": "ISSUE_ASSIGNED",
                "assignee": login,
                "remote_writes": 0,
            }
    prs = reader.list_open_prs(str(snapshot["repository"]))
    overlap = [
        p
        for p in prs
        if not _own_approved_pr(p, snapshot)
        and (
            str(snapshot["issue_number"]) in str(p.get("title") or "")
            or f"#{snapshot['issue_number']}" in str(p.get("body") or "")
        )
    ]
    if overlap:
        return {
            "ok": False,
            "status": "OVERLAPPING_PR",
            "prs": overlap,
            "remote_writes": 0,
        }
    head = reader.get_ref(str(snapshot["repository"]), snapshot.get("base_branch") or "main")
    if head == snapshot["validated_base_sha"]:
        return {
            "ok": True,
            "status": "EXACT",
            "remote_head": head,
            "remote_writes": 0,
        }
    names = reader.diff_names(
        str(snapshot["repository"]), snapshot["validated_base_sha"], head
    )
    kind = classify_delta(
        names,
        patch_files=list(snapshot.get("files_changed") or current_fields.get("files_changed") or []),
    )
    if kind == "CONFLICT_SENSITIVE":
        return {
            "ok": False,
            "status": "NEEDS_REFRESH",
            "remote_head": head,
            "delta_classification": kind,
            "names": names,
            "remote_writes": 0,
        }
    return {
        "ok": True,
        "status": kind,
        "remote_head": head,
        "delta_classification": kind,
        "names": names,
        "remote_writes": 0,
        "disclose": True,
    }
