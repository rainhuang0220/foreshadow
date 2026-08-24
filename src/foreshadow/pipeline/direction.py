from __future__ import annotations

import importlib.resources
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from foreshadow.pipeline.features import clip01

STUFFING_LEXICON = frozenset(
    {"ai", "llm", "agent", "gpt", "rag", "awesome", "best", "ultimate"}
)


@dataclass(frozen=True)
class DirectionBag:
    name: str
    topics: tuple[str, ...]
    keywords: tuple[str, ...]
    languages: tuple[str, ...]


def load_direction_bags() -> list[DirectionBag]:
    raw = tomllib.loads(
        importlib.resources.files("foreshadow")
        .joinpath("directions.toml")
        .read_text(encoding="utf-8")
    )
    bags: list[DirectionBag] = []
    for name, body in raw.items():
        body = body or {}
        bags.append(
            DirectionBag(
                name=name,
                topics=tuple(body.get("topics") or []),
                keywords=tuple(body.get("keywords") or []),
                languages=tuple(body.get("languages") or []),
            )
        )
    return bags


def stuffing_tokens(description: str) -> set[str]:
    folded = (description or "").lower().replace("-", " ").replace("_", " ")
    return set(folded.split()) & STUFFING_LEXICON


def is_keyword_stuffing(description: str) -> bool:
    return len(stuffing_tokens(description)) >= 4


def score_direction(
    name: str,
    description: str,
    topics: Sequence[str] | None,
    headings: Sequence[str] | None,
    language: str | None,
    bags: Sequence[DirectionBag] | Mapping[str, Mapping],
) -> int:
    parsed = _as_bags(bags)
    if not parsed:
        return 0
    topic_list = [t for t in (topics or []) if t]
    heading_list = [h for h in (headings or []) if h]
    text = " ".join(
        [
            name or "",
            description or "",
            " ".join(topic_list),
            " ".join(heading_list),
            language or "",
        ]
    ).lower()
    best = 0.0
    for bag in parsed:
        raw = (
            0.40 * _jaccard(topic_list, bag.topics)
            + 0.35
            * max(_needle_rate(text, bag.keywords), _needle_rate(text, bag.topics))
            + 0.15 * _lang_bonus(language, bag.languages)
            + 0.10 * _heading_rate(heading_list, bag)
        )
        best = max(best, raw)
    return round(100 * clip01(best))


def _as_bags(
    bags: Sequence[DirectionBag] | Mapping[str, Mapping],
) -> list[DirectionBag]:
    if isinstance(bags, Mapping):
        out: list[DirectionBag] = []
        for name, body in bags.items():
            if not isinstance(body, Mapping):
                return []
            out.append(
                DirectionBag(
                    name=str(name),
                    topics=tuple(body.get("topics") or []),
                    keywords=tuple(body.get("keywords") or []),
                    languages=tuple(body.get("languages") or []),
                )
            )
        return out
    return list(bags)


def _jaccard(repo_topics: Sequence[str], bag_topics: Sequence[str]) -> float:
    a = {t.lower() for t in repo_topics if t}
    b = {t.lower() for t in bag_topics if t}
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _needle_rate(text: str, needles: Sequence[str]) -> float:
    xs = [n.lower() for n in needles if n]
    if not xs:
        return 0.0
    hits = sum(1 for n in xs if n in text)
    return min(hits / len(xs), 1.0)


def _lang_bonus(language: str | None, bag_langs: Sequence[str]) -> float:
    if not language or not bag_langs:
        return 0.0
    want = language.lower()
    return 1.0 if any(want == item.lower() for item in bag_langs) else 0.0


def _heading_rate(headings: Sequence[str], bag: DirectionBag) -> float:
    if not headings:
        return 0.0
    needles = [x.lower() for x in (*bag.topics, *bag.keywords) if x]
    if not needles:
        return 0.0
    hits = 0
    for heading in headings:
        low = heading.lower()
        if any(n in low for n in needles):
            hits += 1
    return clip01(hits / 3)
