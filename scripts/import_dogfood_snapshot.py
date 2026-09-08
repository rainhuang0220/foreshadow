#!/usr/bin/env python3
"""Import deja-vu dogfood missions into another Foreshadow DB.

Read-only source. Remaps user/repo/ids. Default is dry-run.
Does not overwrite existing production rows. Does not write to GitHub.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

DEFAULT_REPO = "vshulcz/deja-vu"
DEFAULT_ISSUES = (1828, 1551)
DEFAULT_GITHUB_LOGIN = "rainhuang0220"


class ImportBlocked(Exception):
    """Unresolvable identity, collision policy, or verification failure."""


def _connect_ro(path: Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _issue_from_text(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if text.isdigit():
        n = int(text)
        return n if n > 0 else None
    if text.startswith("#") and text[1:].isdigit():
        return int(text[1:])
    return None


def mission_issue(plan_json: str | None) -> int | None:
    try:
        plan = json.loads(plan_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(plan, dict):
        return None
    for key in ("preferred_issue",):
        n = _issue_from_text(plan.get(key))
        if n:
            return n
    cited = plan.get("cited_issue")
    if isinstance(cited, dict):
        n = _issue_from_text(cited.get("number"))
        if n:
            return n
    active = plan.get("active_entry_target")
    if isinstance(active, dict):
        n = _issue_from_text(active.get("issue_number") or active.get("number"))
        if n:
            return n
    rec = (plan.get("entry_strategy") or {}).get("recommended")
    if isinstance(rec, dict):
        return _issue_from_text(rec.get("issue_number") or rec.get("number"))
    return None


def job_issue(task_json: str | None) -> int | None:
    try:
        task = json.loads(task_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(task, dict):
        return None
    structured = task.get("structured")
    if isinstance(structured, dict):
        n = _issue_from_text(structured.get("issue_number"))
        if n:
            return n
    return _issue_from_text(task.get("issue_number"))


def _sha256(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _canon_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    return _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _mission_fingerprint(row: dict[str, Any]) -> str:
    plan = _canon_json(row.get("plan_json"))
    if isinstance(plan, dict):
        plan = {k: v for k, v in plan.items() if k != "id"}
    return _fingerprint(
        {
            "status": row.get("status"),
            "entry_path": row.get("entry_path"),
            "difficulty": row.get("difficulty"),
            "effort": row.get("effort"),
            "local_path": row.get("local_path"),
            "plan": plan,
        }
    )


def _job_fingerprint(row: dict[str, Any]) -> str:
    return _fingerprint(
        {
            "status": row.get("status"),
            "backend": row.get("backend"),
            "task": _canon_json(row.get("task_json")),
        }
    )


def resolve_prod_user(conn: sqlite3.Connection, github_login: str) -> dict[str, Any]:
    login = (github_login or "").strip()
    if not login:
        raise ImportBlocked("github_login is required")
    rows = conn.execute(
        """
        SELECT id, username, github_id, github_login
        FROM users
        WHERE github_login = ? COLLATE NOCASE
          AND github_id IS NOT NULL
        """,
        (login,),
    ).fetchall()
    if len(rows) != 1:
        raise ImportBlocked(
            f"cannot uniquely resolve GitHub login {login!r}: {len(rows)} matching users"
        )
    user = _row(rows[0])
    if int(user["id"]) < 1:
        raise ImportBlocked("resolved production user id is invalid")
    return user


def resolve_repo(
    conn: sqlite3.Connection, source: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    full_name = source["full_name"]
    found = conn.execute(
        "SELECT * FROM repos WHERE full_name=?", (full_name,)
    ).fetchone()
    if found:
        return _row(found), "reused"
    node_id = source.get("node_id")
    if node_id:
        found = conn.execute("SELECT * FROM repos WHERE node_id=?", (node_id,)).fetchone()
        if found:
            return _row(found), "reused"
    return dict(source), "create"


def _find_mission(
    conn: sqlite3.Connection, user_id: int, full_name: str, issue: int
) -> dict[str, Any] | None:
    rows = conn.execute(
        "SELECT * FROM entry_missions WHERE user_id=? AND full_name=?",
        (user_id, full_name),
    ).fetchall()
    hits = [_row(r) for r in rows if mission_issue(r["plan_json"]) == issue]
    if len(hits) > 1:
        ids = [int(r["id"]) for r in hits]
        raise ImportBlocked(f"multiple production missions for {full_name} #{issue}: {ids}")
    return hits[0] if hits else None


def _find_job(
    conn: sqlite3.Connection,
    user_id: int,
    full_name: str,
    issue: int,
    created_at: str,
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT * FROM contribution_jobs
        WHERE user_id=? AND full_name=? AND created_at=?
        """,
        (user_id, full_name, created_at),
    ).fetchall()
    hits = [_row(r) for r in rows if job_issue(r["task_json"]) == issue]
    if len(hits) > 1:
        raise ImportBlocked(
            f"multiple production jobs for {full_name} #{issue} at {created_at}"
        )
    return hits[0] if hits else None


