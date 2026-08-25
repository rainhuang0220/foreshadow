# Opportunity Engine v2 — Real experiment (2026-08-25)

**Official scoring remains v1.** This run is Preview / comparison only.

| Lock | This run |
|---|---|
| `score.py` / `select.py` | unchanged |
| `min_opportunity` / `min_explosion` | 55 / 35 |
| local `v7` | required for Official; **NA on 120/120** |
| Official Top 5 | **0** (`no_eligible_opportunities`) — correct |
| Discovery templates | PR-D (not modified this experiment) |
| Fake snapshots / activity-as-v7 | none |

Run: `dogfood-run.sh` UTC **2026-08-25**, `FORESHADOW_HOME=dogfood/local/home`.  
`discovered 120 / hydrated 120 / scored 120 / selected 0`. Dual-write: **120 v1 + 120 v2** + 120 `score_compare` rows. Budget GraphQL 224/800, REST 211. `search_truncated` + `search_capped`. `hydrate_failed=0`.

Overlap with 2026-08-24 candidates: **0 names**. This is a new PR-D pool, not a rescore of the old FIFO 120.

---

## Discovery

Pool quotas filled exactly: **A 40 / B 50 / C 30**. Watchlist 0.

### Star distribution

| Band | All | Pool A | Pool B | Pool C |
|---|---:|---:|---:|---:|
| &lt;20 | 38 | 11 | 0 | 27 |
| 20–100 | 19 | 16 | 0 | 3 |
| 100–300 | 19 | 12 | 7 | 0 |
| 300–400 | 5 | 1 | 4 | 0 |
| 400–1k | 18 | 0 | 18 | 0 |
| 1k–3k | 21 | 0 | 21 | 0 |
| 3k+ | **0** | 0 | 0 | 0 |

Pool A (recall `10..400`): **&lt;100 = 27**, **100–300 = 12**, **300–400 = 1**. All 40 seats are in-band.

Stars overall: min 1, median ~127, max 2940. No 3k+ (Pool B ceiling 3000).

### Age (created_at vs 2026-08-25)

| Band | All | A | B | C |
|---|---:|---:|---:|---:|
| &lt;30d | 13 | 7 | 1 | 5 |
| 30–90d | 27 | 9 | 6 | 12 |
| 90–180d | 36 | 14 | 9 | 13 |
| 180d–1y | 15 | 4 | 11 | 0 |
| 1–3y | 20 | 4 | 16 | 0 |
| 3y+ | 9 | 2 | 7 | 0 |

Pool C is entirely &lt;180d (query constraint).

### Recent activity (last_pushed_at)

| Band | All | Phase B | v2 Top 20 |
|---|---:|---:|---:|
| **≤7d** | **120 (100%)** | **30 (100%)** | **20 (100%)** |
| 8–30d / 31–90d / 90d+ | 0 | 0 | 0 |

Every `last_pushed_at` is **2026-08-25** itself. This is `sort:updated` + `first:25`, not a clock bug.

**Success condition 1 (small into the 120): PASS.** 76/120 (63.3%) are &lt;300★ vs 33/120 (27.5%) on 08-24.

---

## Hydration

Phase B = 30 (`features_json.phase='B'`). The other 90 have `features_json='{}'`. That is the **deep-hydrate cap**, not REST failure. All 120 `hydrate_status=ok`.

### UNKNOWN rates (NULL/missing, not zero)

| Field | All 120 | stars &lt;300 (76) | Pool A (40) | Phase B (30) |
|---|---:|---:|---:|---:|
| **Contributors C** | **75.0%** | 77.6% | 70.0% | **0%** |
| **Maintainer `maint_touch`** | **79.2%** | 84.2% | 77.5% | 16.7% |
| **PR acceptance** | **100%** | 100% | 100% | 100% — **field does not exist** |
| **Issue sample** | **75.0%** | 77.6% | 70.0% | **0%** (5 of 30 sampled empty = 0, known) |
| **Contribution opp value** | **75.0%** | 77.6% | 70.0% | **0%** |

`commits_7d` / `issues_created_7d` / `prs_created_7d` / `release_activity` / TTR: **UNKNOWN** (not in schema).

### Did small repos enter Phase B?

| Star band | In 120 | Phase B | Phase B % |
|---|---:|---:|---:|
| **&lt;100** | 57 | **12** | 21% |
| **100–300** | 19 | **5** | 26% |
| **300–400** | 5 | **4** | 80% |
| &gt;400 | 39 | 9 | 23% |
| **All** | 120 | 30 | 25% |

