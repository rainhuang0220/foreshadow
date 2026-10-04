"""Bounded experiment plans. A file check is not an adoption result."""

from __future__ import annotations

from datetime import datetime, timedelta

from foreshadow.growth_intel.casebook import load_casebook
from foreshadow.growth_intel.portfolio import rank_portfolio
from foreshadow.growth_intel.study import build_study
from foreshadow.growth_intel.transfer import transfer_for

# Product policy for rejecting star-primary success. Not a power calculation.
POLICY_STAR_FLOOR = 30
_REQUIRED = (
    "id",
    "baseline",
    "success_criterion",
    "failure_criterion",
    "guardrail",
)


def validate_experiment(experiment: dict) -> dict:
    missing = [key for key in _REQUIRED if not experiment.get(key)]
    if missing:
        raise ValueError(f"{missing[0]} is required")
    metric = (
        experiment.get("implementation_metric")
        or experiment.get("primary_metric")
        or experiment.get("outcome_metric")
    )
    if not metric:
        raise ValueError("implementation_metric is required")
    treatment = experiment.get("kind") == "treatment" or bool(
        experiment.get("implementation_metric")
    )
    if treatment:
        if experiment.get("window_days"):
            raise ValueError("treatment check is not an outcome window")
    else:
        window = experiment.get("window_days")
        if type(window) is not int or window <= 0:
            raise ValueError("window_days must be a positive integer of calendar days")
        if experiment.get("primary_metric") == "stars" or experiment.get("outcome_metric") == "stars":
            try:
                baseline = int(experiment["baseline"])
            except (TypeError, ValueError) as exc:
                raise ValueError("star baseline must be an integer") from exc
            if baseline < POLICY_STAR_FLOOR:
                raise ValueError(
                    f"star success is below the policy floor of {POLICY_STAR_FLOOR}"
                )
    return experiment


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps need a timezone")
    return value.astimezone(tz=value.tzinfo).isoformat().replace("+00:00", "Z")


def _discrepancy(target: dict) -> dict | None:
    if target.get("install_paths_conflict") is not True:
        return None
    found = target.get("surface_discrepancy")
    if not isinstance(found, dict):
        return None
    observed = found.get("observed")
    expected = found.get("expected")
    surfaces = found.get("affected_surfaces")
    if not isinstance(observed, str) or not observed:
        return None
    if not isinstance(expected, str) or not expected:
        return None
    if not isinstance(surfaces, list) or not all(isinstance(item, str) and item for item in surfaces):
        return None
    return found


def _treatment(target: dict) -> dict | None:
    found = _discrepancy(target)
    if found is None:
        return None
    named = " and ".join(found["affected_surfaces"])
    observed = found["observed"]
    expected = found["expected"]
    return validate_experiment(
        {
            "id": target.get("treatment_id") or "gx-surface-agreement",
            "kind": "treatment",
            "role": "treatment-integrity",
            "state": "TREATMENT_READY",
            "target": target["identity"],
            "title": "Make the documented install paths name one version",
            "implementation_metric": "install_path_agreement",
            "outcome_metric": None,
            "baseline": "install paths conflict",
            "success_criterion": f"{named} name {expected} rather than {observed}",
            "failure_criterion": (
                f"{named} still name {observed}, or a second primary install command is added"
            ),
            "guardrail": "no release and no star solicitation; stars and clones are not success",
            "evidence_strength": "HYPOTHESIS",
            "exportable": True,
            "effort": "small",
            "reversibility": "revert the documentation commit",
        }
    )


def _growth_experiment(target: dict) -> dict:
    """An adoption question. build_plan does not see stored traffic, so the baseline is empty."""
    return {
        "id": "gx-qualified-traffic-v1",
        "kind": "outcome",
        "target": target["identity"],
        "state": "INSUFFICIENT_BASELINE",
        "outcome_metric": "daily_unique_visitors",
        "secondary_metrics": ["daily_unique_cloners"],
        "secondary_observations": ["stars"],
        "baseline_observations": [],
        "baseline_window": None,
        "intervention_on": None,
        "post_window": None,
        "elapsed_days": None,
        "low_power": True,
        "low_power_reason": "no stored pre-intervention traffic observations",
        "evidence_strength": "UNKNOWN",
        "interpretation": "UNKNOWN",
        "causal": False,
        "exportable": False,
        "reason": "insufficient-baseline",
        "guardrail": "do not post, solicit stars, or message maintainers",
        "text": (
            "No stored pre-intervention traffic observation is available. "
            "The outcome metric is the last daily unique visitor count, not the rolling 14-day unique count. "
            "Daily unique counts are not summed. "
            "Stars are a secondary observation only. This is not a causal claim."
        ),
    }