def _snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = (
        "users",
        "repos",
        "entry_missions",
        "contribution_jobs",
        "contribution_artifacts",
        "contribution_events",
        "entry_analyses",
        "observations",
        "reviews",
    )
    counts = {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
    }
    return {
        "counts": counts,
        "missions": [
            tuple(r)
            for r in conn.execute(
                "SELECT id, user_id, repo_id, full_name, status, plan_json, created_at FROM entry_missions ORDER BY id"
            )
        ],
        "jobs": [
            tuple(r)
            for r in conn.execute(
                "SELECT id, user_id, full_name, status, task_json, created_at FROM contribution_jobs ORDER BY id"
            )
        ],
        "artifacts": [
            tuple(r)
            for r in conn.execute(
                "SELECT id, job_id, kind, body, created_at FROM contribution_artifacts ORDER BY id"
            )
        ],
        "events": [
            tuple(r)
            for r in conn.execute(
                "SELECT id, user_id, mission_id, full_name, event, detail_json, created_at FROM contribution_events ORDER BY id"
            )
        ],
    }


def _collect_source(
    source: sqlite3.Connection, *, repo: str, issues: tuple[int, ...]
) -> dict[str, Any]:
    repo_row = source.execute(
        "SELECT * FROM repos WHERE full_name=?", (repo,)
    ).fetchone()
    if repo_row is None:
        raise ImportBlocked(f"source repo {repo} not found")
    missions = []
    source_user_ids: set[int] = set()
    for row in source.execute(
        "SELECT * FROM entry_missions WHERE full_name=? ORDER BY created_at, id",
        (repo,),
    ):
        issue = mission_issue(row["plan_json"])
        if issue not in issues:
            continue
        item = _row(row)
        item["issue"] = issue
        missions.append(item)
        source_user_ids.add(int(row["user_id"]))
    if not missions:
        raise ImportBlocked(f"no source missions for {repo} issues {issues}")
    found_issues = {m["issue"] for m in missions}
    missing = [n for n in issues if n not in found_issues]
    if missing:
        raise ImportBlocked(f"source missing missions for issues {missing}")
    if len(source_user_ids) != 1:
        raise ImportBlocked(f"source missions span multiple users: {sorted(source_user_ids)}")

    jobs = []
    latest_ok: dict[int, dict[str, Any]] = {}
    for row in source.execute(
        "SELECT * FROM contribution_jobs WHERE full_name=? ORDER BY created_at, id",
        (repo,),
    ):
        issue = job_issue(row["task_json"])
        if issue not in issues:
            continue
        pkg_row = source.execute(
            """
            SELECT id, body FROM contribution_artifacts
            WHERE job_id=? AND kind='package' AND body IS NOT NULL AND body != ''
            ORDER BY id DESC LIMIT 1
            """,
            (row["id"],),
        ).fetchone()
        if pkg_row is None:
            continue
        try:
            pkg = json.loads(pkg_row["body"])
        except json.JSONDecodeError:
            continue
        if int(pkg.get("remote_writes") or 0) != 0:
            continue
        tests = pkg.get("tests") if isinstance(pkg.get("tests"), dict) else {}
        qa_ok = pkg.get("qa_ok") is True or pkg.get("qa") == "PASS"
        tests_ok = tests.get("ok") is True if tests else qa_ok
        if not (qa_ok and tests_ok):
            continue
        item = _row(row)
        item["issue"] = issue
        item["package_id"] = int(pkg_row["id"])
        latest_ok[issue] = item
    jobs = sorted(latest_ok.values(), key=lambda item: (str(item["created_at"]), int(item["id"])))
    job_ids = [int(j["id"]) for j in jobs]
    if not job_ids:
        raise ImportBlocked("no source jobs with successful package snapshots")

    artifacts = []
    for row in source.execute(
        f"""
        SELECT * FROM contribution_artifacts
        WHERE job_id IN ({",".join("?" * len(job_ids))})
        ORDER BY created_at, id
        """,
        job_ids,
    ):
        artifacts.append(_row(row))

    mission_ids = [int(m["id"]) for m in missions]
    events = []
    for row in source.execute(
        f"""
        SELECT * FROM contribution_events
        WHERE mission_id IN ({",".join("?" * len(mission_ids))})
        ORDER BY id
        """,
        mission_ids,
    ):
        events.append(_row(row))

    packages = []
    for art in artifacts:
        if art["kind"] != "package":
            continue
        try:
            pkg = json.loads(art["body"] or "")
        except json.JSONDecodeError as exc:
            raise ImportBlocked(f"source package {art['id']} is not JSON") from exc
        if int(pkg.get("remote_writes") or 0) != 0:
            raise ImportBlocked(f"source package {art['id']} has remote_writes != 0")
        packages.append(
            {
                "source_id": art["id"],
                "job_id": art["job_id"],
                "sha256": _sha256(art["body"]),
                "bytes": len(art["body"] or ""),
                "related_issue": pkg.get("related_issue"),
                "files_n": pkg.get("files_changed_n"),
                "qa": pkg.get("qa"),
                "status": pkg.get("status"),
                "remote_writes": pkg.get("remote_writes"),
            }
        )
    return {
        "repo": _row(repo_row),
        "source_user_id": next(iter(source_user_ids)),
        "missions": missions,
        "jobs": jobs,
        "artifacts": artifacts,
        "events": events,
        "packages": packages,
    }


