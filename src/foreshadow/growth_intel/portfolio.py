"""Rank owned repositories. This is not an Opportunity score."""

from __future__ import annotations


def _priority(repo: dict) -> int:
    """Actionable friction. Not a growth probability and not an entry value."""
    priority = 0
    if repo.get("install_paths_conflict") is True:
        priority += 3
    if repo.get("one_command_install") is True:
        priority += 1
    if repo.get("demo_present") is True:
        priority += 1
    if repo.get("description_states_job") is False:
        priority += 2
    if repo.get("topics_present") is False:
        priority += 1
    return priority


def rank_portfolio(repos: list[dict]) -> list[dict]:
    ranked = []
    for repo in repos:
        if repo.get("role") not in {None, "owned"}:
            continue
        if repo.get("release_blocked") is True:
            ranked.append(
                {
                    "identity": repo["identity"],
                    "eligible": False,
                    "reason": "release-blocked",
                    "intervention_priority": None,
                    "priority_meaning": "actionable-friction",
                }
            )
            continue
        ranked.append(
            {
                "identity": repo["identity"],
                "eligible": True,
                "reason": "eligible",
                "intervention_priority": _priority(repo),
                "priority_meaning": "actionable-friction",
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            not item["eligible"],
            -(item["intervention_priority"] or 0),
            item["identity"],
        ),
    )
