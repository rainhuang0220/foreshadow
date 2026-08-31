# Opportunity Engine v2 — Activity Observability + Activity Momentum Preview (PR-A)

**Official scoring remains v1.** Activity is Preview only. Never written into `windows.v7`. Never labeled Star Growth.

| Lock | This PR |
|---|---|
| `score.py` / `select.py` | unchanged |
| 55 / 35 / local v7 / Official Top 5 | unchanged (still 0) |
| Discovery PR-D / Hydration PR-H | unchanged |
| Fake snapshots | none |
| In-memory replay | 2026-08-25 120 from `dogfood/local/home` (PR-H force run) |

---

## 1. Activity 数据覆盖率

Source: REST commits (`since=now-30d`) + releases page, persisted only on Phase B/M (`features_json`). Missing key = UNKNOWN. `0` = successful empty fetch.

| Field | Known | UNKNOWN | Notes |
|---|---:|---:|---|
| `commits_7d` | **60 / 120 (50%)** | 50% | 7d cutoff on the same truncated commit list |
| `commits_30d` | **60 / 120** | 50% | `len(fetched)`; medium cap 100, deep cap 300 (lower bound if truncated) |
| `releases_30d` | **60 / 120** | 50% | first 10 releases, then 30d filter |
| `recent_contributors_7d` | **60 / 120** | 50% | unique non-bot logins in the 7d slice |

The four fields are coupled: all known on the 30 deep + 30 medium, all UNKNOWN on the 60 lightweight.

---

## 2. Formula (v2 Preview)

Configurable on `ScoringSettings` (not `WEIGHT_KEYS`, not v1):

```text
intensity  = clip01(commits_7d / 15)                 # 40
persist    = clip01(commits_30d / 30)                # 25
breadth    = clip01(recent_contributors_7d / 4)      # 25
release    = clip01(releases_30d / 2)                # 10

activity_momentum = 100 * weighted mean of known terms
activity_concentration = commits_7d / max(commits_30d, 1)   # Board only; not "acceleration"
```

Gate: `commits_30d is None` → `activity_momentum = UNKNOWN` (not 0). Fetched zeros → 0 / VERY_LOW.

Class: `[0,15) VERY_LOW`, `[15,35) LOW`, `[35,55) MEDIUM`, `[55,75) HIGH`, `[75,100] VERY_HIGH`.

Worked examples (tests):

| Profile | AM | Class |
|---|---:|---|
| 1 / 1 / 0 rel / 1 contrib (single push) | **9.75** | VERY_LOW |
| 10 / 25 / 2 rel / 5 contrib (sustained) | **82.5** | VERY_HIGH |
| 20 commits, 1 author, 0 rel | ~63 | HIGH (diversity holds it down vs 5 authors) |
| all 0 (known empty) | 0 | VERY_LOW |
| all missing | UNKNOWN | — |

**v2 mix:** when official `v7` is NA **and** AM is known, fill the existing 20-point `momentum` slot with Activity Momentum (`why` says not star growth). UNKNOWN leaves that slot NA (omit, not 0). v1 `_momentum` stays NA.

Rejected from the design agent: a hard solo-author cap at 49. Diversity is already 25% of the mix; a cap would flatten real one-maintainer projects (this corpus is full of them).

---

## 3. Activity 分布 (2026-08-25 replay)

| Class | n | /120 |
|---|---:|---:|
| VERY_HIGH | 40 | 33% |
| HIGH | 11 | 9% |
| MEDIUM | 4 | 3% |
| LOW | 3 | 2.5% |
| VERY_LOW | 2 | 1.7% |
| UNKNOWN | **60** | 50% |

Known 60: 51 / 60 are HIGH or VERY_HIGH. That is not “everyone who pushed today scores 100”: see §7.

---

## 4. 1★ / 新仓

Exact `stars<=5` and `age<=3d`: **0** in this 120.

Closest:

| Slice | n | Activity |
|---|---:|---|
| stars ≤5 | 24 | 16 UNKNOWN, 5 VERY_HIGH, 2 HIGH, 1 MEDIUM |
| stars ≤5 and age ≤7d | 4 | **all UNKNOWN** (lightweight; not Phase B/M) |
| age ≤3d (any stars) | 1 | `WalrusQuant/sports-analytic-skills` 33★ age 1d, **VERY_HIGH 76** (`commits_7d=50`) |