def _build_plan(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    *,
    github_login: str,
    repo: str,
    issues: tuple[int, ...],
    dry_run: bool,
) -> dict[str, Any]:
    integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ImportBlocked(f"target integrity_check={integrity}")
    schema = [int(r[0]) for r in target.execute("SELECT version FROM schema_migrations ORDER BY 1")]
    collected = _collect_source(source, repo=repo, issues=issues)
    prod_user = resolve_prod_user(target, github_login)
    if int(prod_user["id"]) == int(collected["source_user_id"]):
        # Allowed only if it is actually the same GitHub identity, never assumed.
        pass
    repo_row, resolution = resolve_repo(target, collected["repo"])
    snapshot = _snapshot(target)

    mission_map: dict[int, int | str] = {}
    job_map: dict[int, int | str] = {}
    artifact_map: dict[int, int | str] = {}
    event_map: dict[int, int | str] = {}
    inserts = {
        "entry_missions": 0,
        "contribution_jobs": 0,
        "contribution_artifacts": 0,
        "contribution_events": 0,
        "repos": 0,
    }
    skips: list[dict[str, Any]] = []

    if resolution == "create":
        inserts["repos"] = 1

    mission_action: dict[int, str] = {}
    for mission in collected["missions"]:
        existing = _find_mission(
            target, int(prod_user["id"]), repo, int(mission["issue"])
        )
        if existing is not None:
            if _mission_fingerprint(mission) != _mission_fingerprint(existing):
                raise ImportBlocked(
                    f"ABORT_CONFLICT: mission {repo} #{mission['issue']} exists with different content"
                )
            mission_map[int(mission["id"])] = int(existing["id"])
            mission_action[int(mission["issue"])] = "SKIP"
            skips.append(
                {
                    "table": "entry_missions",
                    "source_id": mission["id"],
                    "target_id": int(existing["id"]),
                    "reason": "IDEMPOTENT_SKIP",
                }
            )
            continue
        mission_map[int(mission["id"])] = "INSERT"
        mission_action[int(mission["issue"])] = "INSERT"
        inserts["entry_missions"] += 1

    for job in collected["jobs"]:
        existing = _find_job(
            target,
            int(prod_user["id"]),
            repo,
            int(job["issue"]),
            str(job["created_at"]),
        )
        issue = int(job["issue"])
        if existing is not None:
            if _job_fingerprint(job) != _job_fingerprint(existing):
                raise ImportBlocked(
                    f"ABORT_CONFLICT: job {repo} #{issue} exists with different content"
                )
            if mission_action.get(issue) == "INSERT":
                raise ImportBlocked(
                    f"ABORT_CONFLICT: half-set for {repo} #{issue}: job exists, mission would be inserted"
                )
            job_map[int(job["id"])] = int(existing["id"])
            skips.append(
                {
                    "table": "contribution_jobs",
                    "source_id": job["id"],
                    "target_id": int(existing["id"]),
                    "reason": "IDEMPOTENT_SKIP",
                }
            )
            continue
        if mission_action.get(issue) == "SKIP":
            raise ImportBlocked(
                f"ABORT_CONFLICT: half-set for {repo} #{issue}: mission exists, job would be inserted"
            )
        job_map[int(job["id"])] = "INSERT"
        inserts["contribution_jobs"] += 1

    for art in collected["artifacts"]:
        src_job = int(art["job_id"])
        mapped_job = job_map.get(src_job)
        if mapped_job == "INSERT":
            artifact_map[int(art["id"])] = "INSERT"
            inserts["contribution_artifacts"] += 1
            continue
        if isinstance(mapped_job, int):
            existing = target.execute(
                """
                SELECT id, body FROM contribution_artifacts
                WHERE job_id=? AND kind=?
                ORDER BY id
                """,
                (mapped_job, art["kind"]),
            ).fetchall()
            match = [int(r["id"]) for r in existing if r["body"] == art["body"]]
            if match:
                artifact_map[int(art["id"])] = match[0]
                skips.append(
                    {
                        "table": "contribution_artifacts",
                        "source_id": art["id"],
                        "target_id": match[0],
                        "reason": "IDEMPOTENT_SKIP",
                    }
                )
                continue
            if existing:
                raise ImportBlocked(
                    f"ABORT_CONFLICT: artifact kind {art['kind']!r} for job {mapped_job} exists with different content"
                )
            raise ImportBlocked(
                f"ABORT_CONFLICT: half-set for job {mapped_job}: {art['kind']} would be inserted under skipped job"
            )
        raise ImportBlocked(f"artifact {art['id']} job {src_job} was not mapped")

    for event in collected["events"]:
        src_mid = int(event["mission_id"])
        mapped_mid = mission_map.get(src_mid)
        if mapped_mid == "INSERT":
            event_map[int(event["id"])] = "INSERT"
            inserts["contribution_events"] += 1
            continue
        if isinstance(mapped_mid, int):
            existing = target.execute(
                """
                SELECT id FROM contribution_events
                WHERE user_id=? AND mission_id=? AND event=? AND created_at=?
                """,
                (int(prod_user["id"]), mapped_mid, event["event"], event["created_at"]),
            ).fetchone()
            if existing:
                event_map[int(event["id"])] = int(existing["id"])
                skips.append(
                    {
                        "table": "contribution_events",
                        "source_id": event["id"],
                        "target_id": int(existing["id"]),
                        "reason": "IDEMPOTENT_SKIP",
                    }
                )
                continue
            raise ImportBlocked(
                f"ABORT_CONFLICT: half-set for mission {mapped_mid}: event would be inserted under skipped mission"
            )
        raise ImportBlocked(f"event {event['id']} mission {src_mid} was not mapped")

    return {
        "dry_run": dry_run,
        "source_user_id": collected["source_user_id"],
        "prod_user": prod_user,
        "mapping_rule": "LOCAL_USER_ID -> PROD_USER_ID via github_login + github_id",
        "repo": {
            "full_name": repo,
            "source_id": collected["repo"]["id"],
            "target_id": repo_row.get("id"),
            "node_id": collected["repo"].get("node_id"),
            "resolution": resolution,
        },
        "issues": list(issues),
        "schema": schema,
        "integrity": integrity,
        "preserve_snapshot": {
            "counts": snapshot["counts"],
            "existing_mission_ids": [row[0] for row in snapshot["missions"]],
            "existing_job_ids": [row[0] for row in snapshot["jobs"]],
            "existing_artifact_ids": [row[0] for row in snapshot["artifacts"]],
        },
        "inserts": inserts,
        "skips": skips,
        "existing_rows_updated": 0,
        "existing_rows_deleted": 0,
        "conflicts": 0,
        "new_rows_planned": sum(inserts.values()),
        "id_mapping": {
            "missions": mission_map,
            "jobs": job_map,
            "artifacts": artifact_map,
            "events": event_map,
        },
        "packages": collected["packages"],
        "source": collected,
        "target_repo": repo_row,
        "pre_snapshot": snapshot,
    }


