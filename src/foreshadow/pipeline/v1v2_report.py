"""In-memory v1 vs v2 Opportunity review. Does not insert snapshots."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import ScoringSettings
from foreshadow.pipeline.compare import (
    KNOWN_BIAS_RECENCY,
    assign_pool_ranks,
    identity_key,
    rank_delta,
)
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.score_v2 import score_repo_v2

STAR_BANDS = ("<20", "20-100", "100-300", "300-1k", "1k-3k", "3k+")
AGE_BANDS = ("<30d", "30-90d", "90-180d", "180d-1y", "1-3y", "3y+")
ACTIVITY_BANDS = ("<=7d", "8-30d", "31-90d", "90d+")
CONTRIB_BANDS = ("1", "2-5", "6-15", "16-30", "31-80", "80+", "UNKNOWN", "C_censored")
MAINT_BANDS = ("UNKNOWN", "none", "low", "mid", "high")


def star_band(stars: int | None) -> str:
    if stars is None:
        return "UNKNOWN"
    if stars < 20:
        return "<20"
    if stars < 100:
        return "20-100"
    if stars < 300:
        return "100-300"
    if stars < 1000:
        return "300-1k"
    if stars < 3000:
        return "1k-3k"
    return "3k+"


def age_band(age_days: int | None) -> str:
    if age_days is None:
        return "UNKNOWN"
    if age_days < 30:
        return "<30d"
    if age_days < 90:
        return "30-90d"
    if age_days < 180:
        return "90-180d"
    if age_days < 365:
        return "180d-1y"
    if age_days < 365 * 3:
        return "1-3y"
    return "3y+"


def activity_band(pushed_age_days: int | None) -> str:
    if pushed_age_days is None:
        return "UNKNOWN"
    if pushed_age_days <= 7:
        return "<=7d"
    if pushed_age_days <= 30:
        return "8-30d"
    if pushed_age_days <= 90:
        return "31-90d"
    return "90d+"


def contrib_band(c: int | None, censored: bool) -> str:
    if censored:
        return "C_censored"
    if c is None:
        return "UNKNOWN"
    if c <= 1:
        return "1"
    if c <= 5:
        return "2-5"
    if c <= 15:
        return "6-15"
    if c <= 30:
        return "16-30"
    if c <= 80:
        return "31-80"
    return "80+"


def maint_band(touch: float | None) -> str:
    if touch is None:
        return "UNKNOWN"
    if touch <= 0:
        return "none"
    if touch <= 0.3:
        return "low"
    if touch <= 0.7:
        return "mid"
    return "high"


def _pct(counter: Counter[str], n: int, keys: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for key in keys:
        v = counter.get(key, 0)
        out[key] = {"n": v, "pct": round(100.0 * v / n, 1) if n else 0.0}
    return out


def _card(rank: int, scored: Any, data: dict[str, Any]) -> dict[str, Any]:
    feat = data.get("features") or {}
    return {
        "rank": rank,
        "full_name": scored.full_name,
        "stars": data.get("S"),
        "age_days": data.get("age_days"),
        "C": data.get("C"),
        "opportunity": scored.breakdown.opportunity.value,
        "early_entry": scored.breakdown.early_entry.value,
        "gap": scored.breakdown.gap.value,
        "contribution_opp": scored.breakdown.contribution_opp.value,
        "maintainer": scored.breakdown.maintainer.value,
        "real_user": scored.breakdown.real_user.value,
        "explosion": scored.breakdown.explosion.value,
        "vetoed": scored.breakdown.vetoed,
        "pushed_age_days": data.get("pushed_age_days"),
        "maint_touch": feat.get("maint_touch") if isinstance(feat, dict) else None,
    }


def build_comparison(
    items_v1: list[tuple[Any, dict[str, Any]]],
    items_v2: list[tuple[Any, dict[str, Any]]],
    *,
    run_date: str,
) -> dict[str, Any]:
    n = len(items_v1)
    r1 = assign_pool_ranks(items_v1)
    r2 = assign_pool_ranks(items_v2)
    v1_by_key = {identity_key(s, d): (s, d) for s, d in items_v1}
    v2_by_key = {identity_key(s, d): (s, d) for s, d in items_v2}
    deltas = []
    for key, (s1, d1) in v1_by_key.items():
        pair = v2_by_key.get(key)
        if pair is None:
            continue
        s2, _d2 = pair
        delta = rank_delta(r1.get(key), r2.get(key))
        deltas.append(
            {
                "full_name": s1.full_name,
                "v1_rank": r1.get(key),
                "v2_rank": r2.get(key),
                "rank_delta": delta,
                "v1_opportunity": s1.breakdown.opportunity.value,
                "v2_opportunity": s2.breakdown.opportunity.value,
                "stars": d1.get("S"),
            }
        )
    deltas.sort(key=lambda row: -(row["rank_delta"] or 0))
    ordered_v1 = sorted(items_v1, key=lambda it: r1[identity_key(it[0], it[1])])
    ordered_v2 = sorted(items_v2, key=lambda it: r2[identity_key(it[0], it[1])])

    def hist(items: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
        stars = Counter(star_band(d.get("S")) for _, d in items)
        ages = Counter(age_band(d.get("age_days")) for _, d in items)
        act = Counter(activity_band(d.get("pushed_age_days")) for _, d in items)
        contrib = Counter(
            contrib_band(d.get("C"), bool(d.get("C_censored"))) for _, d in items
        )
        maint = Counter()
        for _, d in items:
            feat = d.get("features") or {}
            touch = feat.get("maint_touch") if isinstance(feat, dict) else None
            maint[maint_band(touch)] += 1
        k = len(items)
        return {
            "stars": _pct(stars, k, STAR_BANDS),
            "age": _pct(ages, k, AGE_BANDS),
            "activity": _pct(act, k, ACTIVITY_BANDS),
            "contributors": _pct(contrib, k, CONTRIB_BANDS),
            "maintainer_touch_proxy": _pct(maint, k, MAINT_BANDS),
        }

    share_7d = 0.0
    if n:
        share_7d = round(
            100.0
            * sum(1 for _, d in items_v1 if activity_band(d.get("pushed_age_days")) == "<=7d")
            / n,
            1,
        )
    return {
        "date": run_date,
        "universe": n,
        "sort_key": "opportunity DESC, explosion DESC, stars ASC, node_id",
        "official": "v1",
        "top20_v1": [_card(i, s, d) for i, (s, d) in enumerate(ordered_v1[:20], start=1)],
        "top20_v2": [_card(i, s, d) for i, (s, d) in enumerate(ordered_v2[:20], start=1)],
        "top10_v1": [_card(i, s, d) for i, (s, d) in enumerate(ordered_v1[:10], start=1)],
        "top10_v2": [_card(i, s, d) for i, (s, d) in enumerate(ordered_v2[:10], start=1)],
        "bands_all": hist(items_v1),
        "bands_top20_v1": hist(ordered_v1[:20]),
        "bands_top20_v2": hist(ordered_v2[:20]),
        "largest_winners": [row for row in deltas if (row["rank_delta"] or 0) > 0][:10],
        "largest_losers": sorted(
            [row for row in deltas if (row["rank_delta"] or 0) < 0],
            key=lambda row: row["rank_delta"] or 0,
        )[:10],
        "rank_deltas": deltas,
        "known_bias": {
            KNOWN_BIAS_RECENCY: {
                "flag": share_7d >= 80.0,
                "share_activity_le_7d": share_7d,
                "note": "pushed_at is activity, not star growth; must not fill windows.v7",
            }
        },
        "honest_limits": {
            "maintainer_ttr": "UNKNOWN",
            "star_growth": "UNKNOWN without local v7",
            "official_top5": "v1 only; empty without v7",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# v1 vs v2 Review",
        "",
        f"Date: {report['date']}. Universe: {report['universe']} scored. Official ranking: **v1**.",
        "",
        "Sort: Opportunity DESC (NULL last), Explosion DESC, stars ASC, node_id.",
        "",
        "## Top 10 before / after",
        "",
        "| v1 | repo | ★ | Opp | v2 | repo | ★ | Opp |",
        "|---:|---|---:|---:|---:|---|---:|---:|",
    ]
    t1 = report["top10_v1"]
    t2 = report["top10_v2"]
    for i in range(max(len(t1), len(t2))):
        a = t1[i] if i < len(t1) else {}
        b = t2[i] if i < len(t2) else {}
        lines.append(
            f"| {a.get('rank', '')} | {a.get('full_name', '')} | {a.get('stars', '')} | "
            f"{_fmt(a.get('opportunity'))} | {b.get('rank', '')} | {b.get('full_name', '')} | "
            f"{b.get('stars', '')} | {_fmt(b.get('opportunity'))} |"
        )
    lines += ["", "## Star / age / activity (all scored)", ""]
    lines += _band_table(report["bands_all"])
    lines += ["", "## Top 20 bands v1 vs v2", ""]
    lines += ["### v1 Top 20", ""]
    lines += _band_table(report["bands_top20_v1"])
    lines += ["", "### v2 Top 20", ""]
    lines += _band_table(report["bands_top20_v2"])
    lines += ["", "## Largest winners (positive rank_delta = rose under v2)", ""]
    for row in report["largest_winners"]:
        lines.append(
            f"- {row['full_name']}: v1 #{row['v1_rank']} → v2 #{row['v2_rank']} "
            f"(Δ {row['rank_delta']:+d}) ★{row['stars']}"
        )
    lines += ["", "## Largest losers", ""]
    for row in report["largest_losers"]:
        lines.append(
            f"- {row['full_name']}: v1 #{row['v1_rank']} → v2 #{row['v2_rank']} "
            f"(Δ {row['rank_delta']:+d}) ★{row['stars']}"
        )
    bias = report["known_bias"][KNOWN_BIAS_RECENCY]
    lines += [
        "",
        "## Known biases",
        "",
        (
            f"- `{KNOWN_BIAS_RECENCY}`: flag={bias['flag']}, "
            f"share ≤7d last push = {bias['share_activity_le_7d']}%"
        ),
        f"- {bias['note']}",
        "- Maintainer TTR: UNKNOWN (no comment timestamps).",
        "- Star growth: UNKNOWN without local v7. Activity ≠ star_growth.",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.1f}"


def _band_table(bands: dict[str, Any]) -> list[str]:
    lines = ["| dim | bucket | n | pct |", "|---|---|---:|---:|"]
    for dim in ("stars", "age", "activity", "contributors", "maintainer_touch_proxy"):
        body = bands.get(dim) or {}
        for bucket, cell in body.items():
            lines.append(f"| {dim} | {bucket} | {cell['n']} | {cell['pct']} |")
    return lines


def score_corpus(
    rows: list[dict[str, Any]],
    *,
    clock: Clock,
    scoring: ScoringSettings | None = None,
) -> tuple[list[tuple[Any, dict[str, Any]]], list[tuple[Any, dict[str, Any]]]]:
    scoring = scoring or ScoringSettings()
    v1: list[tuple[Any, dict[str, Any]]] = []
    v2: list[tuple[Any, dict[str, Any]]] = []
    for data in rows:
        v1.append((score_repo(data, clock=clock, scoring=scoring), data))
        v2.append((score_repo_v2(data, clock=clock, scoring=scoring), data))
    return v1, v2


def parse_age_days(created_at: str | None, today: date) -> int | None:
    if not created_at:
        return None
    try:
        text = created_at[:-1] + "+00:00" if created_at.endswith("Z") else created_at
        day = datetime.fromisoformat(text).date()
    except ValueError:
        try:
            day = date.fromisoformat(created_at[:10])
        except ValueError:
            return None
    return max((today - day).days, 0)


def write_review(path_json: Path, path_md: Path, report: dict[str, Any]) -> None:
    path_json.parent.mkdir(parents=True, exist_ok=True)
    path_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    path_md.write_text(render_markdown(report), encoding="utf-8")
