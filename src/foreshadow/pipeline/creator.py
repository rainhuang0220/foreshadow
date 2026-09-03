"""Creator / org prior. No followers, no sum-of-stars celebrity boost."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.features import clip01

EPS = 1e-6


@dataclass
class CreatorPrior:
    score: float | None
    confidence: str
    why: str
    na: bool
    owner_type: str | None = None
    owner_login: str | None = None
    repo_n: int | None = None
    success_n: int | None = None
    abandoned_n: int | None = None
    recent_push_n: int | None = None
    release_n: int | None = None
    longest_maintained_days: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)


def geomean(values: list[float | None]) -> float | None:
    known = [max(float(v), EPS) for v in values if v is not None]
    if not known:
        return None
    return math.exp(sum(math.log(v) for v in known) / len(known))


def compute_creator_stats(
    owner: Mapping[str, Any],
    current_nwo: str | None = None,
    now: datetime | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    prior = compute_creator_prior(owner, current_full_name=current_nwo or "", now=now)
    return {
        "owner_type": prior.owner_type,
        "owner_login": prior.owner_login,
        "creator_repo_n": prior.repo_n,
        "creator_success_n": prior.success_n,
        "creator_abandoned_n": prior.abandoned_n,
        "creator_longest_maintained_days": prior.longest_maintained_days,
        "creator_recent_push_n": prior.recent_push_n,
        "creator_release_n": prior.release_n,
        "login": prior.owner_login,
        "past_public_repos": prior.repo_n,
        "successful_repos": prior.success_n,
        "longest_maintained_days": prior.longest_maintained_days,
    }


def creator_stats(
    owner: Mapping[str, Any],
    current_nwo: str | None = None,
    now: datetime | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return compute_creator_stats(owner, current_nwo=current_nwo, now=now, **kwargs)


def from_owner(
    owner: Mapping[str, Any],
    current_nwo: str | None = None,
    now: datetime | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return compute_creator_stats(owner, current_nwo=current_nwo, now=now, **kwargs)


def compute_creator_prior(
    owner_payload: Mapping[str, Any] | None,
    *,
    current_full_name: str = "",
    now: datetime | None = None,
    feat: FeaturesBlob | Mapping[str, Any] | None = None,
) -> CreatorPrior:
    now = now or datetime.now(UTC)
    if isinstance(owner_payload, Mapping) and owner_payload:
        return _from_owner(owner_payload, current_full_name, now)
    if feat is not None:
        return _from_feat(feat)
    return _na("no owner history")


def _from_owner(owner: Mapping[str, Any], current: str, now: datetime) -> CreatorPrior:
    typename = owner.get("__typename")
    owner_type = typename if typename in {"User", "Organization"} else None
    login = str(owner["login"]) if owner.get("login") else None
    repos = (
        owner.get("repositories")
        if isinstance(owner.get("repositories"), Mapping)
        else {}
    )
    nodes = repos.get("nodes") if isinstance(repos, Mapping) else None
    if not isinstance(nodes, list):
        return _na("no owner repositories", owner_type=owner_type, login=login)
    sample: list[Mapping[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        nwo = str(node.get("nameWithOwner") or "")
        if current and nwo == current:
            continue
        if node.get("isFork"):
            continue
        sample.append(node)
    return _score_sample(
        sample, now, owner_type=owner_type, login=login, total=repos.get("totalCount")
    )


def _from_feat(feat: FeaturesBlob | Mapping[str, Any]) -> CreatorPrior:
    get = (
        feat.get if isinstance(feat, Mapping) else lambda k, d=None: getattr(feat, k, d)
    )
    n = _int(get("creator_repo_n"))
    success = _int(get("creator_success_n")) or 0
    abandoned = _int(get("creator_abandoned_n")) or 0
    recent = _int(get("creator_recent_push_n")) or 0
    released = _int(get("creator_release_n")) or 0
    longest = _int(get("creator_longest_maintained_days"))
    owner_type = get("owner_type")
    login = get("owner_login")
    if n is None or n < 3:
        return _na(
            "fewer than 3 past repos",
            owner_type=str(owner_type) if owner_type else None,
            login=str(login) if login else None,
            repo_n=n,
            success_n=success,
            abandoned_n=abandoned,
        )
    return _from_counts(
        n=n,
        success=success,
        abandoned=abandoned,
        recent=recent,
        released=released,
        longest=longest,
        owner_type=str(owner_type) if owner_type else None,
        login=str(login) if login else None,
    )


def _score_sample(
    sample: list[Mapping[str, Any]],
    now: datetime,
    *,
    owner_type: str | None,
    login: str | None,
    total: Any,
) -> CreatorPrior:
    success = 0
    abandoned = 0
    recent = 0
    released = 0
    longest: int | None = None
    today = now.date()
    for node in sample:
        created = parse_dt(node.get("createdAt"))
        pushed = parse_dt(node.get("pushedAt"))
        age = None if created is None else (today - created.date()).days
        pushed_age = None if pushed is None else (today - pushed.date()).days
        rel = node.get("releases")
        try:
            n_rel = int(rel.get("totalCount") or 0) if isinstance(rel, Mapping) else 0
        except (TypeError, ValueError):
            n_rel = 0
        archived = bool(node.get("isArchived"))
        if n_rel >= 1:
            released += 1
        if pushed_age is not None and pushed_age <= 180:
            recent += 1
        if created is not None and pushed is not None:
            span = (pushed.date() - created.date()).days
            if span >= 0 and (longest is None or span > longest):
                longest = span
        if age is None or age < 180:
            continue
        living = (pushed_age is not None and pushed_age <= 90) or n_rel >= 1
        if living and not archived:
            success += 1
        elif pushed_age is not None and pushed_age > 365:
            abandoned += 1
    n = len(sample)
    return _from_counts(
        n=n,
        success=success,
        abandoned=abandoned,
        recent=recent,
        released=released,
        longest=longest,
        owner_type=owner_type,
        login=login,
        total=_int(total),
    )


def _from_counts(
    *,
    n: int,
    success: int,
    abandoned: int,
    recent: int,
    released: int,
    longest: int | None,
    owner_type: str | None,
    login: str | None,
    total: int | None = None,
) -> CreatorPrior:
    stats = {
        "login": login,
        "owner_type": owner_type,
        "past_public_repos": n,
        "successful_repos": success,
        "abandoned_repos": abandoned,
        "longest_maintained_days": longest,
        "recent_push_n": recent,
        "release_n": released,
        "total_public": total,
    }
    if n < 3:
        return CreatorPrior(
            score=None,
            confidence="low",
            why=f"UNKNOWN (past repos={n} < 3); not 0",
            na=True,
            owner_type=owner_type,
            owner_login=login,
            repo_n=n,
            success_n=success,
            abandoned_n=abandoned,
            recent_push_n=recent,
            release_n=released,
            longest_maintained_days=longest,
            stats=stats,
        )
    denom = success + abandoned
    if denom < 2:
        return CreatorPrior(
            score=None,
            confidence="low",
            why="UNKNOWN (fewer than 2 classifiable past repos); not 0",
            na=True,
            owner_type=owner_type,
            owner_login=login,
            repo_n=n,
            success_n=success,
            abandoned_n=abandoned,
            recent_push_n=recent,
            release_n=released,
            longest_maintained_days=longest,
            stats=stats,
        )
    success_rate = success / denom
    continuity = recent / max(n, 1)
    breadth = clip01(n / 8.0)
    gm = geomean([success_rate, continuity, breadth])
    score = None if gm is None else round(100.0 * gm, 4)
    conf = "high" if n >= 8 else "medium"
    return CreatorPrior(
        score=score,
        confidence=conf,
        why="maintenance continuity prior; stars not summed",
        na=score is None,
        owner_type=owner_type,
        owner_login=login,
        repo_n=n,
        success_n=success,
        abandoned_n=abandoned,
        recent_push_n=recent,
        release_n=released,
        longest_maintained_days=longest,
        stats=stats,
    )


def _na(
    why: str,
    *,
    owner_type: str | None = None,
    login: str | None = None,
    repo_n: int | None = None,
    success_n: int | None = None,
    abandoned_n: int | None = None,
) -> CreatorPrior:
    return CreatorPrior(
        score=None,
        confidence="low",
        why=why,
        na=True,
        owner_type=owner_type,
        owner_login=login,
        repo_n=repo_n,
        success_n=success_n,
        abandoned_n=abandoned_n,
        stats={
            "login": login,
            "past_public_repos": repo_n,
            "successful_repos": success_n,
        },
    )


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