def plan_import(
    source_path: Path | str,
    target_path: Path | str,
    *,
    github_login: str = DEFAULT_GITHUB_LOGIN,
    repo: str = DEFAULT_REPO,
    issues: tuple[int, ...] = DEFAULT_ISSUES,
) -> dict[str, Any]:
    source = _connect_ro(Path(source_path))
    target = _connect_ro(Path(target_path))
    try:
        return _build_plan(
            source,
            target,
            github_login=github_login,
            repo=repo,
            issues=issues,
            dry_run=True,
        )
    finally:
        source.close()
        target.close()


def _create_repo(conn: sqlite3.Connection, source: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO repos(
          node_id, database_id, full_name, owner, name, html_url, description,
          language, license_spdx, created_at, default_branch, has_issues,
          is_fork, is_archived, is_disabled, is_empty, is_template, is_mirror,
          status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            source.get("node_id"),
            source.get("database_id"),
            source["full_name"],
            source.get("owner") or source["full_name"].split("/", 1)[0],
            source.get("name") or source["full_name"].split("/", 1)[1],
            source.get("html_url"),
            source.get("description"),
            source.get("language"),
            source.get("license_spdx"),
            source.get("created_at"),
            source.get("default_branch"),
            source.get("has_issues"),
            source.get("is_fork") or 0,
            source.get("is_archived") or 0,
            source.get("is_disabled") or 0,
            source.get("is_empty") or 0,
            source.get("is_template") or 0,
            source.get("is_mirror") or 0,
            source.get("status") or "active",
            source.get("first_seen_at") or source.get("last_seen_at"),
            source.get("last_seen_at") or source.get("first_seen_at"),
        ),
    )
    return int(cur.lastrowid)


