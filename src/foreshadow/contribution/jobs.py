"""SQLite persistence for contribution_jobs / contribution_artifacts."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from foreshadow.contribution.executor import ContributionJob, JobStatus


def persist_job(conn: sqlite3.Connection, job: ContributionJob) -> int:
    now = datetime.now(UTC).isoformat()
    job.updated_at = now
    if not job.created_at:
        job.created_at = now
    task_json = json.dumps(job.task or {}, ensure_ascii=False)
    log_json = json.dumps(job.log or [], ensure_ascii=False)
    status = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
    if job.id is None:
        cur = conn.execute(
            """
            INSERT INTO contribution_jobs(
              user_id, repo_id, full_name, status, backend, task_json, log_json,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                job.user_id,
                job.repo_id,
                job.full_name,
                status,
                job.backend,
                task_json,
                log_json,
                job.created_at,
                job.updated_at,
            ),
        )
        job.id = int(cur.lastrowid)
    else:
        conn.execute(
            """
            UPDATE contribution_jobs
            SET repo_id=?, full_name=?, status=?, backend=?, task_json=?,
                log_json=?, updated_at=?
            WHERE id=? AND user_id=?
            """,
            (
                job.repo_id,
                job.full_name,
                status,
                job.backend,
                task_json,
                log_json,
                job.updated_at,
                job.id,
                job.user_id,
            ),
        )
    conn.commit()
    return int(job.id)


def persist_artifact(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    kind: str,
    body: str | None = None,
    path: str | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        """
        INSERT INTO contribution_artifacts(
          job_id, kind, path, body, meta_json, created_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            job_id,
            kind,
            path,
            body,
            json.dumps(meta or {}, ensure_ascii=False),
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def load_job(
    conn: sqlite3.Connection, job_id: int, *, user_id: int | None = None
) -> ContributionJob | None:
    if user_id is None:
        row = conn.execute(
            """
            SELECT id, user_id, repo_id, full_name, status, backend, task_json,
                   log_json, created_at, updated_at
            FROM contribution_jobs WHERE id=?
            """,
            (job_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, user_id, repo_id, full_name, status, backend, task_json,
                   log_json, created_at, updated_at
            FROM contribution_jobs WHERE id=? AND user_id=?
            """,
            (job_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def list_jobs(conn: sqlite3.Connection, user_id: int) -> list[ContributionJob]:
    rows = conn.execute(
        """
        SELECT id, user_id, repo_id, full_name, status, backend, task_json,
               log_json, created_at, updated_at
        FROM contribution_jobs WHERE user_id=? ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_artifacts(conn: sqlite3.Connection, job_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, kind, path, body, meta_json, created_at
        FROM contribution_artifacts WHERE job_id=? ORDER BY id ASC
        """,
        (job_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            meta = json.loads(row[4] or "{}")
        except json.JSONDecodeError:
            meta = {}
        out.append(
            {
                "id": row[0],
                "kind": row[1],
                "path": row[2],
                "body": row[3],
                "meta": meta,
                "created_at": row[5],
            }
        )
    return out


def _row_to_job(row: tuple[Any, ...]) -> ContributionJob:
    try:
        task = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        task = {}
    try:
        log = json.loads(row[7] or "[]")
    except json.JSONDecodeError:
        log = []
    if not isinstance(task, dict):
        task = {}
    if not isinstance(log, list):
        log = []
    return ContributionJob(
        id=int(row[0]),
        user_id=int(row[1]),
        repo_id=int(row[2]) if row[2] is not None else None,
        full_name=str(row[3]),
        status=JobStatus(str(row[4])),
        backend=str(row[5]),
        task=task,
        log=list(log),
        created_at=str(row[8]) if row[8] is not None else None,
        updated_at=str(row[9]) if row[9] is not None else None,
    )
