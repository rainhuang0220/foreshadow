# Opportunity Engine v2 — Implementation Plan

| Field | Value |
|---|---|
| **Status** | PR-D + PR-V + PR-H + PR-A + S1 Preview in tree. **No `score.py` change.** |
| **Date** | 2026-08-25 |
| **Official scoring** | **v1** until dual-write + counterexamples + owner cutover |
| **Charter** | [`opportunity-engine-v2-audit.md`](opportunity-engine-v2-audit.md) + DECISIONS E2-0…E2-22 |

Product: **Good Project × Early Window × Real Contribution Opportunity**. Not a high-star picker and not a low-star collector.

---

## Gap vs current code (confirmed)

| Lock | Current | Gap |
|---|---|---|
| E2-1 Discovery first | Search 12× `stars:50..8000`, FIFO 120 | PR-D |
| E2-2 Multi-pool | One band | PR-D: A/B/C |
| E2-3 No star pre-sort | `breakout sort:stars`; `pre_rank_key[..., stars]` | PR-D |
| E2-4 Stars = attention | `late()` / Gap S/C treat stock as opportunity | PR-S1+ |
| E2-5 Entry Window | Discrete `late` / `late_10x` cliffs (C≥8 or S≥2000 → 70–95; 70★/5C → ~62) | PR-S1 |
| E2-6 Gap ≠ Access | Only Gap; bus **+8** ContributionOpp | PR-S3/S4 |
| E2-7 Maintainer weight | 5%; `maint_touch` no timestamps; not on board dims | PR-S2 |
| E2-8 Contribution formula | GFI/`docs` labels + missing files | PR-S4 |
| E2-9 Entry Strategy | Report: “Add CONTRIBUTING.md” / GFI title | PR-S4 + board copy |
| E2-10/15 Opp > Exp > Stars | Official: Opp > Exp > **Contribution**; preview: lightweight / Chair | PR-S5 |
| E2-11 Official v7 | Already correct | **Do not touch** |
| E2-12/13 Activity ≠ stars | `commits_7d` / `releases_30d` in features; not `windows.v7` | PR-H landed; `issues_created_*` still UNKNOWN |
| E2-16 Counterexamples | None of the 10 names exist | PR-T before score behavior |
| E2-17 Dual-write | `UNIQUE(run_id, repo_id)` | PR-V |

Dogfood 2026-08-24: Preview Top 20 **0 rows &lt;300★**. Success for Discovery is **ability** of 10–400★ filtered hits to occupy reserved seats, not a quota of “5 small projects.”

---

## PR sequence (E2-19)

Do not skip. Do not validate scoring on old discovery.

```
PR-D   Discovery multi-pool + pre_rank without stars     ← in tree
PR-V   score_version dual-write (schema 003)             ← in tree; official still v1
PR-H   Hydration expansion (pool Phase B + medium + PR sample)
PR-A   Activity Momentum Preview (v2 only; not v7)
PR-S1  Earlyness × Evidence × Opportunity Window         ← in tree; Preview only
PR-T   Counterexample tests (red until formulas)
PR-S2  Maintainer / Community (TTR, activity)
PR-S3  Contributor Access (PR sample; separate from Gap)
PR-S4  Contribution Opportunity (I×N×F×A) + Entry Strategy copy
PR-S5  Preview ranks v2 Opportunity; official stays v1
PR-R   Replay 120 in-memory; compare v1 vs v2
```

`score.py` first behavior change is still **PR-S1**, only after the owner reads [`opportunity-engine-v2-hydration-report.md`](opportunity-engine-v2-hydration-report.md).

---

## PR-D — Discovery (this is the first code PR)

### Goal

Three recall pools → union → dedup → quality filter → cap 120 with **reserved seats**. Phase B 30 **must not** sort by raw stars. Magnets gone. Official scores unchanged.

### Pools (search recall only)

| Pool | Stars in query | Intent |
|---|---|---|
| **A Early** | `10..400` | Low scale, pushed recently, real text/topics |
| **B Emerging** | `100..3000` | Active / rising band; overlap with A allowed |
| **C New ecosystem** | **no `stars:`** | `created:>180d` + protocol/framework/benchmark/memory/MCP |

Star is a **recall qualifier**, not a score.

### Queries (14, AND/OR/NOT ≤ 5, **no `sort:stars`**, use `sort:updated`)

**Delete:** `local_llm` (llama.cpp/ollama), `ai_infra` (cuda/rocm/tensor rt), `runtime` as vllm magnet, unscoped `help_wanted`, `breakout` (`sort:stars`), merge `compiler_os` into systems.

**Pool A:** mcp, agent, memory, eval, help-wanted∩terms — all `stars:10..400 pushed:>45d sort:updated`. One `topic:` per query (GitHub `topic:X OR …` is a silent 0).

**Pool B:** mcp, agent, runtime (`gguf OR mlx OR candle` — **not** vllm/llama.cpp; no quoted “inference engine” — it zeros the query), systems (Rust embedded/riscv/osdev), help-wanted — `stars:100..3000`.

**Pool C:** mcp, agent framework / mcp server, memory, benchmark — `created:>180d pushed:>45d`, **no stars qualifier**. Unquoted tokens; `topic:benchmark` not a 27k `benchmark OR evals OR leaderboard` scrape.

Keep GET-only, sequential search spacing, `max_candidates=120`, no `fork:false`.

### Cap / quota

`DiscoverySettings`: `pool_a_quota=40`, `pool_b_quota=50`, `pool_c_quota=30`, `per_query_floor=6`.