Phase B star mix: **&lt;300 = 17/30 (56.7%)**. On 08-24, Phase B was 0 under 300★ (old star pre-rank).

Pool A: 12/40 Phase B. `search:A_help` **0/8** deep. Pool C: **3/30** Phase B.

### data_completeness

Heuristic: HIGH = C + issue sample + `maint_touch`; MEDIUM = C xor issue sample; LOW = else.

| | HIGH | MEDIUM | LOW |
|---|---:|---:|---:|
| All 120 | 25 | 0 | 95 |
| stars &lt;300 | 12 | 0 | 64 |
| Phase B | 25 | 0 | 5 |

MEDIUM is empty because C and issue sample are coupled (both only on Phase B). Five Phase B rows have empty issue sample → LOW.

**Answer: small repos were missing from 08-24 scoring because of discovery + star pre-rank. On 08-25 they are in the 120. Remaining blindness is hydrate Phase B skip (75% still have no C).**

---

## Ranking (comparison pool_rank, not Official)

Official `selected_rank`: **0** on v1 and v2. Max Opportunity **42.6 v1 / 44.4 v2**, both **&lt; 55**. Explosion **NA** on 120/120. Confidence **low** on 120/120 (v7 missing). Empty Official Top 5 is correct.

### v1 Top 10 vs v2 Top 10

| v1 | repo | ★ | Opp | v2 | repo | ★ | Opp |
|---:|---|---:|---:|---:|---|---:|---:|
| 1 | boxlite-ai/boxlite | 2276 | 42.6 | 1 | LIUTod/scream-code | **136** | 44.4 |
| 2 | caura-ai/caura | 449 | 40.8 | 2 | caura-ai/caura | 449 | 43.6 |
| 3 | maddada/Ghostex | 706 | 40.8 | 3 | bobmatnyc/trusty-tools | **18** | 43.5 |
| 4 | kody-w/rappterbook | 13 | 40.5 | 4 | mudler/vllm.cpp | 350 | 42.6 |
| 5 | LIUTod/scream-code | 136 | 37.7 | 5 | LunaticLegacy/angelus | **10** | 42.3 |
| 6 | mudler/vllm.cpp | 350 | 37.2 | 6 | boxlite-ai/boxlite | 2276 | 41.4 |
| 7 | mongodb-js/mongodb-mcp-server | 1106 | 36.8 | 7 | kody-w/rappterbook | 13 | 39.4 |
| 8 | rustsbi/rustsbi | 1306 | 36.5 | 8 | maddada/Ghostex | 706 | 39.1 |
| 9 | codecoradev/uteke | 235 | 34.5 | 9 | CherryHQ/stella | 48 | 38.4 |
| 10 | artokun/comfyui-mcp | 672 | 34.2 | 10 | Toloka/tolokaforge | 15 | 37.4 |

### Star mix of Top 20

| Band | v1 Top 20 | v2 Top 20 | All 120 |
|---|---:|---:|---:|
| &lt;100 | 6 | **9** | 57 |
| 100–300 | 3 | 3 | 19 |
| 300–1k | 8 | 5 | 23 |
| 1k–3k | 3 | 3 | 21 |
| 3k+ | 0 | 0 | 0 |
| **&lt;300** | **9** | **12** | **76** |

08-24 comparison Top 20 had **0 under 300★**. That question is closed for *this* corpus.

### Rank deltas (v1_rank − v2_rank; + = rose under v2)