def build_plan(book: dict, *, as_of: datetime) -> dict:
    loaded = load_casebook(book)
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a timezone")
    study = build_study(loaded, as_of=as_of)
    owned = [row for row in loaded["repositories"] if row["role"] == "owned"]
    ranked = rank_portfolio(owned)
    by_id = {row["identity"]: row for row in owned}
    blocked = [
        {
            "identity": item["identity"],
            "reason": item["reason"],
            "evidence_strength": "UNKNOWN",
        }
        for item in ranked
        if not item["eligible"]
    ]
    winner = next((item for item in ranked if item["eligible"]), None)
    target = by_id[winner["identity"]] if winner else None
    counterevidence = [
        "Current README text is a CURRENT_SNAPSHOT and cannot explain historical star growth.",
        "Several successful CLIs document more than one installer when those installers agree. The claim is about a contradiction, not about deleting every extra installer.",
        "Star success below the policy floor of 30 is rejected. That floor is not a power calculation, and stars are not the success metric.",
        "Platform-owned repositories are excluded from the supporting set.",
    ]
    one_command_controls = sorted(
        row["identity"]
        for row in loaded["repositories"]
        if row.get("role") == "control"
        and row.get("one_command_install") is True
        and row.get("brand_advantage") in {"low", "medium"}
    )
    if one_command_controls:
        named = ", ".join(one_command_controls)
        counterevidence.append(
            "One-command install is already present on "
            f"{named}. Their star stocks are not compared here. "
            "This is not a causal claim."
        )
    sources = [
        row
        for row in loaded["repositories"]
        if row.get("identity") in one_command_controls
    ]
    if target is None:
        transfer = {
            "band": "unknown",
            "status": "UNKNOWN",
            "why_might": "No eligible owned repository.",
            "why_might_not": "There is no target to transfer a mechanism onto.",
        }
    else:
        transfer = transfer_for(
            sources=sources,
            target=target,
            as_of=as_of,
            measurement="unknown",
        )
    experiment = _treatment(target) if target else None
    growth = _growth_experiment(target) if target else None
    backlog = []
    if experiment:
        backlog.append(experiment)
    for item in ranked:
        repo = by_id[item["identity"]]
        if not item["eligible"] or repo.get("description_states_job") is not False:
            continue
        if experiment and experiment["target"] == repo["identity"]:
            continue
        backlog.append(
            validate_experiment(
                {
                    "id": "gx-explicit-header-v1",
                    "kind": "treatment",
                    "role": "treatment-integrity",
                    "state": "TREATMENT_READY",
                    "target": repo["identity"],
                    "title": "State the job in the public repository description",
                    "implementation_metric": "description_states_job",
                    "baseline": "description does not state the job",
                    "success_criterion": (
                        "the GitHub description states the job in the language a stranger reads"
                    ),
                    "failure_criterion": "the description is still poetic or empty",
                    "guardrail": "do not solicit stars",
                    "evidence_strength": "HYPOTHESIS",
                    "exportable": False,
                    "reason": "external-write",
                }
            )
        )
        blocked.append(
            {
                "identity": repo["identity"],
                "reason": "external-write",
                "evidence_strength": "HYPOTHESIS",
            }
        )
    return {
        "schema": "foreshadow.growth-plan",
        "version": 1,
        "as_of": _iso(as_of),
        "expires_at": _iso(as_of + timedelta(days=14)),
        "target_identity": None if target is None else target["identity"],
        "target_record": target,
        "portfolio": ranked,
        "study": study,
        "hypothesis": {
            "status": "HYPOTHESIS" if experiment else "UNKNOWN",
            "text": (
                "Making contradictory install instructions agree may reduce activation friction. This is not a causal claim."
                if experiment
                else "No exportable experiment follows from the evidence. This is not a causal claim."
            ),
            "counterevidence": counterevidence,
        },
        "transferability": transfer,
        "comparable_one_command_controls": one_command_controls,
        "recommended_experiment": experiment,
        "growth_experiment": growth,
        "backlog": backlog,
        "blocked_experiments": blocked,
        "sections": {
            "fact": study["claims"][0]["text"],
            "interpretation": "The casebook is a retrospective selection. Comparative star claims stay UNKNOWN.",
            "hypothesis": "A file check can show that a change landed. It does not establish an adoption result.",
            "experiment": experiment["title"] if experiment else "No experiment.",
        },
    }
