# Opportunity Engine v2 — Hydration Expansion (PR-H)

**Official scoring remains v1.** This PR does not retune Opportunity. v2 stays Preview / comparison.

| Lock | This PR |
|---|---|
| `score.py` / `select.py` | unchanged |
| `min_opportunity` / `min_explosion` | 55 / 35 |
| local `v7` | required for Official; **still NA on 120/120** |
| Official Top 5 | **0** (`no_eligible_opportunities`) — correct |
| Discovery PR-D templates | unchanged |
| Activity fields | never written into `windows.v7` |
| `data_completeness` | quality label only; **not** mixed into Opportunity |
| PR-S1 / Entry Window / Activity scoring | **not started** |

Before: first 2026-08-25 PR-D dogfood ([`opportunity-engine-v2-real-experiment.md`](opportunity-engine-v2-real-experiment.md)), GraphQL 224 / REST **211**.  
After: same UTC date, `foreshadow run --force` with PR-H code, GraphQL 224 / REST **342**. Live GitHub numbers were refreshed, so star-band counts can move by 1 (76 → 75 under 300★). Discovery templates are the same 14 queries.

---

## Phase-B Audit

Written from current `phase_b_shortlist` / `_seat_deep_pools` / `_round_robin_query_key` / `pre_rank_key` / `medium_shortlist` **before treating hydrate as done**. The 08-25 first run is the “before” evidence.

### 1. How are the 30 Phase B seats produced?

1. Drop archived / disabled / empty / `not_found` (and forks when `exclude_forks`).
2. Reserve up to `max_watchlist_deep=20` for rankable watchlist actions (`watch` / `interested` / `investigate` / `later`). `enter` is Phase A only and does **not** consume a deep seat.
3. Remaining seats (`30 − watchlist`) are **pool-allocated**, not a global Top-N.
4. Inside each pool, candidates are ordered by `pre_rank_key` (no stars) then seated with `phase_b_per_query_floor` round-robin on `query_key`.
5. Unused pool seats (a pool that has fewer hits than its quota) are filled by leftover `pre_rank` among the unseated remainder so the cap stays 30. Leftover does **not** steal from a pool that still has unseated hits during seating.

This run: watchlist 0, so all 30 seats are search.

### 2. How many seats do A / B / C each get?

Config (not a hard-coded lottery):

```text
phase_b_pool_a = 15   # deep GraphQL issue/PR sample
phase_b_pool_b = 10
phase_b_pool_c = 5
phase_b_per_query_floor = 2
max_medium_hydrate = 30
medium_pool_a/b/c = 15/10/5
```

Chosen after the first 08-25 run (REST 211 / 400, GraphQL 224 / 800) so that:

- every pool has a real deep chance;
- we do **not** deep-hydrate all 120 (that would blow REST 400);
- medium REST (contributors + commits + releases) can cover another 30.

**After PR-H (this run): Phase B A15 / B10 / C5. Medium A15 / B10 / C5. Lightweight 60.**

### 3. Source-order bias?

Search still returns `sort:updated first:25` (PR-D). That is a **recall** bias (everything pushed today), not a Phase B seating sort.

Phase B no longer walks the candidate list in discovery append order. Seating is pool → query-key round-robin → leftover `pre_rank`. `node_id` is only the last `pre_rank` tie-break.

### 4. Stars bias?

`pre_rank_key` is `(direction_keyword_hit, recency_bucket, language_bonus, node_id)`. Raw `stargazerCount` is not in the key. Regression: `test_phase_b_does_not_rank_by_raw_stars` (70★ and 5000★, same activity/direction, both enter Phase B).

### 5. Hidden pre-ranking?

Yes, and it is explicit: direction hit, recency bucket (≤14d / ≤45d / else), language bonus, then `node_id`. Recency is currently **uniform** on this corpus (100% last_push = run date) because discovery uses `sort:updated`. That makes leftover fill a `node_id` lottery **inside unused seats only**. It is no longer the thing that decides whether Pool A exists in the 30.

### 6. Why did `A_help` enter 120 and then get 0 deep seats?

