"""Why a pattern might and might not move to an owned repository.

A low-brand source and an editable file do not produce a transfer band.
"""

from __future__ import annotations

from datetime import datetime


def _age_days(row: dict, as_of: datetime | None) -> int | None:
    if as_of is None or as_of.tzinfo is None:
        return None
    raw = row.get("created_at")
    if not raw:
        return None
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return None
    return (as_of.date() - parsed.date()).days


def _age_compatibility(sources: list[dict], target: dict, as_of: datetime | None) -> str:
    """Young targets are not treated as age-matched to old sources.

    This slice never emits ``comparable``. Missing ages stay unknown.
    """
    target_age = _age_days(target, as_of)
    source_ages = [
        age for age in (_age_days(item, as_of) for item in sources) if age is not None
    ]
    if target_age is None or not source_ages:
        return "unknown"
    if target_age < 180 and (any(age > 730 for age in source_ages) or min(source_ages) > 365):
        return "not_comparable"
    return "unknown"


def _archetype(sources: list[dict], target: dict) -> str:
    target_name = target.get("archetype")
    names = {item.get("archetype") for item in sources}
    if not target_name or not names or None in names:
        return "unknown"
    if names == {target_name}:
        return "same"
    return "mixed"


def _mechanism(target: dict) -> str:
    found = target.get("surface_discrepancy")
    if isinstance(found, dict) and found.get("affected_surfaces"):
        return "file_edit"
    return "unknown"


def transfer_for(
    *,
    sources: list[dict],
    target: dict,
    as_of: datetime | None = None,
    measurement: str = "unknown",
) -> dict:
    brands = {item.get("brand_advantage") for item in sources}
    measurement_quality = measurement if measurement in {"adequate", "unknown", "inadequate"} else "unknown"
    if not sources or brands <= {"high", "unknown"} or brands.isdisjoint({"low", "medium"}):
        return {
            "band": "unknown",
            "status": "UNKNOWN",
            "assessment": {
                "archetype": "unknown",
                "maintainer_class": "unknown",
                "brand_advantage": "blocked",
                "age_compatibility": "unknown",
                "distribution_context": "unknown",
                "mechanism_reproducibility": "unknown",
                "measurement_quality": "unknown",
            },
            "why_might": "No low-brand source is available for this target.",
            "why_might_not": (
                "Brand advantage dominates the supporting cases, so the pattern "
                "is not treated as a transferable tactic."
            ),
        }
    age = _age_compatibility(sources, target, as_of)
    archetype = _archetype(sources, target)
    mechanism = _mechanism(target)
    assessment = {
        "archetype": archetype,
        "maintainer_class": {
            "target": target.get("maintainer_class"),
            "sources": sorted({item.get("maintainer_class") for item in sources}),
        },
        "brand_advantage": "low_or_medium_present",
        "age_compatibility": age,
        "distribution_context": "unknown",
        "mechanism_reproducibility": mechanism,
        "measurement_quality": measurement_quality,
    }
    # Age is never marked comparable here, so the band stays unknown.
    return {
        "band": "unknown",
        "status": "UNKNOWN",
        "assessment": assessment,
        "why_might": "A maintainer may be able to edit a file. That is not a transfer band.",
        "why_might_not": (
            "An editable file and a low-brand source are not a measured transfer. "
            f"Age compatibility is {age}. Archetype is {archetype}. "
            f"Measurement quality is {measurement_quality}. Distribution context is unknown. "
            "The assessment is not an effect size."
        ),
    }