def _rewrite_plan(plan_json: str, new_id: int) -> str:
    try:
        plan = json.loads(plan_json or "{}")
    except json.JSONDecodeError:
        plan = {}
    if isinstance(plan, dict):
        plan["id"] = new_id
    return json.dumps(plan, ensure_ascii=False)


def _verify(
    conn: sqlite3.Connection,
    plan: dict[str, Any],
    pre: dict[str, Any],
    mapping: dict[str, dict[int, int]],
) -> None:
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ImportBlocked(f"post-import integrity_check={integrity}")
    fk = list(conn.execute("PRAGMA foreign_key_check"))
    if fk:
        raise ImportBlocked(f"foreign_key_check failed: {fk[:8]}")

    post = _snapshot(conn)
    if post["missions"][: len(pre["missions"])] != pre["missions"]:
        raise ImportBlocked("existing missions were mutated")
    if post["jobs"][: len(pre["jobs"])] != pre["jobs"]:
        raise ImportBlocked("existing jobs were mutated")
    if post["artifacts"][: len(pre["artifacts"])] != pre["artifacts"]:
        raise ImportBlocked("existing artifacts were mutated")
    if post["events"][: len(pre["events"])] != pre["events"]:
        raise ImportBlocked("existing events were mutated")

    prod_uid = int(plan["prod_user"]["id"])
    repo = plan["repo"]["full_name"]
    missions = list(
        conn.execute(
            """
            SELECT id, plan_json FROM entry_missions
            WHERE user_id=? AND full_name=? AND status != 'ABANDONED'
            ORDER BY id DESC
            """,
            (prod_uid, repo),
        )
    )
    if not missions:
        raise ImportBlocked("no imported missions visible to production user")
    active_issue = mission_issue(missions[0]["plan_json"])
    if active_issue != 1551:
        raise ImportBlocked(f"active mission would be #{active_issue}, expected #1551")
    issues = [mission_issue(r["plan_json"]) for r in missions]
    if 1828 not in issues:
        raise ImportBlocked("history mission #1828 missing after import")
    if 308 in issues:
        raise ImportBlocked("#308 must not become a mission")

    for src_id, digest in (
        (item["source_id"], item["sha256"]) for item in plan["packages"]
    ):
        dst = mapping["artifacts"][int(src_id)]
        body = conn.execute(
            "SELECT body FROM contribution_artifacts WHERE id=?", (dst,)
        ).fetchone()
        if body is None or _sha256(body[0]) != digest:
            raise ImportBlocked(f"package {src_id} snapshot was not preserved")
        pkg = json.loads(body[0])
        if int(pkg.get("remote_writes") or 0) != 0:
            raise ImportBlocked("imported package remote_writes != 0")