**Not a missing-query bug.** Before PR-H, Phase B was **global** `pre_rank` over 120. Recency was identical, so direction-keyword + `node_id` decided the 30. `A_help` is `help-wanted-issues:>0 (mcp OR agent OR llm)` — many hits do not carry direction-bag tokens in name/description/topics. Pool B (50 seats in the 120) did. Result: **8 `A_help` in the 120, 0 Phase B**.

**After:** Pool A has 15 deep seats of its own. Five A query keys share those 15 with floor 2 → **each A query, including `A_help`, received 3 deep + 3 medium + 2 lightweight**. 0 → 3 deep is the routing fix. The remaining 2/8 are budget (40 A − 15 deep − 15 medium = 10 leftover A = 2 per A query), not “Phase B cannot see A_help.”

Regression: `test_pool_a_help_can_reach_deep_hydration`.

### 7. Why were 59 / 76 &lt;300★ missing `features_json`?

Phase B was 30. Only 17 of those 30 were &lt;300★. The other 59 small repos stopped after Phase A GraphQL identity (stars/forks/pushed_at/topics/language). `features_json='{}'`. Contributors, issue sample, maintainer touch, contribution labels were never requested.

After PR-H: &lt;300★ is 75 (live star drift). Empty features **33 / 75**. The other 42 are Phase B (21) or medium (21).

### 8. Can Pool B crowd out A and C?

**Before, yes.** Global Top-30 + 50 B hits → Phase B **A12 / B15 / C3**. B was half of deep hydrate.

**After, no, by quota.** Phase B **A15 / B10 / C5**. B’s 50 candidates cannot take A’s 15 or C’s 5. Unused C seats can spill to leftover; they cannot steal A while A still has unseated hits.

---

## What shipped

Tiers (existing schema, extra optional keys, no rewrite of Opportunity):

| Tier | Who | What |
|---|---|---|
| **Lightweight** | all 120 | Phase A GraphQL: repo metadata, stars, forks, created_at, pushed_at, topics, language, open issue/PR counts |
| **Medium** | 30, pool-allocated | REST: contributors, commits since 30d (1 page), releases. `features_json.phase='M'` |
| **Deep (Phase B)** | 30, pool-allocated | GraphQL RepoB: open-issue sample, merged-PR sample, closed-issue titles, help labels + REST tree/workflows/community/contributors/commits/releases. `phase='B'` |

New raw fields (omitted key = missing, never implicit 0):

- PR acceptance: `pr_merged_sample_n`, `pr_external_merged_n`, `pr_accept_rate` (empty sample → `n=0`, rate **UNKNOWN** not 0)
- Maintainer raw: existing `maint_touch` + `maint_first_response_hours` (mean hours issue createdAt → first maintainer comment in the sample)
- Activity raw: `commits_7d`, `commits_30d`, `recent_contributors_7d`, `releases_30d`
- Placeholders (still UNKNOWN): `issues_created_7d/30d`, `prs_created_7d/30d` — GitHub `filterBy.since` is *updated*, not created; a search `issueCount` per window would cost extra GraphQL on every deep/medium repo. Not spent this PR.
- `data_completeness`: `high` / `medium` / `low`

Completeness formula (descriptive, not a score):

```text
bits = known(contributor_count) + known(issue_sample_n)
     + known(tree_names) + known(maint_touch or pr_merged_sample_n)
HIGH   if bits ≥ 3
MEDIUM if contributor_count or commits_30d or phase in {B, M}
LOW    otherwise
```

Board Preview list + drawer + static HTML:

```text
数据完整度：高 / 中 / 低
置信度：高 / 中 / 低
完整度低不是低分
```

Opportunity 80 + Confidence LOW is legal. This run: max Opportunity 44.9 v1 / 46.6 v2, confidence **low** on 120/120 because `v7` is NA.

---

## Before / after (2026-08-25, PR-D discovery)

### Phase B

| | Before PR-H | After PR-H |
|---|---:|---:|
| Phase B (deep) | 30 | 30 |
| Medium | 0 | **30** |
| Lightweight only (`features_json` empty) | 90 | **60** |
| Phase B Pool A / B / C | **12 / 15 / 3** | **15 / 10 / 5** |
| Medium Pool A / B / C | — | **15 / 10 / 5** |
| `A_help` in 120 | 8 | 8 |
| `A_help` deep | **0** | **3** |
| `A_help` medium | 0 | **3** |
| Pool A deep | 12 / 40 | **15 / 40** |
| Pool A high completeness | 12 (heuristic) | **15** |