1. Fetch all queries; tag `pool` + `query_key`.  
2. Dedup `node_id`: **A then B then C** (early recall wins the seat tag).  
3. `lightweight_keep` (below). **Underfill is success** — do not backfill stuffed wrappers to hit 40.  
4. Watchlist first inside 120; remaining seats split 40:50:30 **scaled**. Round-robin per query inside a pool.  
5. Do not steal unused A quota to dump extra B magnets while A still has kept hits.

### Lightweight filter (search-hit fields only)

Drop: fork/archived/empty/disabled; empty description **and** no topics; `is_keyword_stuffing`; `awesome-` / obvious wrapper names.

Pool A extra (OR, not AND-to-death): `fork_count≥1` **or** topics **or** came from `A_help`.

Pool C extra (宁缺毋滥): description length ≥ 20 **and** (topics or `fork_count≥1`) **and** (`stargazer_count≥1` or `fork_count≥1`). 0★/0 fork topic spam does not fill the C quota.

**Do not** require `language in cfg.languages`. **Do not** sort survivors by stars.

Not in this filter: contributor count, TTR, issue census (hydrate).

### `pre_rank_key` (Phase B 30)

Remove raw `stars` as a ranking key. Keep direction hit, recency bucket, lang bonus, `node_id` tie-break.

Equal direction+recency: **70★ must remain eligible** for Phase B; it must not lose **solely** because 5000★ sorts higher.

Optional: light `pushed` freshness already in recency_bucket. Do **not** add `int(pool=="A")` as “prefer all small repos.”

### Files

- `discover.py` — templates, `SearchHit.pool`, quota cap, `lightweight_keep`
- `config.py` / `examples/config.toml` — pool star bands + quotas
- `hydrate.py` — `pre_rank_key` only
- `tests/test_discover_merge.py`, `tests/test_pre_rank.py`, `tests/test_budget_caps.py` (query count)
- `docs/p0-architecture.md` search table + pre_rank snippet (spec lockstep)

**Do not change:** `score.py`, `select.py`, weights, 55/35, `directions.toml` bags (search can drop llama.cpp while Direction Fit still matches README).

### Tests that must pass in PR-D

- No `sort:stars` in any template  
- Magnet strings absent from templates: `llama.cpp`, `ollama`, `vllm`, `cuda`, `rocm`, `tensor rt`  
- Pool A interpolates `10..400`; Pool C has no `stars:`  
- Operator count ≤ 5  
- Cap round-robin: many B hits listed first cannot zero A  
- Dedup prefers pool A tag on overlap  
- Lightweight drops stuffing / empty desc  
- A underfill does not backfill junk  
- `pre_rank` does not order by raw stars  
- Existing: no `fork:false`; search_capped is not degraded; watchlist+search dedupe; enter ∉ Phase B  

FakeGitHub tests that assume **12** search pages must use `len(SEARCH_QUERY_TEMPLATES)`.

### Success for PR-D (not v2 scoring)

Cold-start 120 **can** contain filtered 10–400★ Pool A seats. Phase B is not a star sort. Official Top 5 still 0 without local v7.

---

## PR-V — Dual-write plumbing (in tree)

Official still v1. Preview `score_v2.py` + `score_compare`. Review: [`opportunity-engine-v2-v1v2.md`](opportunity-engine-v2-v1v2.md). Do not cut over.

## PR-V — Dual-write plumbing (spec)

`003_score_version.sql`: rebuild `scores` with `score_version` and `UNIQUE(run_id, repo_id, score_version)`. Copy existing rows as `v1`.

Update `ON CONFLICT` in `reviews.py` and `_insert_score` / `selected_rank` updates. Default config **v1**. Official `selected_rank` only on v1 until cutover. Never UPDATE a v1 row into v2.

---

## PR-T — Counterexample tests (red)

New `tests/test_score_v2_counterexamples.py` + `tests/fixtures/repos/v2/`. Default `score_repo` remains v1.

Names from E2-16. `external_activity_is_not_star_growth` and `external_history_cannot_fake_official_v7` can assert **v1** today (activity must not fill `windows.v7`). Scoring beat-tests xfail until PR-S1+.

Replay harness: in-memory 120, **snapshot count unchanged**.

---

## Later scoring PRs (summary only)

| PR | Change | Must not |
|---|---|---|
| S1 | Entry Window continuous mix + lifecycle soft penalty; kill `late`/`late_10x` | star&lt;X bonus, star&gt;X reject, 55/35 |
| S2 | Issue/PR TTR, 14d response; drop 0.4 NA-fill | Explosion using contribution surface |
| S3 | `contributor_access` from PR sample; high gap × low access ⇏ high Opportunity | Folding access into Gap |
| S4 | I×N×F×A; trivial/GFI cap; Entry Strategy copy | “file a PR” / Add CONTRIBUTING.md as default |
| S5 | Preview sort = v2 Opportunity (Growth dropped if NA); official `select_top` Opp>Exp>Stars asc on **v1** until cutover | Preview labeled official |

Hydrate activity windows (`commits_7d` from existing REST; GraphQL created-at lists) land as **`features_json.activity`**, sibling `evidence.growth_external`, **never** `windows.v7` (can piggyback S2 or a small PR-H).

---

## Replay question (E2-18)

After PR-D + a dogfood run: **does the 120 contain 10–300★ repos that passed the quality filter?** If still zero, Discovery failed (quota/magnets/pre_rank), not scoring.

After PR-S5: **can** a 73★ / 41d / responsive / accepted-external fixture beat a 2800★ / 3y / 190C / slow-review fixture on **Opportunity**? If not, v2 is not done (E2-16).

---

## Out of scope until owner cutover

Lowering 55/35; fake star %; GH Archive as `v7`; merging v2 into official Top 5; rewriting all of `score.py` in one PR.
