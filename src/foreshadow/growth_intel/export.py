"""Export one experiment as generic Engineering Work Order v1.

Research fields stay in the growth plan. The work order receives only the
bounded file task, with the epistemic status written in ordinary text.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from foreshadow.work_order import dumps, validate


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps need a timezone")
    return value.astimezone(tz=value.tzinfo).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed


def export_work_order(
    plan: dict, *, now: datetime, repository_path: Path | None = None
) -> dict:
    experiment = plan.get("recommended_experiment")
    record = plan.get("target_record")
    if not experiment or not record:
        raise ValueError("no exportable experiment")
    if experiment.get("exportable") is False:
        raise ValueError("experiment requires external-write and cannot be a work order")
    if experiment["target"] != plan["target_identity"] or experiment["target"] != record["identity"]:
        raise ValueError("repository identity does not match the experiment")
    if now.tzinfo is None:
        raise ValueError("timestamps need a timezone")
    if now >= _parse(plan["expires_at"]):
        raise ValueError("stale evidence cannot be exported")
    if _parse(record["observation_time"]) > now:
        raise ValueError("future observation")
    path = None
    if repository_path is not None:
        path = str(Path(repository_path).expanduser().resolve())
        if not Path(path).is_absolute():
            raise ValueError("repository path must be absolute")
    if path is None and not record.get("html_url"):
        raise ValueError("repository needs a local path or URL")
    observed = record["observation_time"]
    observation_id = "obs-install-conflict"
    inference_id = "inf-install-hypothesis"
    counter = plan["hypothesis"]["counterevidence"][0]
    detail = record.get("install_conflict_detail")
    if detail:
        observed_summary = (
            f"On {observed}, {record['identity']}: {detail} OBSERVED. This is not a causal claim."
        )
    else:
        observed_summary = (
            f"On {observed}, {record['identity']} documented install paths that do not "
            "name the same version. OBSERVED. This is not a causal claim."
        )
    rationale = (
        f"{plan['hypothesis']['text']} Counterevidence: {counter} "
        "Evidence strength: HYPOTHESIS. This is not a contribution opportunity "
        "and it is not a causal claim."
    )
    order = {
        "schema": "engineering.work-order",
        "version": 1,
        "task_id": "pending",
        "origin": {"name": "foreshadow", "reference": experiment["id"]},
        "repository": {
            "identity": record["identity"],
            "path": path,
            "url": record.get("html_url"),
            "base_revision": record["default_branch_sha"],
        },
        "title": experiment["title"],
        "objective": (
            (
                f"On {record['identity']}, make README.md and Formula/wheretoken.rb name v0.7.7. "
                "Point the in-repo formula at refs/tags/v0.7.7.tar.gz. Do not cut a release."
            )
            if detail and "v0.7.7" in detail and "v0.7.6" in detail
            else (
                f"On {record['identity']}, make README and Formula/wheretoken.rb name the same "
                "version and one primary install command. Do not cut a release."
            )
        ),
        "rationale": rationale,
        "evidence": [
            {
                "id": observation_id,
                "kind": "observation",
                "summary": observed_summary,
                "source": record["source_url"],
                "observed_at": observed,
                "expires_at": plan["expires_at"],
                "observation_ids": [observation_id],
            },
            {
                "id": inference_id,
                "kind": "inference",
                "summary": (
                    f"{plan['hypothesis']['text']} Counterevidence: {counter}"
                ),
                "source": "foreshadow.growth-plan",
                "observed_at": None,
                "expires_at": plan["expires_at"],
                "observation_ids": [observation_id],
            },
        ],
        "constraints": [
            experiment["guardrail"],
            "Do not add badges, GIFs, Discord links, translations, or benchmarks as part of this task.",
            "Do not solicit stars or open unsolicited issues.",
            "Forbidden: push, publish, deploy, credentials, external-write.",
        ],
        "validation": [
            {
                "argv": (
                    ["git", "grep", "-n", "-F", "-e", "refs/tags/v0.7.7.tar.gz", "--", "Formula/wheretoken.rb"]
                    if detail and "v0.7.7" in detail and "v0.7.6" in detail
                    else ["git", "grep", "-n", "-e", "primary install", "--", "README.md"]
                ),
                "expectation": experiment["success_criterion"],
                "timeout_seconds": 60,
            }
        ],
        "actions": {
            "allowed": ["read", "edit", "commit"],
            "forbidden": ["credentials", "deploy", "external-write", "publish", "push"],
        },
        "references": [record["source_url"]],
        "created_at": _iso(now),
        "provenance": {
            "opportunity_id": experiment["id"],
            "decision_at": _iso(now),
            "evidence_ids": [inference_id, observation_id],
        },
    }
    # Evidence ids in provenance must match the set, independent of order.
    order["provenance"]["evidence_ids"] = ["inf-install-hypothesis", "obs-install-conflict"]
    pending = dumps(order)
    order["task_id"] = "wo-" + hashlib.sha256(pending.encode()).hexdigest()[:24]
    return validate(order)
