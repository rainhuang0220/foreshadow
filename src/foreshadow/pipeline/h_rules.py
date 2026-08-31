from __future__ import annotations

from dataclasses import dataclass, field

from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.direction import is_keyword_stuffing
from foreshadow.pipeline.features import (
    clip,
    is_readme_only_tree,
    readme_install,
    screenshot_only,
)

# Spec Hard rejects / H7 matching — source phrases; fold at match time.
SPAM_LEXICON = (
    "chatgpt wrapper",
    "gpt-4 wrapper",
    "gpt4o wrapper",
    "best ai agent",
    "auto gpt",
    "airdrop",
    "free crypto",
    "1000 stars",
    "buy followers",
    "openai api key",
    "jailbreak gpt",
    "trending 🔥🔥",
    "made with gpt",
)

README_CHARS = 20_000
_H10_PHRASES = (
    "description of the project",
    "# project-name",
    "add a readme",
)


@dataclass(frozen=True)
class HResult:
    fired: list[str]
    vetoed: bool
    veto_reason: str | None
    tree_missing: bool = False
    flags: list[str] = field(default_factory=list)


def h7_fold(s: str) -> str:
    s = (s or "").lower().replace("-", " ").replace("_", " ")
    return " ".join(s.split())


def h7_haystack(repo: object) -> str:
    topics = _attr(repo, "topics") or []
    excerpt = (_attr(repo, "readme_excerpt") or "")[:README_CHARS]
    text = " ".join(
        [
            _attr(repo, "name") or "",
            _attr(repo, "full_name") or "",
            _attr(repo, "description") or "",
            " ".join(topics),
            excerpt,
        ]
    )
    return h7_fold(text)


def h7_fires(repo: object) -> bool:
    hay = h7_haystack(repo)
    return any(h7_fold(phrase) in hay for phrase in SPAM_LEXICON)


def evaluate_h(repo: object) -> HResult:
    names = _tree_names(repo)
    tree_missing = names is None
    fired: list[str] = []

    if _h1(repo):
        fired.append("H1")
    if _flag(repo, "is_fork", "isFork"):
        fired.append("H2")
    if names is not None and is_readme_only_tree(names):
        fired.append("H3")
    if _h4(repo):
        fired.append("H4")
    if _h5(repo):
        fired.append("H5")
    if _h6(repo):
        fired.append("H6")
    if _h7(repo):
        fired.append("H7")
    if _h8(repo):
        fired.append("H8")
    if _h9(repo):
        fired.append("H9")
    if _h10(repo):
        fired.append("H10")

    vetoed = bool(fired)
    reason = ",".join(fired) if fired else None
    return HResult(
        fired=fired,
        vetoed=vetoed,
        veto_reason=reason,
        tree_missing=tree_missing,
        flags=list(fired),
    )


def apply_penalties(scores: ScoreBreakdown, repo: object) -> ScoreBreakdown:
    flags = list(scores.flags)
    d_expl = 0.0
    d_opp = 0.0
    d_real = 0.0
    d_contrib = 0.0
    d_maint = 0.0
    d_dir = 0.0
    cap_explosion: float | None = None
    momentum_low = False

    s = _num(repo, "S")
    fork_star = _num(repo, "fork_star")
    age = _num(repo, "age_days")
    c = _num(repo, "C")
    u30 = _num(repo, "U_commit_30d")

    if s is not None and s >= 200 and fork_star is not None and fork_star < 0.03:
        flags.append("P1")
        d_expl -= 25
        d_opp -= 10
    if s is not None and s >= 200 and fork_star is not None and fork_star > 0.8:
        flags.append("P2")
        d_opp -= 15

    has_wf = _attr(repo, "has_workflows")
    gap_tests = _attr(repo, "gap_tests")
    if has_wf is None:
        has_wf = _blob_attr(repo, "has_workflows")
    if gap_tests is None:
        gap_tests = _blob_attr(repo, "gap_tests")
    if has_wf is False and gap_tests == 1:
        flags.append("P3")
        d_contrib -= 10
        d_maint -= 5

    if _screenshot_only(repo):
        flags.append("P4")
        d_real -= 15

    if c == 1 and age is not None and age >= 60 and s is not None and s >= 150:
        flags.append("P5")

    if age is not None and age < 7:
        flags.append("P6")
        cap_explosion = 40
        momentum_low = True

    if is_keyword_stuffing(_attr(repo, "description") or ""):
        flags.append("P7")
        d_dir -= 20
        d_opp -= 10

    s_prev = _s_prev(repo)
    if s is not None and s_prev is not None and (s - s_prev) >= 50 and u30 == 0:
        flags.append("P8")
        flags.append("p8_spike_no_committers")
        d_expl -= 25
        d_opp -= 10

    explosion = _shift(scores.explosion, d_expl)
    if cap_explosion is not None and explosion.value is not None:
        explosion = explosion.model_copy(
            update={"value": clip(explosion.value, 0, cap_explosion)}
        )
    else:
        explosion = _clip_cs(explosion)

    momentum = scores.momentum
    if momentum_low:
        momentum = momentum.model_copy(update={"confidence": "low"})

    return scores.model_copy(
        update={
            "opportunity": _clip_cs(_shift(scores.opportunity, d_opp)),
            "explosion": explosion,
            "contribution": _clip_cs(_shift(scores.contribution, d_contrib)),
            "momentum": momentum,
            "real_user": _clip_cs(_shift(scores.real_user, d_real)),
            "maintainer": _clip_cs(_shift(scores.maintainer, d_maint)),
            "direction_fit": _clip_cs(_shift(scores.direction_fit, d_dir)),
            "flags": flags,
        }
    )


