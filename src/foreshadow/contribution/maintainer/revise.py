"""Append a safer PR-draft package revision. Never overwrite the original artifact."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from foreshadow.contribution.jobs import persist_artifact
from foreshadow.contribution.maintainer.context import MaintainerDraftContext
from foreshadow.contribution.maintainer.draft import compose_and_gate


def revise_package_draft(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    context: MaintainerDraftContext,
) -> int:
    from foreshadow.contribution.review import latest_package

    packed = latest_package(conn, job_id)
    if packed is None:
        raise KeyError("package not found")
    pkg, old_id = packed
    if not isinstance(pkg, dict):
        raise KeyError("package not found")
    draft, gate = compose_and_gate(context)
    new_pkg: dict[str, Any] = dict(pkg)
    new_pkg["pr_title"] = draft.title
    new_pkg["pr_body"] = draft.body
    new_pkg["maintainer_output_gate"] = gate.as_dict()
    new_pkg["pr_draft_revision"] = int(pkg.get("pr_draft_revision") or 1) + 1
    new_pkg["supersedes_package_artifact_id"] = old_id
    new_pkg["draft_status"] = "current"
    new_pkg["issue_title"] = context.issue_title
    new_pkg["issue_body"] = context.issue_body
    if gate.ok:
        new_pkg["remote_status"] = pkg.get("remote_status") or "WAITING_USER_APPROVAL"
    else:
        new_pkg["remote_status"] = "MAINTAINER_OUTPUT_UNSAFE"
    return persist_artifact(
        conn,
        job_id,
        kind="package",
        body=json.dumps(new_pkg, ensure_ascii=False, indent=2),
        meta={
            "draft_status": "current",
            "supersedes": old_id,
            "role": "pr_draft_revision",
            "safety_ok": gate.ok,
        },
    )
