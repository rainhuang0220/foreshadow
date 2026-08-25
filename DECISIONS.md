# DECISIONS

Locked in the P0 spec (`docs/p0-architecture.md`). Reopen only with a written reason.

| ID | Decision | Why |
|---|---|---|
| K1 | Python 3.12 only in P0. CLI `foreshadow`, PyPI `foreshadow-radar`. **No Go. No dual-language stack.** | Owner lock 2026-08-24: scoring, history, optional LLM HTTP, pytest are the core. Go is a future single-binary/distribution migration only. |
| K2 | Opportunity = 20/15/15/20/15/10/5 mix from the product brief | Rejected a second 0–1 scoring system. |
| K3 | SQLite; `node_id` is identity; `full_name` is mutable | Rename / velocity / reviews need real constraints. |
| K4 | GraphQL-first GET-only `httpx` client | Split issue vs PR counts. No PyGithub. No mutations. |
| K5 | Our daily snapshots **are** star history | Stargazer listing restricted 2026-06-30; GH Archive WatchEvent degraded. |
| K6 | Cap 120 candidates first; Phase B ≤20 rankable watchlist then fill to 30; `enter` is Phase A only | Unbounded hydrate blows the 800/400 budget. |
| K7 | Top 5 requires defined `v7` | Lifetime `stars/age` must not pretend to be Explosion. Day-1 Top 5 is empty. |
| K8 | Direction fit is scored, not a hard gate | Exceptional override at ~60% fit. |
| K9 | Reviews filter eligibility; they do not nudge scores | Opportunity stays a pure function of evidence + config. |
| K10 | LLM off by default; narrative only | Cannot change numbers. |
| K11 | UTC calendar dates | Reproducible runs. |
| K12 | Token: `GITHUB_TOKEN` → `GH_TOKEN` → `gh auth token` | No-scope PAT. Never in TOML/SQLite/logs. |
| K13 | MIT, no telemetry, DB mode 0600 | Local-first. |
| K14 | REST 400 / GraphQL 800 points per run | Phase B on ~30 repos. |
| K15 | Do not send `fork:false`; H2 always vetoes forks from Top 5 | Not an official search qualifier. |
| K16 | GraphQL search primary; REST search fallback | Avoid the 30/min REST search bucket when possible. |
| K17 | Fake growth = H1–H10 + P1–P8 | Not a separate architecture veto table. |
| K18 | Stop contributor pagination early | Thresholds are at C=25/80/500, not page 5. |

| P1-B1 | Preview Audit Board is separate from official ranking | Official Top 5 still requires v7 + P0 thresholds. Preview labels N/A / PROVISIONAL and must not write snapshots. |
| P1-B2 | Three weighted reviewers + Chair, config `[board]` | Trend/Community/Contributor weights differ. Chair 40/20/20/20 with explicit override. Not a silent average. |
| P1-B3 | Reviewers are deterministic evidence engines | CLI cannot spawn Grok subagents. Parallel ThreadPool. LLM narrative remains optional and cannot change numbers. |

**Invariants:** no GitHub writes; max 5; no padding; no commit-count KPI; NA ≠ 0; empty Top 5 is success.

## Opportunity Engine 2.0 (accepted 2026-08-25)

Owner approved E2-0…E2-22. Production scoring remains **v1** until dual-write + counterexamples + explicit cutover.

Plan: [`docs/opportunity-engine-v2-plan.md`](docs/opportunity-engine-v2-plan.md). Audit: [`docs/opportunity-engine-v2-audit.md`](docs/opportunity-engine-v2-audit.md).