### Star bands — deep access

| Band | In 120 before → after | Phase B before | Phase B after | Medium after |
|---|---:|---:|---:|---:|
| &lt;100★ | 57 → 55 | 12 (21%) | **15 (27%)** | 14 |
| 100–300★ | 19 → 20 | 5 (26%) | **6 (30%)** | 7 |
| 300–400★ | 5 → 5 | 4 (80%) | 2 (40%) | 1 |
| 1k+ | 21 → 21 | (in &gt;400: 9) | **3** | 3 |
| **&lt;300★** | 76 → 75 | **17 / 30** | **21 / 30** | 21 |

Discovery → Hydration Access: 10–100★ and 100–300★ now hold **36 / 75** of the 60 paid hydrations (deep+medium), not 17 deep and 59 empty.

### UNKNOWN rates (NULL/omitted, not zero)

Contributor / issue / maintainer / contribution / PR acceptance:

| Field | Slice | Before | After |
|---|---|---:|---:|
| **Contributor C** | all 120 | 75.0% | **50.0%** |
| | &lt;300★ | 77.6% | **44.0%** |
| | &lt;100★ | — | 47.3% |
| | 100–300★ | — | 35.0% |
| | 300–400★ | — | 40.0% |
| | 1k+ | — | 71.4% |
| | Pool A | 70.0% | **25.0%** |
| | Phase B | 0% | 0% |
| **Issue sample** | all 120 | 75.0% | 75.0% |
| | &lt;300★ | 77.6% | **72.0%** |
| | Pool A | 70.0% | 62.5% |
| | Phase B | 0% | 0% |
| **Maintainer `maint_touch`** | all 120 | 79.2% | 83.3% |
| | &lt;300★ | 84.2% | 82.7% |
| | Phase B | 16.7% | 33.3% (empty open-issue sample → NA, not 0) |
| **`maint_first_response_hours`** | all 120 | field missing | 90.0% UNKNOWN; **12 / 30** Phase B known (median ~19h) |
| **Contribution `help_n`** | all 120 | 75.0% | 75.0% |
| | &lt;300★ | 77.6% | 72.0% |
| **PR acceptance rate** | all 120 | **100%** (no field) | **80.8%** |
| | Phase B | 100% | **23.3%** (7 empty merged samples) |
| **`commits_7d`** | all 120 | 100% | **50.0%** (known on all 60 B+M) |
| **`releases_30d`** | all 120 | 100% | **50.0%** |
| **`issues_created_7d` / `prs_created_7d`** | all 120 | 100% | **100%** (not collected; see gaps) |

Issue / contribution UNKNOWN stay high **on the full 120** because those samples are deep-only. The drop that matters for this PR is **C and activity on small / Pool A**, plus **PR acceptance actually existing**.

### PR acceptance (new)

| | After |
|---|---|
| Phase B merged-PR field landed | 30 / 30 (`pr_merged_sample_n` known, including 0) |
| Empty sample (`n=0` → rate UNKNOWN, not 0) | 7 |
| Sample `n>0` (rate known) | **23** |
| Known rate = 0 (merged, all owner/member) | 7 |
| Known rate &gt; 0 (external merged) | **16** |
| Mean known external rate | **0.45** |
| Mean external merged count among `n>0` | 7.6 |

### Data completeness

| | Before (old heuristic) | After (formula above) |
|---|---:|---:|
| HIGH | 25 | **30** (all Phase B) |
| MEDIUM | 0 | **30** (all medium) |
| LOW | 95 | **60** (lightweight) |

| Band | HIGH | MEDIUM | LOW |
|---|---:|---:|---:|
| &lt;100★ | 15 | 14 | 26 |
| 100–300★ | 6 | 7 | 7 |
| 300–400★ | 2 | 1 | 2 |
| 1k+ | 3 | 3 | 15 |

HIGH completeness + LOW confidence is the common Phase B state: we know C / issues / PRs, and we still lack `v7`.

### API request cost

