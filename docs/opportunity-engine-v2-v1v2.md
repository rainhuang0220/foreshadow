# v1 vs v2 Review

**Official scoring remains v1.** v2 is preview / comparison only. 55 / 35 / local v7 / `select.py` unchanged. Discovery was not modified in PR-V.

Date of corpus: **2026-08-24** dogfood (120 candidates, 1 snapshot day, official Top 5 = 0). This is the **v1 discovery** pool (FIFO 50–8000). PR-D’s new 10–400★ seats are **not** in this snapshot set.

Sort for comparison ranks: Opportunity DESC (NULL last), Explosion DESC, stars ASC, `node_id`. Not official Top 5.

---

## Answers (honest)

| Question | Result |
|---|---|
| 1. After Discovery, can a small project rank high? | **Fixtures: yes.** `seed/tinykit` 73★ active beats `giant/infra` 2800★/190C on v2 Opportunity. **This corpus: no.** 0 of 33 repos with &lt;300★ have `C` (Phase B was the old star pre-rank 30). Gap / Early / Contribution stay NA. Top 20 still 0 under 300★. |
| 2. Are mature projects lowered? | Softly. 2800★/3y/190C is not vetoed. `late()` cliffs are gone in v2 Entry Window. On this corpus, several 1k–spec/book repos fell 16–24 ranks. Shimmy 5807★ still #1 on v2 because C=1 and recent push look “open,” not because of a star bonus. |
| 3. Maintainer responsiveness? | **TTR = UNKNOWN** (no comment timestamps). Proxy is `maint_touch` + push freshness. v2 does **not** 0.4-fill missing touch. |
| 4. Access vs Gap? | v2 Gap no longer uses S/C as opportunity. High demand × low `maint_touch` is capped. Needs a later PR-S3 PR sample to be real Access. |
| 5. Contribution vs GFI? | v2 caps GFI, drops missing-file bonus and bus +8. Acceptance NA-drops when `maint_touch` is missing. |
| 6. Early opportunity vs popularity? | Fixture scorer: yes. **Hydrated corpus: not yet.** Phase B still only covers the old famous 30. Next dogfood run after PR-D is the real test. |

---

## Small active vs large mature (fixtures, complete Phase B)

These are the required counterexamples. They are **not** in the 2026-08-24 120. Tests: `test_small_active_beats_large_mature`, `test_small_stagnant_does_not_win`. No star&lt;X bonus; no hand-tuned expected floats.

| Case | Shape | v2 result |
|---|---|---|
| **A small active** | 73★, 41d, push 1d, C=5, real issue users, `maint_touch` 0.85 | High Opportunity; **beats** Case large |
| **B small stagnant** | 73★, 2y, push 220d, silent, no users | Opportunity **&lt; 40**; does **not** beat large; does not beat A |
| **Large mature** | 2800★, ~3y, C=190, slow `maint_touch` 0.05, still pushing | Not vetoed (soft maturity). Loses to A. Beats B. |

“External PR accepted” is **UNKNOWN** in hydrate (no merged-PR sample). Case A uses issue-sample external authors + maintainer comments, not fake merge history.

---

## Top 10 before / after (dogfood 2026-08-24)

| v1 | repo | ★ | Opp | v2 | repo | ★ | Opp |
|---:|---|---:|---:|---:|---|---:|---:|
| 1 | ngxson/wllama | 1171 | 55.9 | 1 | Michael-A-Kuykendall/shimmy | 5807 | 54.5 |
| 2 | withcatai/node-llama-cpp | 2163 | 52.4 | 2 | ovg-project/kvcached | 1141 | 51.5 |
| 3 | Michael-A-Kuykendall/shimmy | 5807 | 49.9 | 3 | ngxson/wllama | 1171 | 51.0 |
| 4 | ovg-project/kvcached | 1141 | 48.8 | 4 | withcatai/node-llama-cpp | 2163 | 49.9 |
| 5 | libriscv/libriscv | 1106 | 46.5 | 5 | libriscv/libriscv | 1106 | 48.7 |
| 6 | riscv-non-isa/riscv-elf-psabi-doc | 852 | 45.5 | 6 | AFLplusplus/LibAFL | 2622 | 46.3 |
| 7 | apple/embedding-atlas | 4917 | 44.4 | 7 | sybil-solutions/local-studio | 1737 | 45.1 |
| 8 | sybil-solutions/local-studio | 1737 | 43.6 | 8 | apple/embedding-atlas | 4917 | 44.5 |
| 9 | go-skynet/go-llama.cpp | 936 | 43.5 | 9 | mostlygeek/llama-swap | 5461 | 44.3 |
| 10 | mybigday/llama.rn | 1023 | 40.2 | 10 | rhaiscript/rhai | 5625 | 44.1 |

