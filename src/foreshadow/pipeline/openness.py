"""Contributor Openness. Wilson LB of external closed PRs. n_ext < 8 → NA."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from foreshadow.github.rest import is_bot
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.wilson import wilson_lower_bound

EXT_ASSOC = frozenset({"NONE", "CONTRIBUTOR", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"})
MAINT_ASSOC = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
NEWCOMER_ASSOC = frozenset({"FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"})
MIN_CLOSED_EXT = 8
BOT_LOGINS = frozenset({"dependabot", "renovate", "greenkeeper", "github-actions"})


@dataclass
class OpennessResult:
    score: float | None
    confidence: str
    sample_n: int
    closed_ext: int
    merged_ext: int
    newcomer_closed: int
    newcomer_merged: int
    first_response_hours: float | None
    merge_hours: float | None
    ignored_ext_n: int | None
    why: str
    na: bool
    truncated: bool = True
    sample_start: str | None = None
    sample_end: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)


def is_external_author(
    assoc: str | None, login: str | None = None, type_: str | None = None
) -> bool:
    if _bot_login(login, type_):
        return False
    return str(assoc or "") in EXT_ASSOC


def compute_openness_from_prs(
    merged_nodes: Sequence[Mapping[str, Any]] | None,
    closed_unmerged_nodes: Sequence[Mapping[str, Any]] | None,
) -> OpennessResult:
    merged = [n for n in (merged_nodes or []) if isinstance(n, Mapping)]
    closed_u = [n for n in (closed_unmerged_nodes or []) if isinstance(n, Mapping)]
    combined = list(merged) + list(closed_u)
    closed_ext = 0
    merged_ext = 0
    newcomer_closed = 0
    newcomer_merged = 0
    resp_hours: list[float] = []
    merge_hours: list[float] = []
    starts: list[str] = []
    for pr in combined:
        login, typ = _author(pr)
        assoc = str(pr.get("authorAssociation") or pr.get("author_association") or "")
        if not is_external_author(assoc, login, typ):
            continue
        closed_ext += 1
        if assoc in NEWCOMER_ASSOC:
            newcomer_closed += 1
        merged_at = pr.get("mergedAt") or pr.get("merged_at")
        is_merged = bool(merged_at) or pr in merged
        if is_merged:
            merged_ext += 1
            if assoc in NEWCOMER_ASSOC:
                newcomer_merged += 1
            hours = _hours_between(
                pr.get("createdAt") or pr.get("created_at"), merged_at
            )
            if hours is not None:
                merge_hours.append(hours)
        created = pr.get("createdAt") or pr.get("created_at") or pr.get("closedAt")
        if created:
            starts.append(str(created)[:10])
        first = _first_maint_hours(pr)
        if first is not None:
            resp_hours.append(first)
    start = min(starts) if starts else None
    end = max(starts) if starts else None
    return _from_counts(
        closed_ext=closed_ext,
        merged_ext=merged_ext,
        newcomer_closed=newcomer_closed,
        newcomer_merged=newcomer_merged,
        first_response_hours=_median(resp_hours),
        merge_hours=_median(merge_hours),
        ignored_ext_n=None,
        sampled=len(combined),
        truncated=True,
        sample_start=start,
        sample_end=end,
    )


def compute_openness(feat: FeaturesBlob | Mapping[str, Any] | None) -> OpennessResult:
    if feat is None:
        return _na("no features")
    get = (
        feat.get if isinstance(feat, Mapping) else lambda k, d=None: getattr(feat, k, d)
    )
    closed_ext = _int(get("pr_external_closed_n"))
    merged_ext = _int(get("pr_external_merged_closed_n"))
    if closed_ext is None or merged_ext is None:
        return _na("missing external closed PR sample")
    return _from_counts(
        closed_ext=closed_ext,
        merged_ext=merged_ext,
        newcomer_closed=_int(get("pr_newcomer_closed_n")) or 0,
        newcomer_merged=_int(get("pr_newcomer_merged_n")) or 0,
        first_response_hours=_float(get("pr_ext_first_response_hours")),
        merge_hours=_float(get("pr_ext_merge_hours")),
        ignored_ext_n=None,
        sampled=_int(get("pr_closed_sample_n")) or closed_ext,
        truncated=_bool(get("pr_sample_truncated"), default=True),
        sample_start=_str(get("pr_sample_start")),
        sample_end=_str(get("pr_sample_end")),
    )


def _from_counts(
    *,
    closed_ext: int,
    merged_ext: int,
    newcomer_closed: int,
    newcomer_merged: int,
    first_response_hours: float | None,
    merge_hours: float | None,
    ignored_ext_n: int | None,
    sampled: int,
    truncated: bool = True,
    sample_start: str | None = None,
    sample_end: str | None = None,
) -> OpennessResult:
    merged_ext = min(merged_ext, closed_ext)
    stats = {
        "sample_n": closed_ext,
        "closed_ext": closed_ext,
        "merged_ext": merged_ext,
        "newcomer_closed": newcomer_closed,
        "newcomer_merged": newcomer_merged,
        "first_response_hours": first_response_hours,
        "merge_hours": merge_hours,
        "sampled_prs": sampled,
        "truncated": truncated,
        "sample_start": sample_start,
        "sample_end": sample_end,
        "window": "recent_closed",
        "window_zh": "最近已关闭外部 PR 样本（非全历史）",
        "ttfr_zh": "近期样本首次维护者回复中位数",
    }
    if closed_ext < MIN_CLOSED_EXT:
        return OpennessResult(
            score=None,
            confidence="low",
            sample_n=closed_ext,
            closed_ext=closed_ext,
            merged_ext=merged_ext,
            newcomer_closed=newcomer_closed,
            newcomer_merged=newcomer_merged,
            first_response_hours=first_response_hours,
            merge_hours=merge_hours,
            ignored_ext_n=None,
            why=f"UNKNOWN (n_ext={closed_ext} < {MIN_CLOSED_EXT}); not 0",
            na=True,
            truncated=truncated,
            sample_start=sample_start,
            sample_end=sample_end,
            stats=stats,
        )
    lb = wilson_lower_bound(merged_ext, closed_ext)
    score = None if lb is None else round(100.0 * lb, 4)
    conf = "high" if closed_ext >= 20 else "medium"
    return OpennessResult(
        score=score,
        confidence=conf,
        sample_n=closed_ext,
        closed_ext=closed_ext,
        merged_ext=merged_ext,
        newcomer_closed=newcomer_closed,
        newcomer_merged=newcomer_merged,
        first_response_hours=first_response_hours,
        merge_hours=merge_hours,
        ignored_ext_n=None,
        why=f"Wilson LB of {merged_ext}/{closed_ext} recent sampled external closed PRs",
        na=False,
        truncated=truncated,
        sample_start=sample_start,
        sample_end=sample_end,
        stats=stats,
    )


def _na(why: str) -> OpennessResult:
    return OpennessResult(
        score=None,
        confidence="low",
        sample_n=0,
        closed_ext=0,
        merged_ext=0,
        newcomer_closed=0,
        newcomer_merged=0,
        first_response_hours=None,
        merge_hours=None,
        ignored_ext_n=None,
        why=why,
        na=True,
        truncated=True,
        stats={"sample_n": None, "truncated": True, "window": "recent_closed"},
    )


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default


def _bot_login(login: str | None, type_: str | None) -> bool:
    if is_bot(login, type_):
        return True
    if not login:
        return False
    low = login.lower().removesuffix("[bot]")
    return low in BOT_LOGINS or login.lower().endswith("[bot]")


def _author(pr: Mapping[str, Any]) -> tuple[str | None, str | None]:
    author = pr.get("author") if isinstance(pr.get("author"), Mapping) else None
    if author is None:
        return None, None
    type_ = author.get("type") or author.get("__typename")
    return (
        str(author.get("login")) if author.get("login") else None,
        str(type_) if type_ else None,
    )


def _ignored_closed_unmerged(pr: Mapping[str, Any]) -> bool:
    reviews = pr.get("reviews") if isinstance(pr.get("reviews"), Mapping) else {}
    try:
        rc = int(reviews.get("totalCount") or 0)
    except (TypeError, ValueError):
        rc = 0
    if rc > 0:
        return False
    comments = pr.get("comments") if isinstance(pr.get("comments"), Mapping) else {}
    nodes = comments.get("nodes") if isinstance(comments, Mapping) else None
    if not isinstance(nodes, list):
        return True
    for cmt in nodes:
        if (
            isinstance(cmt, Mapping)
            and str(cmt.get("authorAssociation") or "") in MAINT_ASSOC
        ):
            return False
    return True


def _first_maint_hours(pr: Mapping[str, Any]) -> float | None:
    created = pr.get("createdAt") or pr.get("created_at")
    comments = pr.get("comments") if isinstance(pr.get("comments"), Mapping) else {}
    nodes = comments.get("nodes") if isinstance(comments, Mapping) else None
    if not isinstance(nodes, list):
        return None
    first: datetime | None = None
    for cmt in nodes:
        if not isinstance(cmt, Mapping):
            continue
        if str(cmt.get("authorAssociation") or "") not in MAINT_ASSOC:
            continue
        at = _parse_dt(cmt.get("createdAt") or cmt.get("created_at"))
        if at is None:
            continue
        if first is None or at < first:
            first = at
    start = _parse_dt(created)
    if first is None or start is None:
        return None
    hours = (first - start).total_seconds() / 3600.0
    return hours if hours >= 0 else None


def _hours_between(start: Any, end: Any) -> float | None:
    a, b = _parse_dt(start), _parse_dt(end)
    if a is None or b is None:
        return None
    hours = (b - a).total_seconds() / 3600.0
    return hours if hours >= 0 else None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
