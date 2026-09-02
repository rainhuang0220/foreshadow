"""Contribution executor protocol. Coding backends are pluggable.

Foreshadow orchestrates prepare → analyze → implement → test → iterate →
patch → QA. It never git-pushes, never opens PRs, and never talks to GitHub
mutations. Remote writes stay blocked.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class JobStatus(StrEnum):
    queued = "queued"
    preparing = "preparing"
    implementing = "implementing"
    testing = "testing"
    qa = "qa"
    ready = "ready"
    waiting_approval = "waiting_approval"
    failed = "failed"
    refused_remote = "refused_remote"


class ContributionError(Exception):
    """Executor failed before a patch was ready."""


class BackendNotInstalled(ContributionError):
    """Optional coding backend extra is not installed."""


class RemoteWriteRefused(ContributionError):
    """GitHub mutation or git push was blocked."""


@dataclass
class ContributionJob:
    full_name: str
    task: dict[str, Any] = field(default_factory=dict)
    backend: str = "native"
    status: JobStatus = JobStatus.queued
    user_id: int = 0
    repo_id: int | None = None
    id: int | None = None
    log: list[dict[str, Any]] = field(default_factory=list)
    source_dir: Path | None = None
    sandbox_path: Path | None = None
    work_dir: Path | None = None
    test_result: dict[str, Any] | None = None
    why: str = ""
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.source_dir is not None:
            self.source_dir = Path(self.source_dir)
        if self.sandbox_path is not None:
            self.sandbox_path = Path(self.sandbox_path)
        if self.work_dir is not None:
            self.work_dir = Path(self.work_dir)
        if not isinstance(self.status, JobStatus):
            self.status = JobStatus(str(self.status))
        if self.task is None:
            self.task = {}
        if not self.why:
            self.why = str(self.task.get("why") or "")


@dataclass
class PatchArtifact:
    diff: str
    why: str = ""
    test_log: str = ""
    files: list[str] = field(default_factory=list)
    title: str = ""
    body: str = ""
    risk: str = "local sandbox only; remote GitHub writes are refused"
    tests_passed: bool = False
    qa_ok: bool = False
    qa_reasons: list[str] = field(default_factory=list)


@runtime_checkable
class ContributionExecutor(Protocol):
    name: str

    def prepare(self, job: ContributionJob) -> None: ...

    def analyze(self, job: ContributionJob) -> None: ...

    def implement(self, job: ContributionJob) -> None: ...

    def test(self, job: ContributionJob) -> None: ...

    def iterate(self, job: ContributionJob) -> None: ...

    def produce_patch(self, job: ContributionJob) -> PatchArtifact: ...


def refuse_remote(action: str) -> dict[str, Any]:
    """Always blocked. Foreshadow does not push, open PRs, or mutate GitHub."""
    from foreshadow.mission import refuse_remote_action

    out = dict(refuse_remote_action(action))
    out["status"] = JobStatus.refused_remote.value
    return out


def get_executor(name: str | None) -> ContributionExecutor:
    key = (name or "native").strip().lower()
    if key in {"", "native"}:
        from foreshadow.contribution.native import NativeExecutor

        return NativeExecutor()
    if key in {"mini_swe", "mini_swe_agent", "minisweagent"}:
        from foreshadow.contribution.mini_swe import MiniSweExecutor

        return MiniSweExecutor()
    if key in {"openhands", "open_hands"}:
        from foreshadow.contribution.openhands import OpenHandsExecutor

        return OpenHandsExecutor()
    raise BackendNotInstalled(
        f"unknown contribution backend {name!r}; "
        "Foreshadow ships native, plus optional mini_swe_agent / openhands extras"
    )


def run_contribution(
    job: ContributionJob,
    *,
    executor: ContributionExecutor | None = None,
    conn: sqlite3.Connection | None = None,
) -> PatchArtifact:
    """Drive the protocol, quality-gate the patch, persist job + artifacts."""
    from foreshadow.contribution.jobs import persist_artifact
    from foreshadow.contribution.qa import gate

    worker = executor or get_executor(job.backend)
    job.backend = worker.name
    artifact: PatchArtifact | None = None
    try:
        job.status = JobStatus.queued
        _save(conn, job)
        job.status = JobStatus.preparing
        _save(conn, job)
        worker.prepare(job)
        worker.analyze(job)
        job.status = JobStatus.implementing
        _save(conn, job)
        worker.implement(job)
        job.status = JobStatus.testing
        _save(conn, job)
        worker.test(job)
        worker.iterate(job)
        artifact = worker.produce_patch(job)
        job.status = JobStatus.qa
        _save(conn, job)
        verdict = gate(job, artifact)
        artifact.qa_ok = verdict.ok
        artifact.qa_reasons = list(verdict.reasons)
        if conn is not None and job.id is not None:
            persist_artifact(
                conn,
                job.id,
                kind="diff",
                body=artifact.diff,
                meta={"files": artifact.files, "tests_passed": artifact.tests_passed},
            )
            persist_artifact(
                conn,
                job.id,
                kind="test_log",
                body=artifact.test_log,
                meta={"ok": artifact.tests_passed},
            )
            persist_artifact(
                conn,
                job.id,
                kind="qa",
                body="\n".join(verdict.reasons) if verdict.reasons else "ok",
                meta={"ok": verdict.ok, "reasons": list(verdict.reasons)},
            )
        if not verdict.ok:
            job.status = JobStatus.failed
            job.log.append(
                {"step": "qa", "ok": False, "reasons": list(verdict.reasons)}
            )
            _save(conn, job)
            return artifact
        job.status = JobStatus.ready
        job.log.append({"step": "qa", "ok": True})
        _save(conn, job)
        return artifact
    except RemoteWriteRefused as exc:
        job.status = JobStatus.refused_remote
        job.log.append({"step": "refused_remote", "error": str(exc)})
        _save(conn, job)
        raise
    except Exception as exc:
        job.status = JobStatus.failed
        job.log.append({"step": "failed", "error": f"{type(exc).__name__}: {exc}"})
        _save(conn, job)
        raise


def _save(conn: sqlite3.Connection | None, job: ContributionJob) -> None:
    if conn is None:
        return
    from foreshadow.contribution.jobs import persist_job

    persist_job(conn, job)
