"""Short extractive project thesis. Competitors stay 信息不足 unless the README says so."""

from __future__ import annotations

from collections.abc import Sequence

MISSING = "信息不足"

_COMPETE_HINTS = (
    "alternative",
    "compared to",
    "vs ",
    "versus",
    "competitor",
    "inspired by",
    "unlike ",
    "similar to",
)


def extract_thesis(
    *,
    description: str | None = None,
    readme: str | None = None,
    headings: Sequence[str] | None = None,
    topics: Sequence[str] | None = None,
    releases_30d: int | None = None,
    age_days: int | None = None,
) -> dict[str, str]:
    desc = (description or "").strip()
    heads = [str(h).strip() for h in (headings or []) if str(h).strip()]
    what = desc or (heads[0] if heads else MISSING)
    why = _sentence_with(
        readme,
        ("why", "motivation", "problem", "解决", "为了"),
    ) or (desc if desc else MISSING)
    users = (
        _sentence_with(
            readme,
            (
                "for developers",
                "for teams",
                "users",
                "面向",
                "who it's for",
                "audience",
            ),
        )
        or MISSING
    )
    diff = (
        _from_headings(heads)
        or _sentence_with(readme, ("different", "unique", "instead of", "unlike"))
        or MISSING
    )
    if age_days is None and releases_30d is None:
        maturity = MISSING
    elif age_days is not None and releases_30d is None:
        maturity = f"约 {int(age_days)} 天"
    else:
        age_bit = f"约 {int(age_days)} 天" if age_days is not None else "年龄未知"
        if releases_30d is not None and releases_30d > 0:
            rel_bit = "近 30 天有 release"
        else:
            rel_bit = "近 30 天无 release"
        maturity = f"{age_bit}，{rel_bit}"
    competitors = _competitors(readme)
    risks = (
        _sentence_with(readme, ("limit", "risk", "not yet", "experimental", "alpha"))
        or MISSING
    )
    topics_s = "、".join(str(t) for t in (topics or [])[:6] if t)
    if what == MISSING and topics_s:
        what = topics_s
    return {
        "what": _short(what),
        "why_it_may_matter": _short(why),
        "target_users": _short(users),
        "technical_differentiation": _short(diff),
        "current_maturity": _short(maturity),
        "main_competitors": _short(competitors),
        "risks": _short(risks),
    }


def _competitors(readme: str | None) -> str:
    if not readme:
        return MISSING
    captured: list[str] = []
    grab = False
    for raw in readme.splitlines():
        line = raw.strip()
        low = line.lower()
        if line.startswith("#") and "alternativ" in low:
            grab = True
            continue
        if grab:
            if line.startswith("#"):
                break
            if not line:
                continue
            captured.append(line.lstrip("-* ").strip())
            continue
        if any(h in low for h in _COMPETE_HINTS):
            return line[:180]
    if captured:
        return "；".join(captured[:6])
    return MISSING


def _from_headings(heads: Sequence[str]) -> str | None:
    skip = {"readme", "installation", "install", "license", "contributing", "changelog"}
    kept = [h for h in heads if h.lower() not in skip]
    if not kept:
        return None
    return "；".join(kept[:4])


def _sentence_with(readme: str | None, needles: Sequence[str]) -> str | None:
    if not readme:
        return None
    for raw in readme.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "[")):
            continue
        low = line.lower()
        if any(n in low for n in needles) and len(line) >= 20:
            return line[:180]
    return None


def _short(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= 180:
        return text or MISSING
    return text[:179].rstrip() + "…"
