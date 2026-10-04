"""Rank owned repositories. This is not an Opportunity score."""

from __future__ import annotations


def _score(repo: dict) -> int:
    score = 0
    if repo.get("install_paths_conflict") is True:
        score += 3
    if repo.get("one_command_install") is True:
        score += 1
    if repo.get("demo_present") is True:
        score += 1
    if repo.get("description_states_job") is False:
        score += 2
    if repo.get("topics_present") is False:
        score += 1
    return score


def rank_portfolio(repos: list[dict]) -> list[dict]:
    ranked = []
    for repo in repos:
        if repo.get("role") not in {None, "owned"} and repo.get("role") != "owned":
            continue
        if repo.get("release_blocked") is True:
            ranked.append(
                {
                    "identity": repo["identity"],
                    "eligible": False,
                    "reason": "release-blocked",
                    "score": None,
                }
            )
            continue
        ranked.append(
            {
                "identity": repo["identity"],
                "eligible": True,
                "reason": "eligible",
                "score": _score(repo),
            }
        )
    return sorted(
        ranked,
        key=lambda item: (not item["eligible"], -(item["score"] or 0), item["identity"]),
    )
