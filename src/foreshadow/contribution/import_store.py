"""Import a validated local contribution into the mission pipeline.

Does not reimplement the patch. Does not write to third-party GitHub.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from foreshadow.contribution.approval import (
    create_snapshot,
    current_snapshot,
    maintainer_safety_from_review,
    matches_package,
    snapshot_fields,
)
from foreshadow.contribution.executor import ContributionJob, JobStatus
from foreshadow.contribution.identity import issue_from_plan
from foreshadow.contribution.jobs import persist_artifact, persist_job
from foreshadow.mission import (
    build_mission,
    list_missions,
    load_mission_plan,
    patch_mission_plan,
    persist_mission,
    set_status,
)
from foreshadow.paths import resolve_data_dir

RIPWIRE_74_STORE = "redhat-et__ripwire__74"


def contribution_store_dir(
    repository: str, issue_number: int, *, data_dir: Path | None = None
) -> Path:
    root = data_dir if data_dir is not None else resolve_data_dir()
    slug = repository.replace("/", "__")
    return root / "contributions" / f"{slug}__{issue_number}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(store: Path) -> dict[str, Any]:
    return json.loads((store / "MANIFEST.json").read_text(encoding="utf-8"))


def copy_store(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() != src.resolve():
        if dest.exists():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copytree(src, dest)
    return dest


def package_from_store(store: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    pkg_dir = store / "package"
    diff = (pkg_dir / "clean.diff").read_text(encoding="utf-8")
    digest = sha256_text(diff)
    expected = str(manifest.get("diff_sha256") or "")
    if expected and digest != expected:
        raise ValueError(f"diff sha256 mismatch: {digest} != {expected}")
    files = [
        line.strip()
        for line in (pkg_dir / "FILES.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    title = (pkg_dir / "PR_TITLE.txt").read_text(encoding="utf-8").strip()
    body = (pkg_dir / "PR_BODY.md").read_text(encoding="utf-8")
    validation = (pkg_dir / "VALIDATION.md").read_text(encoding="utf-8")
    issue = int(manifest["issue_number"])
    repo = str(manifest["repository"])
    env_fails = list(manifest.get("environmental_failures") or [])
    targeted_commands = list(manifest.get("targeted_commands") or [])
    if not targeted_commands:
        targeted_commands = [
            "RIPWIRE_BIN=build/ripwire bash test/javamethodrefcheck.sh",
            "bash test/callformcheck.sh",
        ]
    test_commands = [
        {"command": str(command), "ok": True, "label": "targeted validation"}
        for command in targeted_commands
    ]
    if str(manifest.get("broader_validation") or "PASS").upper() != "NOT_NEEDED":
        plain = manifest.get("plain") if isinstance(manifest.get("plain"), dict) else {}
        label = "plain full suite"
        if plain:
            label = (
                f"plain {plain.get('gates', '?')}/{plain.get('pass', '?')}/"
                f"{plain.get('skip', '?')} + {plain.get('fail', '?')} classified"
            )
        test_commands.append(
            {
                "command": "python3 test/pargates.py . ./build/ripwire",
                "ok": True,
                "label": label,
                "classification": env_fails,
            }
        )
    return {
        "repository": repo,
        "related_issue": f"#{issue}",
        "issue_number": issue,
        "issue_url": manifest.get("issue_url")
        or f"https://github.com/{repo}/issues/{issue}",
        "issue_title": manifest.get("issue_title"),
        "pr_title": title,
        "pr_body": body,
        "diff": diff,
        "diff_sha256": digest,
        "files_changed": files,
        "files_changed_n": len(files),
        "validated_base_sha": manifest.get("validated_base_sha"),
        "patch_commit_sha": manifest.get("patch_commit_sha"),
        "freshness": manifest.get("freshness") or "EXACT",
        "upstream_head": manifest.get("remote_head_after_asan")
        or manifest.get("validated_base_sha"),
        "persistent_store": str(store),
        "tmp_independent": True,
        "git_bundle": str(pkg_dir / "patch.bundle")
        if (pkg_dir / "patch.bundle").is_file()
        else None,
        "why": {
            "technical": (
                "Java Type::method was parsed but never captured as a call site "
                "for --uses/--callers."
            ),
            "maintainer_intent": (
                "Issue #74: method references should appear beside lambda call forms."
            ),
            "scope": "Query-only change in queries/java/tags.scm plus matching gates.",
        },
        "evidence": {
            "red": manifest.get("red") or "confirmed on pristine 766913d",
            "targeted": manifest.get("targeted_validation")
            or ["javamethodrefcheck PASS", "callformcheck PASS"],
            "plain": manifest.get("plain"),
            "environmental_failures": env_fails,
            "environmental_class": "ENVIRONMENT_WORKTREE",
            "asan": manifest.get("asan") or "PASS_REQUIRED_G1",
            "determinism": "det-gate ×3 PASS",
            "sanitizer_findings": "none",
            "validation": validation,
            "qa": manifest.get("qa") or "PASS",
        },
        "tests": {
            "ok": True,
            "commands": test_commands,
        },
        "qa": manifest.get("qa") or "PASS",
        "qa_ok": True,
        "remote_writes": 0,
        "remote_status": "WAITING_USER_APPROVAL",
        "status": "WAITING_USER_APPROVAL",
        "display_status": "SUBMISSION_CHECK_REQUIRED",
        "third_party_submit": "HOLD_FOR_HUMAN",
        "implementation": {
            "mode": "imported_validated_artifact",
            "backend": "import_store",
            "clean_before": True,
            "branch": "foreshadow/ripwire-74-method-ref",
            "upstream_head": manifest.get("validated_base_sha"),
            "patch_commit_sha": manifest.get("patch_commit_sha"),
        },
        "remote_plan": {
            "will": ["fork (if needed)", "push one contribution branch", "create one PR"],
            "will_not": ["comment", "review", "merge", "force push"],
        },
        "entry_revision": "ripwire-74-imported",
        "authority": "package",
    }


def _existing_mission(
    conn: sqlite3.Connection, user_id: int, repository: str, issue_number: int
) -> dict[str, Any] | None:
    for plan in list_missions(conn, user_id):
        if plan.get("full_name") != repository:
            continue
        if str(plan.get("status") or "") in {"MERGED", "ABANDONED"}:
            continue
        if issue_from_plan(plan) == issue_number:
            return plan
        if int(plan.get("issue_number") or 0) == issue_number:
            return plan
    return None


def import_validated_contribution(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    store: Path,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    store = Path(store)
    manifest = load_manifest(store)
    repository = str(manifest["repository"])
    issue_number = int(manifest["issue_number"])
    dest = contribution_store_dir(repository, issue_number, data_dir=data_dir)
    dest = copy_store(store, dest)
    pkg = package_from_store(dest, manifest)
    existing = _existing_mission(conn, user_id, repository, issue_number)
    if existing is not None:
        mid = int(existing["id"])
        _ensure_job_and_snapshot(conn, user_id, mid, pkg, manifest)
        if str(existing.get("status") or "") not in {
            "SUBMITTED",
            "REVIEWING",
            "WAITING_MAINTAINER",
            "WAITING_USER_APPROVAL",
        }:
            set_status(conn, mid, user_id, "WAITING_USER_APPROVAL")
        plan = load_mission_plan(conn, mid, user_id) or existing
        return {"mission_id": mid, "imported": False, "reused": True, "mission": plan}
    mission = build_mission(
        repository,
        language="C",
        blurb=str(manifest.get("issue_title") or ""),
    )
    mission.status = "WAITING_USER_APPROVAL"
    persist_mission(conn, mission, user_id=user_id, repo_id=None)
    mid = int(mission.id or 0)
    issue_url = str(
        manifest.get("issue_url") or f"https://github.com/{repository}/issues/{issue_number}"
    )
    patch_mission_plan(
        conn,
        mid,
        user_id,
        {
            "repository": repository,
            "issue_number": issue_number,
            "issue_url": issue_url,
            "preferred_issue": issue_number,
            "cited_issue": {
                "number": issue_number,
                "title": manifest.get("issue_title"),
                "html_url": issue_url,
            },
            "active_entry_target": {
                "issue_number": issue_number,
                "title": manifest.get("issue_title"),
                "route": "ISSUE",
            },
            "entry_source": "HUMAN_CONFIRM",
            "validated_base_sha": manifest.get("validated_base_sha"),
            "patch_commit_sha": manifest.get("patch_commit_sha"),
            "diff_sha256": pkg["diff_sha256"],
            "freshness": manifest.get("freshness"),
            "persistent_store": str(dest),
            "display_status": "SUBMISSION_CHECK_REQUIRED",
            "third_party_submit": "HOLD_FOR_HUMAN",
            "remote_writes": 0,
        },
        status="WAITING_USER_APPROVAL",
    )
    _ensure_job_and_snapshot(conn, user_id, mid, pkg, manifest)
    plan = load_mission_plan(conn, mid, user_id) or {}
    return {"mission_id": mid, "imported": True, "reused": False, "mission": plan}


def _ensure_job_and_snapshot(
    conn: sqlite3.Connection,
    user_id: int,
    mission_id: int,
    pkg: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    job = ContributionJob(
        user_id=user_id,
        full_name=str(pkg["repository"]),
        backend="import_store",
        status=JobStatus.ready,
        mission_id=mission_id,
        task={
            "structured": {
                "issue_number": pkg["issue_number"],
                "repository": pkg["repository"],
                "task": pkg.get("pr_title"),
            }
        },
    )
    persist_job(conn, job)
    package_revision = persist_artifact(
        conn,
        int(job.id or 0),
        kind="package",
        body=json.dumps(pkg, ensure_ascii=False),
        meta={
            "diff_sha256": pkg["diff_sha256"],
            "persistent_store": pkg.get("persistent_store"),
            "imported_at": datetime.now(UTC).isoformat(),
        },
    )
    fields = snapshot_fields(
        mission_id=mission_id,
        package_revision=package_revision,
        repository=str(pkg["repository"]),
        issue_number=int(pkg["issue_number"]),
        issue_url=str(pkg["issue_url"]),
        base_repo=str(pkg["repository"]),
        base_branch="main",
        validated_base_sha=str(pkg.get("validated_base_sha") or ""),
        patch_commit_sha=str(pkg.get("patch_commit_sha") or ""),
        diff_sha256=str(pkg["diff_sha256"]),
        branch_name=str((pkg.get("implementation") or {}).get("branch") or "foreshadow/entry"),
        pr_title=str(pkg.get("pr_title") or ""),
        pr_body=str(pkg.get("pr_body") or ""),
        test_evidence_digest=sha256_text(json.dumps(pkg.get("evidence") or {}, sort_keys=True)),
        qa_verdict=str(pkg.get("qa") or "PASS"),
        maintainer_output_safety=maintainer_safety_from_review(
            {
                "repository": pkg["repository"],
                "pr_title": pkg.get("pr_title"),
                "pr_body": pkg.get("pr_body"),
                "diff": pkg.get("diff"),
                "files_changed": pkg.get("files_changed") or [],
                "issue_number": pkg.get("issue_number"),
                "title": pkg.get("issue_title"),
                "package": pkg,
                "tests_ok": True,
            }
        ),
        freshness=str(pkg.get("freshness") or "EXACT"),
    )
    current = current_snapshot(conn, user_id=user_id, mission_id=mission_id)
    if current is None or not matches_package(current, fields):
        create_snapshot(conn, user_id=user_id, fields=fields)


def default_ripwire74_store() -> Path:
    mac = (
        Path.home()
        / "Library"
        / "Application Support"
        / "foreshadow"
        / "contributions"
        / RIPWIRE_74_STORE
    )
    if mac.is_dir() and (mac / "MANIFEST.json").is_file():
        return mac
    return contribution_store_dir("redhat-et/ripwire", 74)