def apply_import(
    source_path: Path | str,
    target_path: Path | str,
    *,
    github_login: str = DEFAULT_GITHUB_LOGIN,
    repo: str = DEFAULT_REPO,
    issues: tuple[int, ...] = DEFAULT_ISSUES,
) -> dict[str, Any]:
    source = _connect_ro(Path(source_path))
    target = _connect_rw(Path(target_path))
    target.isolation_level = None
    try:
        plan = _build_plan(
            source,
            target,
            github_login=github_login,
            repo=repo,
            issues=issues,
            dry_run=False,
        )
        collected = plan["source"]
        prod_uid = int(plan["prod_user"]["id"])
        pre = plan["pre_snapshot"]
        mapping = {
            "missions": {int(k): v for k, v in plan["id_mapping"]["missions"].items() if v != "INSERT"},
            "jobs": {int(k): v for k, v in plan["id_mapping"]["jobs"].items() if v != "INSERT"},
            "artifacts": {
                int(k): v for k, v in plan["id_mapping"]["artifacts"].items() if v != "INSERT"
            },
            "events": {int(k): v for k, v in plan["id_mapping"]["events"].items() if v != "INSERT"},
        }

        target.execute("BEGIN IMMEDIATE")
        try:
            repo_id = plan["repo"]["target_id"]
            if plan["repo"]["resolution"] == "create":
                repo_id = _create_repo(target, collected["repo"])
                plan["repo"]["target_id"] = repo_id
            repo_id = int(repo_id)

            for mission in collected["missions"]:
                src_id = int(mission["id"])
                if plan["id_mapping"]["missions"][src_id] != "INSERT":
                    mapping["missions"][src_id] = int(plan["id_mapping"]["missions"][src_id])
                    continue
                cur = target.execute(
                    """
                    INSERT INTO entry_missions(
                      user_id, repo_id, full_name, status, entry_path, difficulty, effort,
                      plan_json, local_path, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        prod_uid,
                        repo_id,
                        mission["full_name"],
                        mission["status"],
                        mission["entry_path"],
                        mission["difficulty"],
                        mission["effort"],
                        mission["plan_json"],
                        mission["local_path"],
                        mission["created_at"],
                        mission["updated_at"],
                    ),
                )
                new_id = int(cur.lastrowid)
                target.execute(
                    "UPDATE entry_missions SET plan_json=? WHERE id=? AND user_id=?",
                    (_rewrite_plan(mission["plan_json"], new_id), new_id, prod_uid),
                )
                mapping["missions"][src_id] = new_id

            for job in collected["jobs"]:
                src_id = int(job["id"])
                if plan["id_mapping"]["jobs"][src_id] != "INSERT":
                    mapping["jobs"][src_id] = int(plan["id_mapping"]["jobs"][src_id])
                    continue
                cur = target.execute(
                    """
                    INSERT INTO contribution_jobs(
                      user_id, repo_id, full_name, status, backend, task_json, log_json,
                      created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        prod_uid,
                        repo_id,
                        job["full_name"],
                        job["status"],
                        job["backend"],
                        job["task_json"],
                        job["log_json"],
                        job["created_at"],
                        job["updated_at"],
                    ),
                )
                mapping["jobs"][src_id] = int(cur.lastrowid)

            for art in collected["artifacts"]:
                src_id = int(art["id"])
                if plan["id_mapping"]["artifacts"][src_id] != "INSERT":
                    mapping["artifacts"][src_id] = int(plan["id_mapping"]["artifacts"][src_id])
                    continue
                job_id = mapping["jobs"][int(art["job_id"])]
                cur = target.execute(
                    """
                    INSERT INTO contribution_artifacts(
                      job_id, kind, path, body, meta_json, created_at
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        art["kind"],
                        art["path"],
                        art["body"],
                        art["meta_json"],
                        art["created_at"],
                    ),
                )
                mapping["artifacts"][src_id] = int(cur.lastrowid)

            for event in collected["events"]:
                src_id = int(event["id"])
                if plan["id_mapping"]["events"][src_id] != "INSERT":
                    mapping["events"][src_id] = int(plan["id_mapping"]["events"][src_id])
                    continue
                cur = target.execute(
                    """
                    INSERT INTO contribution_events(
                      user_id, mission_id, full_name, event, detail_json, created_at
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        prod_uid,
                        mapping["missions"][int(event["mission_id"])],
                        event["full_name"],
                        event["event"],
                        event["detail_json"],
                        event["created_at"],
                    ),
                )
                mapping["events"][src_id] = int(cur.lastrowid)

            _verify(target, plan, pre, mapping)
            target.execute("COMMIT")
        except Exception:
            target.execute("ROLLBACK")
            raise

        plan["id_mapping"] = mapping
        plan["dry_run"] = False
        plan.pop("source", None)
        plan.pop("target_repo", None)
        plan.pop("pre_snapshot", None)
        return plan
    finally:
        source.close()
        target.close()


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    out = {
        "dry_run": plan["dry_run"],
        "source_user_id": plan["source_user_id"],
        "prod_user": plan["prod_user"],
        "mapping_rule": plan["mapping_rule"],
        "repo": plan["repo"],
        "issues": plan["issues"],
        "schema": plan["schema"],
        "integrity": plan["integrity"],
        "preserve_snapshot": plan["preserve_snapshot"],
        "inserts": plan["inserts"],
        "skips": plan["skips"],
        "existing_rows_updated": plan["existing_rows_updated"],
        "existing_rows_deleted": plan["existing_rows_deleted"],
        "conflicts": plan["conflicts"],
        "new_rows_planned": plan["new_rows_planned"],
        "id_mapping": plan["id_mapping"],
        "packages": plan["packages"],
    }
    return out


