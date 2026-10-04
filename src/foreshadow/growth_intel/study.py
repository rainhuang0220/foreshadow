"""Provenance-preserving study. Current READMEs do not explain past growth."""

from __future__ import annotations

from datetime import datetime

from foreshadow.growth_intel.casebook import load_casebook
from foreshadow.growth_intel.models import dump_claim


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observation time needs a timezone")
    return parsed


def build_study(book: dict, *, as_of: datetime) -> dict:
    loaded = load_casebook(book)
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a timezone")
    for repo in loaded["repositories"]:
        if _time(repo["observation_time"]) > as_of:
            raise ValueError("future observation")
    snapshot = any(repo.get("readme_scope") == "CURRENT_SNAPSHOT" for repo in loaded["repositories"])
    text = (
        "README fields in this study are a CURRENT_SNAPSHOT pinned by blob SHA. "
        "They were not observed before the growth window, so they cannot explain historical stars."
        if snapshot
        else "No README snapshot was attached. Historical README effects are UNKNOWN."
    )
    claim = dump_claim(
        {
            "id": "cl-readme-snapshot",
            "about": "readme",
            "status": "UNKNOWN",
            "text": text,
            "observation_ids": ["casebook"],
        }
    )
    return {
        "selection": loaded["selection"],
        "epistemic_ceiling": loaded["epistemic_ceiling"],
        "claims": [claim],
    }
