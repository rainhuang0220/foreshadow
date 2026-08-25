# Opportunity Engine 2.0 — Current Scoring Audit & Migration Plan

| Field | Value |
|---|---|
| **Status** | Research complete. **Scoring not changed.** |
| **Date** | 2026-08-25 |
| **Dogfood corpus** | 2026-08-24, 120 candidates, 1 snapshot day, official Top 5 = 0 |
| **Scoring in production** | **v1** (20/15/15/20/15/10/5). Official gates 55 / 35 / local `v7`. |

This document is the Phase 1–7 deliverable. Implementation is Phase 8+ and must not start until the owner accepts the locks in § Honest limits.

---

## Current problem

Foreshadow is supposed to find **early entry**: a project that is starting to matter, where a newcomer can still become a real contributor.

v1 + discovery currently surface **already-famous mid-size AI repos** (about 1k–6k stars). Preview Top 5 on 2026-08-24:

| Rank | Repo | Stars |
|---|---|---|
| 1 | ngxson/wllama | 1171 |
| 2 | withcatai/node-llama-cpp | 2163 |
| 3 | Michael-A-Kuykendall/shimmy | 5807 |
| 4 | ovg-project/kvcached | 1141 |
| 5 | go-skynet/go-llama.cpp | 936 |

Shortlist of 20: **zero repos under 300 stars**. Nine of twenty have ≥3000 stars. That is “good / known project,” not “early window.”

A second, separate problem: **Momentum cannot exist on day 1** because v1 defines growth only from *our* snapshots. That is honest about GitHub 2026. It is not the same as “the project had no past.”

---

## Evidence (why 1000–5000 stars win)

### 1. Discovery never asks for small-and-active

All 12 search templates include `stars:{star_min}..{star_max}` → **50..8000**.

- Floor 50 drops true seedlings from search (not a post-filter).
- Ceiling 8000 still includes famous mid-tier.
- GitHub default sort is **best-match** (popularity-correlated). `first:25` and **no pagination** keep the head.
- `breakout` is `created:>180d … sort:stars` — highest stars in the band.
- Keywords are incumbents: `llama.cpp`, `ollama`, `cuda`, `rocm`, `vllm`.
- Cap fill is FIFO by query key: MCP / RAG / local_llm / agent eat the 120 before RISC-V.

Pool 2026-08-24 (n=120): min 66, median ~740, 43% ≥1000, 36% in 1k–5k, **0 under 50**.

### 2. Phase B pre-rank sorts by raw stars

`hydrate.pre_rank_key` last numeric key is **stars** (`reverse=True`). Only ~30 repos get C / issues / tree. Lightweight board score then drops NA Momentum and ranks Gap + Early Entry + Real User — which light up on large-S / thin-C repos.

### 3. Early Entry rewards mid-size, not small

`late()` = `(S≥5000 and C≥30) or S≥20000 or C≥80`.

`late_10x = late(S*10, C*10)` is true if **C≥8** (almost every 1k-star repo). Then Early Entry sits in **70–95**.

A 70-star / 5-contributor repo takes the **micro** branch (62, clip 40–80). **v1 Early Entry prefers 1k–6k over 70.** Shimmy (5807★, C=1) is still “early” because C&lt;30.

### 4. Gap is S/C

`r = clip01((S/C − 10) / 90)`. 1171/9 ≈ 130 → r=1. 70/5 = 14 → r≈0.04. Famous-and-thin looks starved. `small_bench` also rewards C&lt;20 at any star stock.

### 5. Real User saturates on issue samples

`U_issue_ext/15`, `(bug+talk)/12`. Established trackers max this. `fork_signal` requires S≥50.

### 6. ContributionOpp is labels + missing files, not acceptance