def _print_mapping(plan: dict[str, Any]) -> None:
    user = plan["prod_user"]
    repo = plan["repo"]
    src = plan["source_user_id"]
    mapping = plan["id_mapping"]
    missions = mapping.get("missions") or {}
    jobs = mapping.get("jobs") or {}
    artifacts = mapping.get("artifacts") or {}
    sys.stderr.write(
        "\n".join(
            [
                "USER",
                f"local {src}",
                f"→ prod {user['id']}",
                f"verified GitHub {user.get('github_login')}",
                "",
                "REPO",
                f"local {repo.get('source_id')}",
                f"→ prod {repo.get('target_id')}",
                f"{repo.get('resolution')}",
                "",
                "ROUND 1",
                f"mission 1 → {missions.get(1) or missions.get('1')}",
                f"job 2 → {jobs.get(2) or jobs.get('2')}",
                f"artifacts 5–8 → { {k: artifacts.get(k) or artifacts.get(str(k)) for k in (5, 6, 7, 8)} }",
                "",
                "ROUND 2",
                f"mission 2 → {missions.get(2) or missions.get('2')}",
                f"job 6 → {jobs.get(6) or jobs.get('6')}",
                f"artifacts 13–16 → { {k: artifacts.get(k) or artifacts.get(str(k)) for k in (13, 14, 15, 16)} }",
                "",
                f"existing rows updated = {plan.get('existing_rows_updated', 0)}",
                f"existing rows deleted = {plan.get('existing_rows_deleted', 0)}",
                f"conflicts = {plan.get('conflicts', 0)}",
                f"new rows planned = {plan.get('new_rows_planned', sum((plan.get('inserts') or {}).values()))}",
                "",
            ]
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Read-only dogfood sqlite path")
    parser.add_argument("--target", required=True, help="Production sqlite path")
    parser.add_argument("--github-login", default=DEFAULT_GITHUB_LOGIN)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--issues",
        default=",".join(str(n) for n in DEFAULT_ISSUES),
        help="Comma-separated issue numbers",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit remapped inserts. Default is dry-run.",
    )
    args = parser.parse_args(argv)
    issues = tuple(int(part.strip()) for part in args.issues.split(",") if part.strip())
    try:
        if args.apply:
            plan = apply_import(
                args.source,
                args.target,
                github_login=args.github_login,
                repo=args.repo,
                issues=issues,
            )
        else:
            plan = plan_import(
                args.source,
                args.target,
                github_login=args.github_login,
                repo=args.repo,
                issues=issues,
            )
    except ImportBlocked as exc:
        sys.stderr.write(f"IMPORT_BLOCKED: {exc}\n")
        return 2
    public = _public_plan(plan)
    _print_mapping(public)
    json.dump(public, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
