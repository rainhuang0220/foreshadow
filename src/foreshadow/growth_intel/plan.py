"""Bounded experiment plans. Stars are not the decision function."""

from __future__ import annotations

from datetime import datetime, timedelta

from foreshadow.growth_intel.casebook import load_casebook
from foreshadow.growth_intel.portfolio import rank_portfolio
from foreshadow.growth_intel.study import build_study
from foreshadow.growth_intel.transfer import transfer_for

STAR_FLOOR = 30
_REQUIRED = (
    "id",
    "primary_metric",
    "baseline",
    "window_days",
    "success_criterion",
    "failure_criterion",
    "guardrail",
)


def validate_experiment(experiment: dict) -> dict:
    missing = [key for key in _REQUIRED if not experiment.get(key)]
    if missing:
        raise ValueError(f"{missing[0]} is required")
    if type(experiment["window_days"]) is not int or experiment["window_days"] <= 0:
        raise ValueError("window_days must be a positive integer of calendar days")
    if experiment["primary_metric"] == "stars":
        try:
            baseline = int(experiment["baseline"])
        except (TypeError, ValueError) as exc:
            raise ValueError("star baseline must be an integer") from exc
        if baseline < STAR_FLOOR:
            raise ValueError(
                f"star success is underpowered below {STAR_FLOOR} stars"
            )
    return experiment


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps need a timezone")
    return value.astimezone(tz=value.tzinfo).isoformat().replace("+00:00", "Z")


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
        "Star movement is underpowered for a repository with fewer than 30 stars, so stars are not the success metric.",
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
            f"{named}, and those controls are not in the same star regime as their matched breakouts. "
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
        transfer = transfer_for(sources=sources, target=target)
        transfer["why_might_not"] = (
            transfer["why_might_not"]
            + " The band is not an effect size. It does not match on age, and a current README cannot explain historical stars."
        )
    experiment = None
    backlog = []
    if target and target.get("install_paths_conflict") is True:
        pinned = target.get("install_conflict_detail") or ""
        versioned = "v0.7.6" in pinned and "v0.7.7" in pinned
        experiment = validate_experiment(
            {
                "id": "gx-single-install-path-v1",
                "target": target["identity"],
                "title": "Make the documented install paths name one version",
                "primary_metric": "install_path_agreement",
                "baseline": "install paths conflict",
                "window_days": 14,
                "success_criterion": (
                    "README.md and Formula/wheretoken.rb both name v0.7.7, and the formula urls refs/tags/v0.7.7.tar.gz rather than v0.7.6"
                    if versioned
                    else "README and Formula/wheretoken.rb name the same version and one primary install command"
                ),
                "failure_criterion": (
                    "Formula/wheretoken.rb still urls v0.7.6, or the README adds a second primary install command"
                    if versioned
                    else "the files still name different versions, or a second primary command is added"
                ),
                "guardrail": "no release and no star solicitation; stars and clones are not success",
                "evidence_strength": "HYPOTHESIS",
                "exportable": True,
                "effort": "small",
                "reversibility": "revert the documentation commit",
            }
        )
        backlog.append(experiment)
    for item in ranked:
        repo = by_id[item["identity"]]
        if not item["eligible"] or repo.get("description_states_job") is not False:
            continue
        if experiment and experiment["target"] == repo["identity"]:
            continue
        backlog.append(
            {
                "id": "gx-explicit-header-v1",
                "target": repo["identity"],
                "title": "State the job in the public repository description",
                "primary_metric": "description_states_job",
                "baseline": "description does not state the job",
                "window_days": 14,
                "success_criterion": "the GitHub description states the job in the language a stranger reads",
                "failure_criterion": "the description is still poetic or empty",
                "guardrail": "do not solicit stars",
                "evidence_strength": "HYPOTHESIS",
                "exportable": False,
                "reason": "external-write",
            }
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
        "backlog": backlog,
        "blocked_experiments": blocked,
        "sections": {
            "fact": study["claims"][0]["text"],
            "interpretation": "The casebook is a retrospective selection. Comparative star claims stay UNKNOWN.",
            "hypothesis": "A file-level install contradiction is a reversible trial. It does not establish a cause of stars.",
            "experiment": experiment["title"] if experiment else "No experiment.",
        },
    }