`surface` is 70% `help_n` (GFI + help-wanted + docs labels). Missing CONTRIBUTING/tests/CI **raises** the score. No external-PR merge rate. `bus` **+8** even when nobody will review you. `maint_touch` is “a maintainer commented in the first 3 comments,” not hours-to-first-response. Maintainer is **5%** of Opportunity and **absent from board dimensions**.

### 7. Official Top 5 is correctly empty

Opportunity mix **drops** NA Momentum (no renormalize) → cap 80. Explosion is **NULL** without v7. Gate 55/35/`v7` → 0 seats. **Do not lower 55/35** to fill the list; that would promote hot-but-closed stock.

wllama is the only shortlist row with Opportunity ≥55 (55.88), and Explosion is still NA.

---

## How v1 scores are produced

| Score | Formula (v1) |
|---|---|
| **Opportunity** | 20 Momentum + 15 RealUser + 15 Gap + 20 ContributionOpp + 15 EarlyEntry + 10 Direction + 5 Maintainer. NA terms dropped, not zero-filled. |
| **Explosion** | 50% 7d relative star growth + 30% accel + 20% (1−size). **NULL if no v7.** Lifetime `S/age` is evidence only, never satisfies ≥35. |
| **Contribution** | ≡ ContributionOpp (surface / file gaps / maint_touch / direction). |

**Momentum** needs `S(today) − S(t−7)` from **local snapshots** (`window_slack_days=1`). Repo younger than 7 days → window undefined.

### What must wait ~7 local days

`v7`, `rel_growth_7d`, Momentum, published Explosion, official Top 5, `is_accelerating`, `v30`/`accel_ratio` (~30d), `v90` (~90d).

### What GitHub already gives *today* (no wait)

`createdAt`, `pushedAt`, `stargazerCount`, `forkCount`, issue/PR **counts**, README, issue sample, C (REST contributors), unique committers 30d, community profile files, `hasIssues`, license. Enough for RealUser / Gap / EarlyEntry / Maintainer / Direction. **Not** a 7-day star delta.

---

## Historical signals (2026 reality)

GitHub changelog 2026-06-30: **stargazer listing (and `starred_at`) is admin/collaborator only.** GraphQL `stargazers { edges { starredAt } }` is the same lock. No-scope PAT on a foreign public repo: 403/404/FORBIDDEN.

| Tier | Source | Day-1 star velocity? |
|---|---|---|
| 1 Direct GH star history | REST/GraphQL stargazers + `starred_at` | **Dead** for Foreshadow’s token |
| 2 Activity-derived | Forks `created_at`; issues/PRs `created:`; commits `since=`; releases | **Yes for activity, no for stars** |
| 3 Local snapshots | Daily `stargazerCount` | Honest `v7` from day 8 |
| 4 Current-only | Today’s S, age, `pushed_at` | Not a window |

**GH Archive WatchEvent** is degraded (capture often &lt;20% in 2026; no unstar). **star-history.com** is blank for foreign repos. `/stats/*` is 202-forever and denied. Traffic is owner-only. Repo events: ≤300 events and **30 days**, WatchEvent ≠ stars.

**Lock: do not write activity or GH Archive into `windows.v7`.** Label them `fork_v7`, `issues_created_7d`, `growth_external` with `source`, `window`, `confidence`. Official Explosion still requires local `v7`.

### Redefinition of 7-day v7 (product, not a lie)

```
Day 1
  External *activity* windows + current stock
  → provisional “is it moving?” (not official star Momentum)

Day 2–7
  Local snapshots accumulate
  → independent star series starts

Day 8+
  Local v7 exists
  → official Momentum / Explosion / Top 5
  If activity windows and local v7 agree → confidence ↑
  If they conflict → confidence ↓, do not average them into a fake v7
```

New projects can be **analyzed** on day 1. They still **cannot** occupy official Top 5 until local `v7` exists. Empty Top 5 remains success.

---

## Proposed v2 scoring (not implemented)

`scoring.score_version = v1` until dual-write dogfood. Schema later: `UNIQUE(run_id, repo_id, score_version)`. Never overwrite historical v1 rows.

