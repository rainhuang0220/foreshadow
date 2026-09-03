"""Star-trust damper for Potential. Not a rank axis. Range [0.3, 1.0]."""

from __future__ import annotations

from collections.abc import Sequence

from foreshadow.pipeline.features import clip

_FAKE_FLAGS = frozenset(
    {
        "H1",
        "H7",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "P7",
        "P8",
        "FAKE-GROWTH",
        "FAKE_GROWTH",
        "FAKEGROWTH",
        "P8_SPIKE_NO_COMMITTERS",
    }
)


def star_trust(
    stars: int | None,
    forks: int | None = None,
    open_issues: int | None = None,
    contributors: int | None = None,
    v7: float | None = None,
    v30: float | None = None,
    h_flags: Sequence[str] | None = None,
) -> float:
    trust = 1.0
    flags = {str(f).strip().upper().replace(" ", "-") for f in (h_flags or [])}
    if flags & _FAKE_FLAGS or any("FAKE" in f and "GROWTH" in f for f in flags):
        trust *= 0.45
    if stars is not None and stars >= 80:
        denom = (forks or 0) + (open_issues or 0) + (contributors or 0)
        if denom <= 0:
            trust *= 0.4
        else:
            ratio = stars / max(denom, 1)
            if ratio >= 80:
                trust *= 0.4
            elif ratio >= 40:
                trust *= 0.55
            elif ratio >= 20:
                trust *= 0.75
    if v7 is not None and v30 is not None and v30 > 0 and v7 / v30 >= 6:
        trust *= 0.6
    elif v7 is not None and v30 is not None and v30 <= 0 and v7 >= 15:
        trust *= 0.7
    return clip(trust, 0.3, 1.0)
