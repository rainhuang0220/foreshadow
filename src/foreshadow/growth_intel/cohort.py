"""Deterministic cohorts. Brand and ownership stay visible exclusions."""

from __future__ import annotations

from datetime import datetime

from foreshadow.growth_intel.models import parse_status


def select_cohort(cases: list[dict], *, archetype: str) -> dict:
    members = []
    excluded = []
    for case in sorted(cases, key=lambda item: item["identity"]):
        if case.get("archetype") != archetype:
            excluded.append((case["identity"], "archetype"))
            continue
        if case.get("role") == "owned":
            excluded.append((case["identity"], "owned"))
            continue
        if case.get("role") == "context":
            excluded.append((case["identity"], "context"))
            continue
        if case.get("brand_advantage") in {"high", "unknown"}:
            excluded.append((case["identity"], "brand"))
            continue
        if case.get("stars") is None:
            excluded.append((case["identity"], "missing-stars"))
            continue
        members.append(case["identity"])
    return {"members": members, "excluded": excluded}


def claim_status(
    *,
    requested: str,
    event: dict | None,
    control_window: dict | None,
    readme_scope: str | None,
) -> str:
    """Refuse quasi-experimental evidence unless the window is real."""
    if requested != "QUASI_EXPERIMENTAL":
        return parse_status(requested).value
    occurred = event.get("occurred_at") if event else None
    dated = False
    if event and event.get("source_url") and event.get("type") and isinstance(occurred, str):
        try:
            parsed = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        dated = parsed is not None and parsed.tzinfo is not None
    matched = bool(
        control_window
        and control_window.get("identity")
        and type(control_window.get("elapsed_days")) is int
        and control_window["elapsed_days"] > 0
    )
    if dated and matched and readme_scope != "CURRENT_SNAPSHOT":
        return "QUASI_EXPERIMENTAL"
    return "HYPOTHESIS"