Hydrated tiny repos are **not** one-push seedlings. They have real commit volume:

- `TraceFold/tracefold` 2★ age 12d: c7=14 c30=42 rel=2 u7=1 → **VERY_HIGH 78.6**
- `mindsers/ohmyharness` 3★ age 19d: c7=42 c30=100 → **VERY_HIGH 81.3**
- Lightweight 1★ (`Mechanica-Labs/goliath` age 4d): AM **UNKNOWN**, rank 84→85. No fake 0, no fake boost.

`tiezbro/cc-switch-headless` is **not in this 120** (live search seating after PR-H force run). Do not invent its AM.

**Answer:** Activity describes facts when data exist. A 2★ repo with 14 commits / 2 releases is correctly HIGH. A 1★ with no hydrate stays UNKNOWN, not VERY_HIGH. Entry Window can still lift UNKNOWN youth on Preview — that is **not** solved by Activity alone.

---

## 5. &lt;300★ 活跃仓

`stars<300` and `age>3d` and class HIGH/VERY_HIGH: **32**.

They keep Preview rank. Examples:

| repo | ★ | AM | class | v2 old → new |
|---|---:|---:|---|---|
| curie-eng/curie | 33 | 100 | VERY_HIGH | 4 → **3** |
| bobmatnyc/trusty-tools | 18 | 87.5 | VERY_HIGH | 2 → 5 |
| alizahidraja/isnad | 36 | 100 | VERY_HIGH | 14 → **7** |
| eigenpal/docx-editor | 253 | 87.5 | VERY_HIGH | 13 → **9** |
| ThinkOffApp/CarWatch | 10 | 76.3 | VERY_HIGH | 20 → 19 |

Activity did **not** flatten small active repos.

---

## 6. 1000+★ 成熟仓

n=21. Known AM: 6 (5 VERY_HIGH, 1 HIGH). Other 15 lightweight UNKNOWN (Opportunity stays ~8–9 from direction-only mix).

| repo | ★ | AM | v2 |
|---|---:|---|---|
| Gitlawb/zero | 1626 | 94.7 VERY_HIGH | **#1 → #1** |
| NVIDIA-NeMo/Gym | 1139 | 95.0 VERY_HIGH | #6 → #6 |
| agentlas-ai/Agentlas-OS | 1108 | 81.3 VERY_HIGH | 30 → 24 |
| boxlite-ai/boxlite | 2275 | UNKNOWN | 93 → 94 |

Activity does not mass-kill mature repos. Unhydrated 1k+ stay low because v7/C/issues are still NA, not because AM is 0.

---

## 7. Rank Delta (old v2 without AM fill → new v2)

Old v2 = stored `scores.score_version=v2` from PR-H (momentum NA). New v2 = same snapshots, AM fills the NA momentum slot. **No new GitHub calls. No fake snapshots.**

### Top 10

| old | new | repo | ★ | AM | Δ |
|---:|---:|---|---:|---|---:|
| 1 | **1** | Gitlawb/zero | 1626 | VERY_HIGH 94.7 | 0 |
| 3 | **2** | caura-ai/caura | 449 | VERY_HIGH 100 | +1 |
| 4 | **3** | curie-eng/curie | 33 | VERY_HIGH 100 | +1 |
| 5 | **4** | mudler/vllm.cpp | 350 | VERY_HIGH 100 | +1 |
| 2 | **5** | bobmatnyc/trusty-tools | 18 | VERY_HIGH 87.5 | −3 |
| 6 | **6** | NVIDIA-NeMo/Gym | 1139 | VERY_HIGH 95.0 | 0 |
| 14 | **7** | alizahidraja/isnad | 36 | VERY_HIGH 100 | +7 |
| 7 | **8** | maddada/Ghostex | 706 | VERY_HIGH 87.5 | −1 |
| 13 | **9** | eigenpal/docx-editor | 253 | VERY_HIGH 87.5 | +4 |
| 11 | **10** | opena2a-org/hackmyagent | 38 | VERY_HIGH 81.3 | +1 |

### Named effects

