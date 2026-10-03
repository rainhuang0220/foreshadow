"""Immutable decision concepts; observations, inferences and tasks stay distinct."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from foreshadow.decision.task import StructuredTask


class EvidenceKind(StrEnum):
    OBSERVATION = "observation"
    INFERENCE = "inference"


@dataclass(frozen=True)
class Repository:
    identity: str
    path: str | None = None
    url: str | None = None
    base_revision: str | None = None


@dataclass(frozen=True)
class Observation:
    id: str
    repository_identity: str
    observed_at: datetime
    source: str
    summary: str


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: EvidenceKind
    summary: str
    source: str
    observed_at: datetime | None
    expires_at: datetime
    observation_ids: tuple[str, ...]

    @classmethod
    def observed(cls, observation: Observation, *, expires_at: datetime) -> Evidence:
        return cls(
            observation.id,
            EvidenceKind.OBSERVATION,
            observation.summary,
            observation.source,
            observation.observed_at,
            expires_at,
            (observation.id,),
        )

    @classmethod
    def inferred(
        cls,
        *,
        id: str,
        summary: str,
        source: str,
        observations: tuple[Observation, ...],
        expires_at: datetime,
    ) -> Evidence:
        return cls(
            id,
            EvidenceKind.INFERENCE,
            summary,
            source,
            None,
            expires_at,
            tuple(sorted(obs.id for obs in observations)),
        )


@dataclass(frozen=True)
class Validation:
    argv: tuple[str, ...]
    expectation: str
    timeout_seconds: int = 300


@dataclass(frozen=True)
class Opportunity:
    id: str
    repository: Repository
    title: str
    objective: str
    rationale: str
    task: StructuredTask
    evidence: tuple[Evidence, ...]
    confidence: float
    validation: tuple[Validation, ...]


@dataclass(frozen=True)
class ValidatedOpportunity:
    opportunity: Opportunity
    validated_at: datetime
    observations: tuple[Observation, ...]
