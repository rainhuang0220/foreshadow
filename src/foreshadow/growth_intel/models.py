"""Epistemic status. Correlation is never given a causal token."""

from __future__ import annotations

import json
from enum import StrEnum


class EpistemicStatus(StrEnum):
    OBSERVED = "OBSERVED"
    CORRELATED = "CORRELATED"
    HYPOTHESIS = "HYPOTHESIS"
    QUASI_EXPERIMENTAL = "QUASI_EXPERIMENTAL"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    UNKNOWN = "UNKNOWN"


def parse_status(value: str) -> EpistemicStatus:
    if value.upper() == "CAUSAL":
        raise ValueError("correlation is not a causal claim")
    try:
        return EpistemicStatus(value)
    except ValueError as exc:
        raise ValueError(f"unknown epistemic status: {value}") from exc


def dump_claim(claim: dict) -> dict:
    status = parse_status(claim["status"])
    if status is EpistemicStatus.CORRELATED and "not a causal claim" not in claim["text"]:
        raise ValueError("a correlated claim must say it is not a causal claim")
    out = {
        "id": claim["id"],
        "observation_ids": list(claim["observation_ids"]),
        "status": status.value,
        "text": claim["text"],
    }
    if "about" in claim:
        out["about"] = claim["about"]
    encoded = json.dumps(out)
    if "CAUSAL" in encoded:
        raise ValueError("correlation is not a causal claim")
    return out
