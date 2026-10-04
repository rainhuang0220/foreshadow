"""Why a pattern might and might not move to an owned repository."""

from __future__ import annotations


def transfer_for(*, sources: list[dict], target: dict) -> dict:
    brands = {item.get("brand_advantage") for item in sources}
    if not sources or brands <= {"high", "unknown"} or "low" not in brands and "medium" not in brands:
        return {
            "band": "unknown",
            "status": "UNKNOWN",
            "why_might": "No low-brand source is available for this target.",
            "why_might_not": "Brand advantage dominates the supporting cases, so the pattern is not treated as a transferable tactic.",
        }
    low = [item["identity"] for item in sources if item.get("brand_advantage") == "low"]
    if target.get("maintainer_class") == "solo" and low:
        return {
            "band": "medium",
            "status": "HYPOTHESIS",
            "why_might": "The supporting cases include a low-brand maintainer, and the change is a file the target maintainer can edit.",
            "why_might_not": "A low-brand case still does not show that the same change caused adoption. Audience, age, and launch channel can differ.",
        }
    return {
        "band": "low",
        "status": "HYPOTHESIS",
        "why_might": "Part of the mechanism can be reproduced without a platform account.",
        "why_might_not": "Team size or distribution still differs from the source cases.",
    }