def _h1(repo: object) -> bool:
    return (
        _flag(repo, "archived", "is_archived", "isArchived")
        or _flag(repo, "disabled", "is_disabled", "isDisabled")
        or _flag(repo, "is_empty", "isEmpty")
    )


def _h4(repo: object) -> bool:
    s = _num(repo, "S")
    i_open = _num(repo, "I_open", "i_open")
    i_closed = _num(repo, "I_closed", "i_closed")
    age = _num(repo, "age_days")
    fork_star = _num(repo, "fork_star")
    has_issues = _attr(repo, "has_issues")
    if has_issues is None:
        has_issues = _attr(repo, "hasIssuesEnabled")
    if None in (s, i_open, i_closed, age, fork_star) or has_issues is not True:
        return False
    return s >= 400 and (i_open + i_closed) == 0 and age >= 14 and fork_star < 0.04


def _h5(repo: object) -> bool:
    age = _num(repo, "age_days")
    s = _num(repo, "S")
    c = _num(repo, "C")
    if None in (age, s, c):
        return False
    return age <= 14 and s >= 2_000 and c <= 2


def _h6(repo: object) -> bool:
    age = _num(repo, "age_days")
    s = _num(repo, "S")
    fork_star = _num(repo, "fork_star")
    u30 = _num(repo, "U_commit_30d")
    if None in (age, s, fork_star, u30):
        return False
    return age <= 45 and s >= 5_000 and fork_star < 0.03 and u30 <= 2


def _h7(repo: object) -> bool:
    c = _num(repo, "C")
    if c is None or c > 3:
        return False
    if _has_install(repo):
        return False
    return h7_fires(repo)


def _h8(repo: object) -> bool:
    pushed_age = _num(repo, "pushed_age_days")
    i_open = _num(repo, "I_open", "i_open")
    u30 = _num(repo, "U_commit_30d")
    if None in (pushed_age, i_open, u30):
        return False
    return pushed_age >= 180 and i_open >= 8 and u30 == 0


def _h9(repo: object) -> bool:
    spdx = _attr(repo, "license_spdx")
    s = _num(repo, "S")
    age = _num(repo, "age_days")
    if s is None or age is None:
        return False
    unlicensed = spdx is None or str(spdx).upper() == "NOASSERTION"
    return unlicensed and s >= 300 and age >= 30


def _h10(repo: object) -> bool:
    excerpt = _attr(repo, "readme_excerpt")
    if excerpt is None or len(excerpt) >= 400:
        return False
    low = excerpt.lower()
    if any(p in low for p in _H10_PHRASES):
        return True
    name = _attr(repo, "name") or ""
    return bool(name and low.strip() == f"# {name}".lower())


def _has_install(repo: object) -> bool:
    val = _attr(repo, "readme_install")
    if val is None:
        val = _blob_attr(repo, "readme_install")
    if val is None:
        excerpt = _attr(repo, "readme_excerpt") or ""
        return bool(readme_install(excerpt)) if excerpt else False
    return bool(val)


def _screenshot_only(repo: object) -> bool:
    val = _attr(repo, "screenshot_only")
    if val is None:
        val = _blob_attr(repo, "screenshot_only")
    if val is None:
        excerpt = _attr(repo, "readme_excerpt") or ""
        return screenshot_only(excerpt) if excerpt else False
    return bool(val)


def _tree_names(repo: object) -> list[str] | None:
    for key in ("root_names", "tree_names"):
        if hasattr(repo, key):
            val = getattr(repo, key)
            return None if val is None else list(val)
    blob = getattr(repo, "features", None)
    if blob is not None:
        val = getattr(blob, "tree_names", None)
        return None if val is None else list(val)
    return None


def _s_prev(repo: object) -> int | None:
    for key in ("S_prev", "S_t_minus_1", "stars_yesterday"):
        if hasattr(repo, key):
            val = getattr(repo, key)
            if val is not None:
                return int(val)
    return None


def _flag(repo: object, *names: str) -> bool:
    return any(getattr(repo, name, None) is True for name in names)


def _attr(repo: object, name: str):
    return getattr(repo, name, None)


def _blob_attr(repo: object, name: str):
    blob = getattr(repo, "features", None)
    if blob is None:
        return None
    return getattr(blob, name, None)


def _num(repo: object, *names: str) -> float | int | None:
    for name in names:
        if hasattr(repo, name):
            val = getattr(repo, name)
            if val is not None:
                return val
        blob_val = _blob_attr(repo, name)
        if blob_val is not None:
            return blob_val
    return None


def _shift(cs: ComponentScore, delta: float) -> ComponentScore:
    if cs.value is None or delta == 0:
        return cs
    return cs.model_copy(update={"value": cs.value + delta})


def _clip_cs(cs: ComponentScore) -> ComponentScore:
    if cs.value is None:
        return cs
    return cs.model_copy(update={"value": clip(cs.value, 0, 100)})