| | Cap | Before | After |
|---|---:|---:|---:|
| GraphQL points | 800 | 224 | **224** (same 14 searches + 120 Phase A + 30 RepoB; PR fields are extra *fields*, not extra operations) |
| REST | 400 | 211 | **342** |
| Headroom REST | | 189 | **58** |
| `hydrate_failed` | | 0 | 0 |
| `budget_abort` | | false | false |
| Wall time | | ~7 min | ~7 min (`14:00:48Z`–`14:07:47Z`) |

Cost model that forbade hydrating all 120 deep: this run already spends 342 REST on 30 deep + 30 medium. Another 60 at deep REST (contributors pages + commits + contents + workflows + community + releases) would exceed 400.

---

## `A_help` (required check)

| repo | ★ | tier | completeness | C | issue sample | PR accept | commits_7d |
|---|---:|---|---|---:|---:|---:|---:|
| eigenpal/docx-editor | 253 | **B** | high | 6 | 23 | 1.00 | 103 |
| alizahidraja/isnad | 36 | **B** | high | 5 | 21 | 0.05 | 124 |
| no-human-ai/no_human | 49 | **B** | high | 1 | 6 | UNKNOWN (`n=0`) | 157 |
| fazer-ai/agents | 67 | M | medium | 7 | — | — | 93 |
| llm-d/llm-d-router | 305 | M | medium | 100 | — | — | 66 |
| hushh-labs/hushh-research | 25 | M | medium | 61 | — | — | 100 |
| 3ndetz/unionclef | 19 | none | low | — | — | — | — |
| termio-sh/termio | 243 | none | low | — | — | — | — |

Even split across **all five** A queries (3 B / 3 M / 2 none). Routing, not a special-case hole.

---

## Success criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Discovery smalls can reach Phase B | **PASS.** Pool A 15/40 deep; &lt;300★ = 21/30 Phase B (was 17); `A_help` 0 → 3 deep |
| 2 | No hidden stars / source-order squeeze | **PASS.** Quotas + tests; B no longer takes 15 of 30 by volume |
| 3 | &lt;300★ key-feature UNKNOWN down | **PASS on C** (77.6% → 44%) and **PR** (100% → 81%). Issue/contribution still ~72% because samples are deep-only |
| 4 | PR acceptance real samples | **PASS.** 23 known rates; 16 with external merges; empty → UNKNOWN |
| 5 | Maintainer raw features | **PASS as raw.** `maint_first_response_hours` on 12/30 Phase B. Not a scoring engine |
| 6 | Activity raw for later scoring | **PASS on commits/releases/recent contributors.** `issues_created_*` / `prs_created_*` still UNKNOWN |
| 7 | Completeness explainable | **PASS.** HIGH/MEDIUM/LOW + Board copy. Not in Opportunity |
| 8 | Full tests | **PASS.** `uv run pytest` → **267 passed** |

Official Top 5 remains 0. Max Opportunity still below 55. Empty is success.

---

## Residual (do not solve in this PR)

### Recency bias — known issue

`last_pushed_at` is still 100% the run date. Do not treat push as growth. Keep until real Activity features are *scored* (not this PR).

### 1★ / youth on the Preview board

v2 comparison Top 10 still includes `TraceFold/tracefold` **2★**. That is Entry Window / scoring, not a hydrate miss (it now has a completeness label). **No star floor this PR.** Revisit only after the owner reads this report.

### Issue / PR *created* windows

Still UNKNOWN. Cheap GraphQL cannot answer “how many issues were *created* in 7d.” A search `issueCount` per repo per window is a future budget item, not S1.

### Medium has no issue/PR *sample*

By design (GraphQL cost). Snapshot `open_issues` / `open_prs` already exist on all 120 from Phase A. Contribution labels (`help_n`) remain deep-only.

### Maintainer scoring

Raw TTR hours only. Weight changes are PR-S2.

---

## What not to do next automatically

```text
Hydration  ← this PR, in tree
    ↓
re-read this experiment
    ↓
Activity scoring     if C/activity are enough to attack recency
    or
S1 Entry Window      if 1★/youth still dominate Preview *after* hydrate
    or
deeper issue/PR created counts   if UNKNOWN on contribution is the next blocker
```

Do **not** start PR-S1 in this change. Do not cut over Official to v2. Do not write activity into `windows.v7`.