### Weights (sum 100)

| Key | v1 | **v2** | Why |
|---|---|---|---|
| momentum (Growth) | 20 | 18 | Size term becomes reverse difficulty |
| real_user | 15 | 12 | Stars are not users |
| gap | 15 | 12 | Plus maturity offset |
| contribution_opp | 20 | 15 | Acceptance, not GFI |
| early_entry → **Entry Window** | 15 | **25** | Ranking lever |
| maintainer | 5 | **10** | Usable window |
| direction_fit | 10 | 8 | Still not a hard gate |

Official sort: **Opportunity desc, Explosion desc, Stars asc**. Stars never win.

**Do not lower 55/35.** A hot-closed 2000★ repo can clear Explosion 35 and must **fail Opportunity**. Lowering Opportunity to ~40 would promote exactly the false positive Engine 2.0 exists to stop.

### Entry Window (replaces `late()` / `late_10x`)

Continuous mix (drop NA, no renormalize):

- open_scale = 1 − log-star difficulty  
- open_identity = 1 − crowd(C)  
- age_fit from lifecycle  
- growth_open from `rel_growth_7d` if local v7 exists  
- maint_open from maintainer score  
- pr_accept from closed-PR sample (omit if NA)

Then **maturity penalty** (points, not a star hard-gate):

| Lifecycle | Entry penalty |
|---|---|
| too_new / early_validated / emerging | 0 |
| maturing | −12 |
| mature | −22 |
| stagnant | −30, then cap Entry at 35 |

Lifecycle uses **age + push + growth**, not “created &lt; 30 days.” An 8-month repo that just accelerated can stay `emerging`. A 2-week silent repo is `too_new`, not a gem.

### Contribution Opportunity

Replace 40% GFI surface with:

```
0.35 acceptance (external PR merge / review)
0.25 need (unassigned help-wanted, repeat user bugs — not missing CI files)
0.20 access (TTR, not file checklist)
0.20 direction fit
```

Caps: closed shop / silent author / trivial-title merge share ≥70% → Contribution ≤35–40. **Do not +8 for bus factor** unless `accepts_ext`. GFI-only is a farming warning. Entry copy: issue → repro → discuss → PR; never “add CONTRIBUTING.md.”

### Maintainer / community (GET-only)

Phase B add: issue `createdAt` + comment timestamps (TTR); GraphQL ~50 closed PRs with `authorAssociation`, `mergedAt`, reviews. NA if sample missing. Community reviewer uses TTR / talk / closed-shop risk. Contributor reviewer uses **will a PR land**. Trend does not eat contribution surface.

### Discovery (no new GitHub history API)

Ship **before** weight changes if we want a different 120:

1. Per-query quota / round-robin into the 120 (zero extra API).  
2. Kill `breakout sort:stars` and `llama.cpp` / `cuda` / `rocm` magnets.  
3. Add `stars:10..400 pushed:>45d` early-active family (not a 30-day created wall).  
4. `why_now` from search hit fields only (`createdAt`, `pushedAt`, S, F, query key). Lifetime S/age is a **label**, not Explosion.

---

## Reviewers + Chair (v2 copy, same engines until dimensions exist)

| Reviewer | Focus |
|---|---|
| Trend | growth, acceleration, emerging ecosystem, early signals |
| Community | real users, gap, maintainer TTR, external acceptance |
| Contributor | genuine opportunity, feasibility, entry difficulty, acceptance |

Chair must answer, in Chinese on the Board:

1. **If the user joined today, why is it worth it?**  
2. **If they should not join, what is the largest blocker?**

Two illusions to name explicitly:

- Hot ≠ early window (already successful).  
- Small ≠ blue ocean (may have no users).