| ID | Decision |
|---|---|
| E2-0 | Target is Good Project × Early Window × Real Contribution. Not a high-star picker and not a low-star collector. |
| E2-1 | **Discovery before scoring.** Do not retune weights on the old 50–8000 FIFO funnel. |
| E2-2 | Three pools: A Early (recall 10–400★), B Emerging (100–3000★), C New ecosystem (no star-primary recall). Union → dedup → quality filter → reserved seats. Underfill is OK. |
| E2-3 | No `sort:stars`; Phase B `pre_rank_key` must not use raw stars as the main key. |
| E2-4 | Stars = attention / maturity proxy, not opportunity or quality. |
| E2-5 | Entry Window is continuous + soft penalty. No `star>X` reject, no `star<X` bonus. |
| E2-6 | **Contributor Gap ≠ Contributor Access.** High gap + low access must not score high. |
| E2-7 | Maintainer / community responsiveness is a real component (not 5% decoration). |
| E2-8 | Contribution = Impact × Need × Feasibility × Acceptance. GFI/typo/docs are not high opportunity. |
| E2-9 | Entry Strategy (issue → repro → discuss → PR, or do not enter). Never default “file a PR.” |
| E2-10 | Explosion (will it get big?) ≠ Opportunity (can I enter now?). Top 5 keyed on Opportunity. |
| E2-11 | Official Top 5 still needs genuine **local v7**. No lower 55/35, no lifetime-as-v7, no NA→0, no fake snapshots, no Preview-as-Official. |
| E2-12 | No third-party star timestamp history. Activity timestamps are allowed. |
| E2-13 | `forks_created_7d` / `issues_created_7d` / `prs_created_7d` / `commits_7d` **are not** `stars_growth_7d`. |
| E2-14 | Dual history: external activity + local snapshots; local v7 verifies, it is not first knowledge. |
| E2-15 | Rank Opportunity > Explosion > Stars (stars never primary). |
| E2-16 | Named counterexample tests must pass before v2 is “done.” |
| E2-17 | Dual-write: v1 official, v2 preview, until cutover. |
| E2-18 | Replay must ask whether 10–300★ **can** enter shortlist, not that smallness is required. |
| E2-19 | Order: Discovery → score_version → tests → Entry Window → Maintainer → Access → Contribution → Preview v2 → replay → compare. |
| E2-20 | Parallel research on independent slices; Grok 4.6. |
| E2-21 | Update PROJECT_STATE / DECISIONS / ROADMAP / TODO at each phase. |
| E2-22 | Success = exclude mature-closed “good projects” while keeping early, used, responsive, enterable repos — including when they have 73★ and beat 2800★. |

**K2 (v1 weights) and `late()`:** remain v1 until PR-S1. Reopen only behind `score_version=v2`. **K5/K7 unchanged.**

## PR-H Hydration (2026-08-25)

| ID | Decision |
|---|---|
| H1 | Phase B is **pool budget** (default A15/B10/C5), not global Top-30. Unused seats leftover-fill by `pre_rank`; they do not steal from a pool that still has hits. |
| H2 | Phase B / medium must not rank by raw stars. |
| H3 | Do not deep-hydrate all 120. Tiers: lightweight (all) / medium REST 30 / deep GraphQL 30. |
| H4 | PR acceptance empty sample → UNKNOWN, never 0. |
| H5 | Activity raw (`commits_7d`, …) is not `windows.v7` and is not scored this PR. |
| H6 | `data_completeness` is a quality label for Board / audit / routing. Not Opportunity. |
| H7 | Confidence and Opportunity stay independent. HIGH completeness + LOW confidence is legal. |
| H8 | PR-S1 / Entry Window stay suspended until Activity observability exists. |

## PR-A Activity Momentum (2026-08-25)

| ID | Decision |
|---|---|
| A1 | Activity Momentum is v2 Preview only. Never v1, never Official, never `windows.v7`. |
| A2 | UNKNOWN if `commits_30d` missing; known 0 is 0. Do not call it Growth. |
| A3 | When v7 is NA and AM is known, v2 fills the existing momentum slot. No new WEIGHT_KEYS. |
| A4 | `activity_concentration = c7 / max(c30, 1)` is explainable evidence, not acceleration. |
| A5 | Board shows 活跃度 + four raw counts + disclaimer 不代表 Star 增长. |
| A6 | Next after Activity: S1 Earlyness × Evidence, not more AM tuning. |

## S1 Preview (2026-08-26)

| ID | Decision |
|---|---|
| S1-1 | Earlyness is age + uncrowded **C** + access + living AM. Not 1/stars. |
| S1-2 | Evidence is a 100-point drop-NA mix. Stars ≤4 points. UNKNOWN omitted, not “bad”. |
| S1-3 | Opportunity Window = 75×√(E×Ev)+25×access. Gold needs both. Replaces v2 `entry_window` only. |
| S1-4 | Experimental pool (thin evidence + young/tiny) is ranked after main in v2 `pool_rank`. Not a star veto. |
| S1-5 | Stage is not a star table. Official v1 untouched. |

## S2 Community Access (2026-08-26)

| ID | Decision |
|---|---|
| S2-1 | Access Score is independent of Contributor Gap. |
| S2-2 | Empty PR sample → merge/review UNKNOWN, not 0. |
| S2-3 | GFI/help-wanted are onboarding signals inside Access, not contribution opportunity. |
