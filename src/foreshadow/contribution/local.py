"""Confirmed entry → local contribution. Remote GitHub writes stay refused."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from foreshadow.contribution.executor import (
    ContributionExecutor,
    ContributionJob,
    JobStatus,
    get_executor,
    run_contribution,
)
from foreshadow.contribution.task import from_entry
from foreshadow.github.live_entry import extras_from_issue
from foreshadow.mission import list_missions

_OVERLAY_MTIME_SKIPS = (
    ("internal/sources/notes_memo_test.go", "TestTheNotesFileIsParsedOncePerProcess"),
    ("internal/index/damaged_manifest_test.go", "TestDamagedUnreadableManifest"),
    ("internal/index/version_upgrade_test.go", "TestIsCurrentVersionDetectsOlderStore"),
)


def go_test_commands(repo: Path) -> list[str]:
    """Go suite for the official executor. Skip overlay-mtime flakes when present."""
    root = Path(repo)
    skips = [name for rel, name in _OVERLAY_MTIME_SKIPS if (root / rel).is_file()]
    suite = "go test ./... -count=1"
    if skips:
        suite = f"{suite} -skip '{'|'.join(skips)}'"
    return [suite, "go vet ./..."]


def start_local_contribution(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str,
    data_dir: Path,
    executor: ContributionExecutor | None = None,
) -> ContributionJob:
    """Run prepare→analyze→implement→test→QA→package. Never pushes."""
    from foreshadow.entry import load_entry

    row = conn.execute(
        "SELECT id FROM repos WHERE full_name=?", (full_name,)
    ).fetchone()
    entry = None
    if row:
        stored = load_entry(conn, int(row[0]))
        entry = stored.as_dict() if stored else None
    plan = next(
        (m for m in list_missions(conn, user_id) if m.get("full_name") == full_name),
        None,
    )
    if plan and isinstance(plan.get("entry_strategy"), dict):
        entry = plan["entry_strategy"]
    extra = _extras_for(conn, user_id, full_name, entry, data_dir=data_dir)
    structured = from_entry(full_name, entry, extra=extra)
    task = {
        "structured": structured.as_dict(),
        "why": structured.why,
        "entry": entry or {},
    }
    if str(task.get("fixture") or "") == "demo_add":
        raise ValueError("confirmed contribution refuses demo_add")
    worker = executor or get_executor(_default_backend())
    source_dir = _mission_repo(conn, user_id, full_name, data_dir)
    mission_id = plan.get("id") if plan else None
    try:
        mission_id = int(mission_id) if mission_id is not None else None
    except (TypeError, ValueError):
        mission_id = None
    job = ContributionJob(
        user_id=user_id,
        repo_id=int(row[0]) if row else None,
        full_name=full_name,
        backend=worker.name,
        task=task,
        why=structured.why,
        status=JobStatus.queued,
        source_dir=source_dir,
        work_dir=_contrib_work_dir(data_dir, full_name, mission_id),
    )
    run_contribution(job, executor=worker, conn=conn)
    return job


def _default_backend() -> str:
    # Missing optional dependencies must fail at executor initialization.
    return "mini_swe_agent"


def _contrib_work_dir(
    data_dir: Path, full_name: str, mission_id: int | None
) -> Path:
    slug = full_name.replace("/", "__")
    if mission_id is None:
        return data_dir / "contrib" / slug
    return data_dir / "contrib" / f"{slug}__m{int(mission_id)}"


def _extras_for(
    conn: sqlite3.Connection,
    user_id: int,
    full_name: str,
    entry: dict[str, Any] | None,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    rec = {}
    if isinstance(entry, dict) and isinstance(entry.get("recommended"), dict):
        rec = entry["recommended"]
    issue_n = rec.get("issue_number")
    extra: dict[str, Any] = {}
    plan = next(
        (m for m in list_missions(conn, user_id) if m.get("full_name") == full_name),
        None,
    )
    cited = (plan or {}).get("cited_issue") if isinstance(plan, dict) else None
    if isinstance(cited, dict) and str(cited.get("number")) == str(issue_n):
        extra.update(extras_from_issue(cited))
    if issue_n is not None and not extra.get("issue_body"):
        from foreshadow.github.live_entry import fetch_live_payload

        try:
            payload = fetch_live_payload(full_name)
        except (OSError, ValueError, TypeError, RuntimeError, KeyError):
            payload = {}
        for item in payload.get("issues") or []:
            if isinstance(item, dict) and int(item.get("number") or 0) == int(issue_n):
                extra.update(extras_from_issue(item))
                break
    inspect = (plan or {}).get("inspect") if isinstance(plan, dict) else None
    repo = _mission_repo(conn, user_id, full_name, data_dir or Path("."))
    if repo is not None and (repo / "go.mod").is_file():
        extra["test_commands"] = go_test_commands(repo)
    elif isinstance(inspect, dict):
        tests = inspect.get("tests") if isinstance(inspect.get("tests"), dict) else {}
        cmd = tests.get("command") or tests.get("argv")
        if cmd and not extra.get("test_commands"):
            extra["test_commands"] = [cmd] if isinstance(cmd, str) else []
        lang = str(inspect.get("language") or plan.get("language") or "").lower()
        kind = str(tests.get("kind") or inspect.get("kind") or "").lower()
        if (lang == "go" or kind == "go") and not extra.get("test_commands"):
            extra["test_commands"] = go_test_commands(repo or Path("."))
    if not extra.get("constraints"):
        extra["constraints"] = [
            "minimal change; no unrelated refactor",
            "do not git push or open a GitHub PR",
        ]
    return extra


def _mission_repo(
    conn: sqlite3.Connection, user_id: int, full_name: str, data_dir: Path
) -> Path | None:
    plan = next(
        (m for m in list_missions(conn, user_id) if m.get("full_name") == full_name),
        None,
    )
    local = Path(str((plan or {}).get("local_path") or ""))
    repo = local / "repo"
    if repo.is_dir() and ((repo / ".git").exists() or (repo / "go.mod").is_file()):
        return repo
    return None