Archetypes (not a score): `EARLY_GEM`, `FAST_RISER`, `COMMUNITY_GAP`, `NEW_ECOSYSTEM`, `MATURE_BUT_OPEN`, `HIGH_RISK`, `WATCH_ONLY`. Top 5 should not be five copies of the same llama.cpp binding.

---

## Current Top 20 vs what v2 is *designed* to do

**Before (v1 preview, 2026-08-24, no local v7):** attention list, 802–6477 stars, Momentum NA on every row.

**After (not yet run):** v2 cannot invent official Momentum on this corpus. A replay must keep official Top 5 = 0. Preview may rank by v2 Opportunity **dropping** Growth, using Entry Window + acceptance + maturity. Success criterion: a 70-star fast riser **can** beat a 2000-star mature repo in tests; the live 120 may still contain no such riser until discovery changes.

Do not claim a live before/after until `scripts/replay` exists.

---

## Tests (to land before score.py behavior change)

Keep all v1 pins (`test_worked_examples`, `test_cold_start`, `test_select`, `test_score` NA mix). Default `engine="v1"`.

New:

- `test_small_fast_riser_can_beat_large_mature_repo`
- `test_recent_active_repo_beats_old_stagnant_repo`
- `test_responsive_maintainer_beats_silent_maintainer`
- `test_high_acceptance_project_beats_closed_project`
- `test_trivial_pr_opportunity_does_not_score_high`
- `test_mature_repo_gets_entry_penalty`
- `test_low_star_stagnant_repo_is_not_promoted`
- `test_external_history_can_generate_momentum_before_v7` — **activity/external labeled; official v7 still None; no snapshot writes**
- Replay 120: in-memory only, snapshot count unchanged

Synthetic `starred_at` fixtures must be labeled `SYNTHETIC_FIXTURE` and must never `upsert_snapshot`.

---

## Known limitations (do not paper over)

1. **No third-party star timestamps in 2026** for a no-scope PAT. Day-1 “+520% stars / 30d” from GitHub is usually a lie.  
2. GH Archive WatchEvent is incomplete; P1 labeled backfill only, never mixed into `accel_ratio`.  
3. Fork/issue/PR windows are **not** star growth.  
4. `/stats/contributors` is unusable.  
5. PR acceptance sample costs GraphQL; if over budget, **NA**, not 0.5.  
6. Discovery still cannot see C or true star delta.  
7. Dual-write needs `scores.score_version` before persisting v2.  
8. P0 dogfood through 2026-08-31 UTC: **do not cut over official ranking this week.**

---

## What stays locked until an explicit RFC

- GET-only, no GitHub writes  
- `min_opportunity=55`, `min_explosion=35`  
- Official Top 5 requires **local** `v7`  
- NA ≠ 0; empty Top 5 is success  
- LLM cannot change numbers  
- Lifetime `S/age` is not Explosion  
- H1–H10  
- Reviews filter eligibility, do not nudge scores  

---

## Next phase (implementation order, after owner OK)

1. **Discovery v2** (quota, star strata, drop magnet queries, `why_now`) — does not change official scores.  
2. Schema `score_version`; dual-write v1+v2; default still v1.  
3. Counterexample tests against a v2 module (red until formulas land).  
4. Entry Window + lifecycle + maturity penalty.  
5. Contribution acceptance (PR sample) + maintainer TTR.  
6. Growth size curve; trivial-PR cap.  
7. Preview board reads v2; official report stays v1.  
8. Replay the 120 in-memory; compare lists.  
9. One dual-write dogfood week **after** local v7 exists.  
10. Cutover `score_version=v2` only with a written before/after.

---

## Decision the owner must make

**K5/K7 stay:** snapshots remain the only official star history; Top 5 still needs local `v7`.

**Reopen K2 (weights) and Early Entry `late()`** when v2 ships — written reason: v1 Early Entry + discovery invert “early window” on real 2026-08-24 data (shimmy 5807★ in provisional #3; zero shortlist rows &lt;300★).