Official Top 5 is still **0** (no local v7). wllama is the only v1 Opportunity ≥ 55; Explosion still NA.

---

## Distributions (all 120)

### Stars

| band | n | pct |
|---|---:|---:|
| &lt;20 | 0 | 0.0 |
| 20–100 | 7 | 5.8 |
| 100–300 | 26 | 21.7 |
| 300–1k | 35 | 29.2 |
| 1k–3k | 30 | 25.0 |
| 3k+ | 22 | 18.3 |

### Age

| band | n | pct |
|---|---:|---:|
| &lt;30d | 2 | 1.7 |
| 30–90d | 5 | 4.2 |
| 90–180d | 15 | 12.5 |
| 180d–1y | 11 | 9.2 |
| 1–3y | 31 | 25.8 |
| 3y+ | 56 | 46.7 |

### Activity (last push, **not** star growth)

| band | n | pct |
|---|---:|---:|
| ≤7d | 72 | 60.0 |
| 8–30d | 32 | 26.7 |
| 31–90d | 16 | 13.3 |
| 90d+ | 0 | 0.0 |

### Contributors

| band | n | pct |
|---|---:|---:|
| UNKNOWN (Phase A) | 90 | 75.0 |
| 1 | 1 | 0.8 |
| 2–5 | 1 | 0.8 |
| 6–15 | 6 | 5.0 |
| 16–30 | 6 | 5.0 |
| 31–80 | 6 | 5.0 |
| 80+ | 10 | 8.3 |

**Every repo under 300★ has C=UNKNOWN.** Phase B = 30, all of them ≥300★.

### Maintainer responsiveness

True TTR: **UNKNOWN**.

`maint_touch` proxy: UNKNOWN 90 (75%), none 2, low 5, mid 16, high 7.

---

## Top 20 star mix

| band | v1 Top 20 | v2 Top 20 |
|---|---:|---:|
| &lt;300 | 0 | 0 |
| 300–1k | 3 | 3 |
| 1k–3k | 8 | 9 |
| 3k+ | 9 | 8 |

v2 Top 20 is **not** “more small projects” on this corpus. That is expected until a run hydrates PR-D’s Pool A.

---

## Rank deltas

Positive Δ = rose under v2 (`v1_rank − v2_rank`).

**Largest winners:** rust-mqtt 120★ +15, edge-net 228★ +15, crypto-bigint 306★ +15, picoserve 393★ +15, kobe 162★ +15.

**Largest losers:** R-KV 1209★ −24, ethercrab 436★ −22, xv6-riscv-book 943★ −22, riscv-debug-spec 527★ −22, **ser-no-std 71★ −20** (small does not get a free win).

---

## Known biases

- **`discovery_recency_bias`:** on *this* 2026-08-24 corpus, 60% last-push ≤7d (not the 100% of a raw PR-D search page). `sort:updated` + `first:25` still slices the head. **`pushed_at` ≠ growth.** Do not fill `windows.v7` from it. Do not change Discovery in PR-V.
- **Phase-B star hangover:** this run’s deep hydrate 30 were chosen by v1 `pre_rank` (raw stars). Small candidates never received C / issue sample, so v2 cannot score Entry/Access/Contribution on them.
- **Maintainer TTR:** UNKNOWN until comment `createdAt` exists.
- **Star growth:** UNKNOWN without local v7. `commits_7d` in a fixture is ignored and is not v7.
- **NA ≠ 0.** Missing C / v7 / touch are omitted from the mix.

---

## Dual-write

Each scored repo persists `score_version=v1` and `score_version=v2`. `selected_rank` is written **only** on v1. `score_compare` stores `v1_rank`, `v2_rank`, `rank_delta`. Never UPDATE a v1 row into v2.

---

## What not to do next

Do **not** cut over Official to v2. Do **not** lower 55/35. Do **not** fabricate snapshots.

A later PR-S1 still has work (Entry Window vs remaining `late_10x` effects on 1k–6k / C≥8). The next useful experiment is a **dogfood run on PR-D discovery** so Pool A 10–400★ actually get Phase B, then replay this comparison.
