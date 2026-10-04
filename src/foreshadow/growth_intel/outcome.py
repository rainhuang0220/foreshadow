"""Treatment checks and outcome windows. A file pass is not a result."""

from __future__ import annotations

from datetime import date, datetime


def mark_implementation(experiment: dict, *, passed: bool) -> dict:
    """Record whether the requested change landed. This is not an outcome."""
    if experiment.get("kind") != "treatment":
        raise ValueError("only a treatment has an implementation check")
    out = dict(experiment)
    if passed:
        out["state"] = "READY_FOR_OBSERVATION"
        out["implementation"] = "PASS"
    else:
        out["state"] = "ABANDONED"
        out["implementation"] = "FAIL"
    if out.get("evidence_strength") == "EXPERIMENT_RESULT":
        raise ValueError("implementation check is not an experiment result")
    out["evidence_strength"] = "HYPOTHESIS"
    return out


def _day(value: str) -> date:
    if "T" in value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("observation time needs a timezone")
        return parsed.date()
    return date.fromisoformat(value)


def _stamp(value: str, *, as_of: datetime) -> date:
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a timezone")
    day = _day(value)
    if day > as_of.date():
        raise ValueError("future observation")
    return day


def elapsed_days(points: list[dict], *, as_of: datetime) -> int | None:
    """Calendar distance between the first and last dated point. Not a sample count."""
    days = sorted(_stamp(str(item["observed_on"]), as_of=as_of) for item in points)
    if len(days) < 2:
        return None
    return (days[-1] - days[0]).days


def measure_outcome(
    *,
    baseline: list[dict],
    post: list[dict],
    intervention_on: str,
    as_of: datetime,
) -> dict:
    """Compare stored pre/post observations. Missing stays missing."""
    cut = _stamp(intervention_on, as_of=as_of)
    base_days = [_stamp(str(item["observed_on"]), as_of=as_of) for item in baseline]
    post_days = [_stamp(str(item["observed_on"]), as_of=as_of) for item in post]
    if any(day >= cut for day in base_days) or any(day < cut for day in post_days):
        raise ValueError("baseline and post windows must sit on opposite sides of the intervention")
    raw_base = [dict(item) for item in baseline]
    raw_post = [dict(item) for item in post]
    if not raw_base:
        return {
            "state": "INSUFFICIENT_BASELINE",
            "evidence_strength": "UNKNOWN",
            "interpretation": "UNKNOWN",
            "causal": False,
            "elapsed_days": None,
            "baseline_observations": raw_base,
            "post_observations": raw_post,
            "text": "No pre-intervention observation is stored. This is not a causal claim.",
        }
    span = elapsed_days(raw_post, as_of=as_of) if len(raw_post) >= 2 else None
    if span is None or span <= 0:
        return {
            "state": "INSUFFICIENT_BASELINE",
            "evidence_strength": "UNKNOWN",
            "interpretation": "UNKNOWN",
            "causal": False,
            "elapsed_days": span,
            "baseline_observations": raw_base,
            "post_observations": raw_post,
            "text": "The post window has no elapsed calendar span. This is not a causal claim.",
        }
    ordered_base = sorted(raw_base, key=lambda item: _stamp(str(item["observed_on"]), as_of=as_of))
    ordered_post = sorted(raw_post, key=lambda item: _stamp(str(item["observed_on"]), as_of=as_of))
    before = ordered_base[-1].get("unique_visitors")
    after = ordered_post[-1].get("unique_visitors")
    if type(before) is not int or type(after) is not int:
        interpretation = "UNKNOWN"
    elif before == after:
        interpretation = "NO_CLEAR_CHANGE"
    else:
        interpretation = "OBSERVED_CHANGE"
    return {
        "state": "MEASURED",
        "evidence_strength": "OBSERVED",
        "interpretation": interpretation,
        "causal": False,
        "elapsed_days": span,
        "baseline_observations": raw_base,
        "post_observations": raw_post,
        "text": (
            "The pre and post counts are stored observations. "
            "This is not a causal claim."
        ),
    }