| Project | ★ | Activity | v1 | v2 before | v2 with Activity |
|---|---:|---|---:|---:|---:|
| trusty-tools | 18 | VERY_HIGH 87.5 (c7=178, rel=10) | #10 | #2 | **#5** |
| Gitlawb/zero | 1626 | VERY_HIGH 94.7 (u7=9) | #1 | #1 | **#1** |
| Lyzr-Cognis/cognis | 54 | **LOW 25.3** (c7=4, c30=4, u7=1) | #32 | **#10** | **#42** |
| MrGiovanni/PanTS | 123 | **VERY_LOW 9.75** (c7=1, c30=1) | — | #32 | **#54** |
| TraceFold/tracefold | 2 | VERY_HIGH 78.6 (c7=14, rel=2) | #53 | #9 | #12 |
| kody-w/rappterbook | 13 | HIGH 65 (300 commits, **u7=0**) | #3 | #8 | #17 |

Biggest riser: `llm-d/llm-d-router` 305★ VERY_HIGH 100, **#120 → #60**. Biggest faller among hydrated: **cognis #10 → #42**.

Star mix of Top 20 is almost unchanged (`<100` 12→11). Activity reorders *inside* the already-small Preview set; it does not restore a star ranking.

v1 Top 5 / Official: still 0. Max v1 Opportunity still &lt; 55. New v2 Opportunity can exceed 55 (zero 65.6) because the 20-point slot is no longer empty — Explosion still NA, so Official `select.py` still rejects.

---

## 8. Recency bias — main result

```text
last_pushed_at = 2026-08-25 for 120 / 120
```

Among those 120, Activity Momentum is **not** uniform:

| | n |
|---|---:|
| last_push today | 120 |
| AM known | 60 |
| of known: HIGH or VERY_HIGH | 51 |
| of known: LOW or VERY_LOW | **5** |
| UNKNOWN (lightweight) | 60 |

Same-day push **does not** imply high AM:

- `PanTS`: pushed today, **1 commit in 30d** → VERY_LOW 9.75, rank 32→54
- `curie`: pushed today, **263 commits / 7d**, 5 contributors, 9 releases → VERY_HIGH 100, rank 4→3

**Yes: Foreshadow can now tell “one push today” from “sustained 7d development + contributors + releases” — when hydrate actually collected the fields. The Board shows the four counts, concentration, and the sentence 活跃度反映开发与社区活动，不代表 Star 增长.**

The leftover recency problem is the **60 UNKNOWN** rows (including most 1★ ≤7d). They still look the same to Opportunity because AM is omitted, and v2 Early Window still treats `pushed_age_days=0` as fresh. That is S1 / more hydrate, not a formula miss.

---

## 9. Tests

`uv run pytest` → **276 passed** (9 new in `tests/test_activity_momentum.py`).

Required names all present:

- `test_single_recent_push_is_not_high_activity`
- `test_many_recent_commits_is_high_activity`
- `test_recent_contributor_diversity_affects_activity`
- `test_release_activity_affects_activity`
- `test_activity_is_not_star_growth`
- `test_zero_30d_activity_is_safe`
- `test_activity_unknown_is_not_zero`
- `test_small_active_repo_keeps_activity_advantage`
- `test_new_one_push_repo_does_not_get_fake_activity_boost`

---

## 10. Decision

```text
Activity observability: PASS (hydrated 60)
Activity vs last_push: PASS (PanTS vs curie)
Small active kept: PASS
Mature not mass-killed: PASS
1★ one-push auto-demoted: PARTIAL — no age≤3d 1★ in this 120 were hydrated;
  lightweight 1★ stay UNKNOWN; they are not given a fake AM boost
```

**Next is not “keep tuning Activity.”**

Next is **S1 Entry Window**, because UNKNOWN youth still get a high `fresh=1.0` from `last_pushed_at=today` in v2 `_entry_window`. Activity cannot see those rows.

Do not mix S1 into this PR. Do not cut over Official.

### TODO (out of hour box)

- `issues_created_*` / `prs_created_*` still UNKNOWN (REST budget).
- `commits_30d` is fetch length, truncated.
- Solo-author cap: rejected this PR.
- Persist new v2 on the next real `foreshadow run` (this experiment was in-memory).
- Optional: medium-hydrate more of the 1★ ≤7d band so AM can describe them.
