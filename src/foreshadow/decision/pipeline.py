"""Validate, rank, select and export; collection/storage live in adapters."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime

from foreshadow.decision.models import (
    EvidenceKind,
    Observation,
    Opportunity,
    ValidatedOpportunity,
)
from foreshadow.work_order import REQUIRED_DENIALS, dumps, validate


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("decision timestamps must be timezone aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_opportunity(
    opportunity: Opportunity, observations: tuple[Observation, ...], *, now: datetime
) -> ValidatedOpportunity:
    _iso(now)
    if (
        not math.isfinite(opportunity.confidence)
        or not 0.5 <= opportunity.confidence <= 1
        or not opportunity.objective.strip()
        or not opportunity.validation
        or not opportunity.task.acceptance_criteria
        or not opportunity.task.expected_behavior.strip()
    ):
        raise ValueError(
            "opportunity is not actionable: objective, acceptance, checks and adequate confidence required"
        )
    if opportunity.task.repository != opportunity.repository.identity:
        raise ValueError("task repository does not match opportunity")
    by_id = {obs.id: obs for obs in observations}
    if len(by_id) != len(observations):
        raise ValueError("duplicate observation identity")
    for obs in observations:
        _iso(obs.observed_at)
        if (
            obs.observed_at > now
            or obs.repository_identity != opportunity.repository.identity
        ):
            raise ValueError("future or wrong-repository observation")
    for evidence in opportunity.evidence:
        if evidence.expires_at <= now:
            raise ValueError("stale evidence cannot produce an executable task")
        if not evidence.observation_ids or not set(evidence.observation_ids) <= set(
            by_id
        ):
            raise ValueError("missing observation provenance")
        if evidence.kind == EvidenceKind.OBSERVATION:
            obs = by_id.get(evidence.id)
            if (
                obs is None
                or evidence.observed_at != obs.observed_at
                or evidence.source != obs.source
                or evidence.summary != obs.summary
            ):
                raise ValueError("evidence does not match its actual observation")
        elif evidence.observed_at is not None:
            raise ValueError("inference must not claim an observation timestamp")
    result = ValidatedOpportunity(opportunity, now, observations)
    validate(_manifest(result))
    return result


def rank_opportunities(items: list[ValidatedOpportunity]) -> list[ValidatedOpportunity]:
    # Confidence is an inference, used for ordering rather than exported as fact.
    return sorted(
        items, key=lambda item: (-item.opportunity.confidence, item.opportunity.id)
    )


def select_opportunities(
    items: list[ValidatedOpportunity], *, limit: int = 1
) -> list[ValidatedOpportunity]:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    return rank_opportunities(items)[:limit]


def _manifest(item: ValidatedOpportunity) -> dict:
    opportunity = item.opportunity
    evidence = [
        {
            "id": e.id,
            "kind": e.kind.value,
            "summary": e.summary,
            "source": e.source,
            "observed_at": _iso(e.observed_at) if e.observed_at else None,
            "expires_at": _iso(e.expires_at),
            "observation_ids": list(e.observation_ids),
        }
        for e in sorted(opportunity.evidence, key=lambda e: e.id)
    ]
    repository = opportunity.repository
    manifest = {
        "schema": "engineering.work-order",
        "version": 1,
        "task_id": "pending",
        "origin": {"name": "foreshadow", "reference": opportunity.id},
        "repository": {
            "identity": repository.identity,
            "path": repository.path,
            "url": repository.url,
            "base_revision": repository.base_revision,
        },
        "title": opportunity.title,
        "objective": opportunity.objective,
        "rationale": opportunity.rationale,
        "evidence": evidence,
        "constraints": list(opportunity.task.constraints),
        "validation": [
            {
                "argv": list(v.argv),
                "expectation": v.expectation,
                "timeout_seconds": v.timeout_seconds,
            }
            for v in opportunity.validation
        ],
        "actions": {
            "allowed": ["read", "edit", "commit"],
            "forbidden": sorted(REQUIRED_DENIALS),
        },
        "references": [opportunity.task.issue_url]
        if opportunity.task.issue_url
        else [],
        "created_at": _iso(item.validated_at),
        "provenance": {
            "opportunity_id": opportunity.id,
            "decision_at": _iso(item.validated_at),
            "evidence_ids": [e["id"] for e in evidence],
        },
    }
    # Bind task identity to all semantic content, including the pinned revision.
    manifest["task_id"] = (
        "wo-" + hashlib.sha256(dumps(manifest).encode()).hexdigest()[:24]
    )
    return manifest


def export_work_order(item: ValidatedOpportunity, *, now: datetime) -> dict:
    if not isinstance(item, ValidatedOpportunity):
        raise ValueError("only a validated opportunity can be exported")  # noqa: TRY004 — domain rejection
    # Export can occur after validation; recheck actual evidence freshness.
    validate_opportunity(item.opportunity, item.observations, now=now)
    return validate(_manifest(item))
