"""Load a provenance-preserving casebook. Missing values stay missing."""

from __future__ import annotations

import json
import re
from pathlib import Path

IDENTITY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ROLES = {"breakout", "control", "predecessor", "owned", "context"}
BRANDS = {"low", "medium", "high", "unknown"}
CLASSES = {
    "solo",
    "small_independent_team",
    "startup_or_company",
    "large_incumbent_or_platform",
    "foundation",
}
_DATA = Path(__file__).with_name("data") / "casebook.json"


def packaged_casebook() -> dict:
    return load_casebook(json.loads(_DATA.read_text(encoding="utf-8")))


def load_casebook(book: dict) -> dict:
    if book.get("schema") != "foreshadow.growth-casebook" or book.get("version") != 1:
        raise ValueError("unsupported growth casebook")
    if book.get("selection") != "RETROSPECTIVE_SELECTION":
        raise ValueError("casebook selection must stay retrospective")
    if book.get("epistemic_ceiling") != "HYPOTHESIS":
        raise ValueError("this slice cannot raise the epistemic ceiling")
    if not book.get("observation_time"):
        raise ValueError("provenance requires an observation time")
    seen = set()
    repos = []
    for row in book["repositories"]:
        identity = row.get("identity") or ""
        if not IDENTITY.fullmatch(identity):
            raise ValueError(f"repository identity must be owner/name: {identity!r}")
        if identity in seen:
            raise ValueError(f"duplicate repository identity: {identity}")
        seen.add(identity)
        if not row.get("source_url") or not row.get("observation_time"):
            raise ValueError(f"provenance requires source and observation time for {identity}")
        if row.get("role") not in ROLES:
            raise ValueError(f"unknown role for {identity}")
        if row.get("brand_advantage") not in BRANDS:
            raise ValueError(f"unknown brand advantage for {identity}")
        if row.get("maintainer_class") not in CLASSES:
            raise ValueError(f"unknown maintainer class for {identity}")
        if row["role"] == "control" and not row.get("matched_to"):
            raise ValueError(f"control {identity} needs matched_to")
        stars = row.get("stars")
        if stars is not None and type(stars) is not int:
            raise ValueError(f"stars must be an integer or null for {identity}")
        forks = row.get("forks")
        if forks is not None and type(forks) is not int:
            raise ValueError(f"forks must be an integer or null for {identity}")
        repos.append(row)
    return {**book, "repositories": repos}