**Winners:** angelus 10★ +14; swissdevjobs-cli 27★ +14; cc-switch-headless **1★** +12; trusty-tools 18★ +11; CarWatch 10★ +10; SSHub 120★ +8; scream-code 136★ +4 (to #1).

**Losers:** frona 198★ −19 (Phase A, C UNKNOWN — rank noise among ~8 Opportunity); scheme-rs 325★ −14; comfyui-mcp 672★ −13; qvac 540★ −12; rustsbi 1306★ −12.

---

## Three case groups

### A. Small and active

Definition used: stars &lt;300, last push ≤7d (all of them), and (C≥1 or issue sample or open_issues≥3).

Hydrated subset (Phase B, n=17): v2 **raised 11/17**. Mean Δ **+3.6**. Twelve of them sit in v2 Top 20.

| repo | ★ | C | v1→v2 | Δ | v2 Opp | note |
|---|---:|---:|---|---:|---:|---|
| LIUTod/scream-code | 136 | 2 | #5→#1 | +4 | 44.4 | real issues (3), maint_touch 1.0 |
| bobmatnyc/trusty-tools | 18 | 4 | #14→#3 | +11 | 43.5 | 508 open issues, maint_touch 0.52 |
| LunaticLegacy/angelus | 10 | 1 | #19→#5 | +14 | 42.3 | 29d old, sample n=1 |
| CherryHQ/stella | 48 | 8 | #11→#9 | +2 | 38.4 | 144 issues |
| Petyok/SSHub | 120 | 5 | #24→#16 | +8 | 35.4 | 16 issues |

**Hydrate hole (not scoring):** `geserdugarov/agent-orchestrator` 10★, 15 issues, C UNKNOWN, #41→#41, Opp ~9. Same for several Pool A names that never got Phase B.

**Scoring leak:** `Stupidoodle/swissdevjobs-cli` 27★ age 1d, 0 issues, early_entry 99 → v2 #14. `tiezbro/cc-switch-headless` 1★ created today → v2 #15.

**Success 2: PASS on hydrated small-actives. FAIL on 1★/0-issue youth.**

### B. Large, mature, still open

Only **two** 1k+ / age≥1y repos got Phase B (the rest of the 13 large-mature are C UNKNOWN).

| repo | ★ | age | C | v1→v2 | Δ | v2 Opp | veto |
|---|---:|---|---:|---|---:|---:|---|
| mongodb-js/mongodb-mcp-server | 1106 | 508d | 47 | #7→#12 | −5 | 36.8 | no |
| rustsbi/rustsbi | 1306 | 2237d | 53 | #8→#20 | −12 | 34.5 | no |

v2 kept both. No star hard-veto. Rank drop is other smalls rising + rustsbi youth term. `boxlite` 2276★ (age 261d, not 1y) stayed #6. H9 is license, not stars.

**Success 4: PASS** (soft, not veto). Sample is tiny because Phase B only captured 2 mature larges.

### C. Small and stagnant

**n by last_push &gt;30d = 0.** Discovery cannot produce a stagnant-by-push row when every hit was pushed today.

Closest: `Frisher1/ClaudeCode-Workflow-Lab` 117★, U30=0, 0 issues, still pushed today. v2 Opportunity **rose** 28.8→32.0; rank fell only because group A rose more. Entry window still ~97 because C=2 and push is today.

**Success 3: NOT TESTABLE on last_push. Weak FAIL on U30=0 + empty tracker still getting a high entry window.**

---

## Recency bias

```text
known_bias: discovery_recency_bias = true
share_last_push_le_7d = 100%
```

`last_pushed_at` **is not a valid activity discriminator inside this 120** — it is a search-sort echo.

Among the same-day-push pool:

| U30 (unique committers 30d, Phase B only) | n | share of 120 |
|---|---:|---:|
| NULL | 90 | 75% |
| 0 | 1 | 0.8% |
| ≥1 | 29 | 24% |

Phase B (measured): 29/30 have U30≥1. Median U30 = 2. So **when we actually hydrate commits, same-day push usually is real human activity**. The 90 Phase A rows have **no** commit census — push is the only signal.

`commit_count_7d`: UNKNOWN. `issues_created_7d` / `prs_created_7d`: UNKNOWN. Stock `open_issues` median 5.5 (all) / 12 (Phase B). Releases: UNKNOWN.

Push-only noise examples:

- ClaudeCode-Workflow-Lab: same-day push, **U30=0**, empty tracker.
- `anywhere-labs/Agents-Anywhere`: pushed today, default-branch commit **15d** stale, C UNKNOWN.
- 1★ Pool C seedlings pushed in the same UTC hour as 2k★ B_runtime hits.

**Do not treat recent push as high potential.** Do not write it into `windows.v7`.

---

## C noise

| Stage | n | /30 |
|---|---:|---:|
| C candidates | 30 | 100% |
| Hydrated ok | 30 | 100% |
| Scored v2 | 30 | 100% |
| v2 Top 20 | **1** | 3.3% (`cc-switch-headless` 1★) |
| v2 Opp ≥ 55 | **0** | 0% |
| v2 Opp ≥ 40 | **0** | 0% |
| v2 Opp ≥ 20 | 3 | 10% |

Stars: 1★ = 11 (36.7%); &lt;10 = 27 (90%); max 42. Median 3.

| Rate | Value |
|---|---|
| **C_noise_rate** (≤1★ and C unknown/≤1 and no issue sample) | **10/30 = 33.3%** |
| **C_keep_rate** (scored / candidates) | **30/30 = 100%** |
| **C_high_opportunity_rate** (Opp ≥ 55) | **0/30 = 0%** |

Do **not** delete Pool C from this. Survival into Top 20 is 1 noisy 1★ that Phase B happened to pick. 27/30 C never got C/issues. Quality filter vs Phase B lottery is the next decision, not this PR.

Real-looking C seedlings (not in Top 20): `EndoTheDev/OMeter` 25★ C=5; `rinaldofesta/tessera` 4★ C=3 (v2 #24).

---

## Confidence vs completeness

**Do not confuse LOW SCORE with LOW CONFIDENCE.**

This run: **every** row is `confidence=low` because official `v7` / Momentum is NA. HIGH completeness (25 Phase B with touch) still says LOW. Completeness is **not yet a separate published band**.

What *does* work as designed:

- Missing C → `early_entry` / `gap` / `contribution_opp` **NA, not 0**. Mix drops those terms (Opportunity ceiling ~8–10 from direction+maintainer freshness only).
- Example **high evidence, modest Opportunity:** scream-code Opp 44.4, completeness HIGH, confidence still LOW only because v7. That 44 is not “punished UNKNOWN”; it is missing Growth.
- Example **low Opportunity, LOW completeness:** 1024pix/pix 281★, 5 issues, C UNKNOWN, Opp 5.0, rank ~112. That is omitted terms, **not** a confident “this is a bad project.”

Gap: confidence cannot yet say “HIGH completeness but early window is poor.” Both A (good small) and Phase-A unknown look `low`.

**Success 5: PARTIAL.** NA≠0 holds. Confidence does not yet encode data completeness separately from v7.

---

## Success conditions

| # | Criterion | Result |
|---|---|---|
| 1 | Real small projects enter Phase B | **PASS** — 17/30 Phase B are &lt;300★ (12 &lt;100★). 08-24 was 0. |
| 2 | v2 can raise a real small project | **PASS with caveats** — scream-code / trusty-tools / angelus / SSHub. Also raised 1★ and 1-day CLIs. |
| 3 | v2 does not auto-reward stagnant junk | **NOT TESTABLE** on push-age (0 stagnant). Weak on U30=0 still getting early_entry ~97. |
| 4 | Mature not hard-vetoed for stars | **PASS** — mongodb-mcp, rustsbi, boxlite kept. |
| 5 | UNKNOWN lowers confidence, not silent 0 | **PARTIAL** — NA drop works; all confidence LOW from v7, completeness not split. |
| 6 | Identify PR-D recency bias | **PASS** — 100% last_push same UTC day. `known_bias.discovery_recency_bias=true`. |

---

## Conclusions — which layer is wrong

| Symptom | Layer |
|---|---|
| 10–400★ now in the 120; 0 overlap with 08-24 llama/ROCm set | **Discovery working** |
| 100% same-day `pushedAt`; no stagnant contrast class | **Discovery recency** (`sort:updated` + first:25). Do not retune Entry Window to compensate. Next: Activity feature / second sort, **not** S1. |
| 75% C / issue sample / contribution UNKNOWN | **Hydrate** — Phase B still 30. Pre-rank is no longer stars (small *can* get in) but 59/76 small still skip deep. `A_help` 0/8. |
| PR acceptance 100% UNKNOWN | **Hydrate / feature availability** — not fetched. |
| Hydrated small-actives rise under v2 | **Scoring (preview) doing its job** |
| 1★ / 0d / 0-issue in v2 Top 20 (`cc-switch-headless`, `swissdevjobs-cli`) | **Scoring** — Entry Window treats C=1 + today-push as open. Do not “fix” by adding a star floor. Need activity/completeness in the window, or a quality gate **after** hydrate. |
| Official Top 5 empty | **Scoring Official correct** (no v7). |
| Pool C 33% 1★ noise, 0 high Opportunity, 1 noise in Top 20 | **Discovery recall + hydrate lottery**. Record rates; do not delete C this round. |

**Primary remaining problem is still hydration depth + recency-shaped discovery, not “Entry Window weights.”**

Recommended next fork (owner decide, one problem per PR):

1. **If the goal is to score the small repos we already found:** raise Phase B information (more than 30, or reserve seats for Pool A), still GET-only. That is hydrate, not S1.
2. **If the goal is a stagnant contrast class / real activity:** Activity features (`commits_7d` from existing REST commits, issue/PR created-at). Never write them into `v7`. Separate from S1.
3. **If the goal is to stop 1★ youth topping Preview:** a post-hydrate quality/completeness term — still not a star&lt;X bonus. Could be S1-adjacent but should not mix with hydrate work.
4. **Do not start PR-S1** until (1) or (2) lands, or the owner explicitly wants Entry Window retune on this recency-collapsed pool.

Official stays v1 / 55 / 35 / local v7. Preview stays preview.
