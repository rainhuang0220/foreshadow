# Observation integrity audit

| Field | Value |
|---|---|
| **Document** | `006-observation-integrity-audit.md` |
| **Product** | Foreshadow (伏笔) |
| **PR** | PR3 — Observation integrity foundation for temporal evidence projection |
| **Date** | 2026-09-17 |
| **Status** | Accepted (Option B: small implementation) |
| **Base** | `main` at `da5129f` |

This is not a temporal intelligence design. It records what evidence already exists, where timestamps are honest or not, and the smallest change that makes future temporal views trustworthy.

## Executive Summary

Foreshadow already stores enough evidence to answer:

- What evidence do we have?
- When was it observed?
- What changed between observations?

The source of truth is existing SQLite rows: `snapshots` (daily counts + `captured_at`), `repos` (identity + first/last seen), `observations` (panel membership), and `observation_events` (persisted day-to-day deltas). Official 7-day velocity (`windows.v7`) is a separate dated lookup in `compute_windows` and must stay that way.

The requested v1 architecture pack is **not in this repository**:

- `docs/architecture/000-v1-architecture-decision.md` — absent
- `docs/architecture/005-v1-implementation-plan.md` — absent
- `docs/reviews/grok-v1-adversarial-review.md` — absent

Recent related work on `main` is Gate-2 / submission closure (`da5129f`, `f2411b3`). PR2 (Gate-2 contract pack) is open draft [#16](https://github.com/rainhuang0220/foreshadow/pull/16) on `cursor/gate2-contract-pack-f1df` and is **not merged**. There is no separate “PR1 Gate-1 recertification” pull request; Gate-1 coverage lives in `tests/test_two_gate_contribution.py`.

PR3 decision is **Option B**: a small read-path honesty fix. No schema migration.

Concrete gaps:

1. `load_series` dropped `captured_at`, so the observation read contract had no `observed_at`.
2. `star_delta(..., days=7)` compared first→last of the whole series but labeled the result as a 7-day window (`days: 7`, `window_complete` by observation count).
3. Board `factCells` branded that first→last delta as `7日增长`.

Those lies would poison any later temporal projection. Official `v7` scoring is already honest and is not changed.

## Subagent Findings

Five parallel investigations plus a coordinator pass. All five landed on **Option B, no migration**.

### A — Database / schema

**Source of truth:** `snapshots` keyed by `(repo_id, snapshot_date)`. Identity is `repos.id` / `repos.node_id`. `full_name` is mutable.

| Table | Role | Time fields |
|---|---|---|
| `repos` | Identity | `created_at`, `first_seen_at`, `last_seen_at` |
| `snapshots` | Daily evidence (star history) | `snapshot_date` (UTC calendar), `captured_at` (ISO run timestamp) |
| `observations` | System panel membership, not evidence | `added_on`, `last_observed_on`, `expires_on` (UTC dates) |
| `observation_events` | Persisted first-seen / deltas | `occurred_on` (UTC date) |
| `scores` / `intel_scores` | Derived interpretations | `scored_at`, `as_of_date` |
| `raw_payloads` | Schema only — never written | `fetched_at`, `etag`, `cache_key` |
| `candidates` | Per-run seating; deleted on same-day rerun | `discovery_source`, `hydrate_status` |

There is no `observed_at` column. `snapshots.captured_at` already is that timestamp. A new column would duplicate it. Schema migration is **not required**.

### B — Pipeline

- GraphQL cache is day-keyed. REST ETag bodies are process-lifetime; a reused client past UTC midnight could 304 yesterday’s REST body. Daily `foreshadow run` creates a new client. **Left out of PR3.**
- Same-day reruns upsert `(repo_id, snapshot_date)` and refresh `captured_at`. Last write wins.
- `captured_at` is `clock.now()` at discovery start, shared by every snapshot in that run.
- `observation_events` compare the latest prior snapshot by date, not a synthetic t−7 point, and skip NULL→value.
- Official `compute_windows` uses dated `t-N` lookup with slack. Do not unify that with Board first→last deltas.
- `first_seen` has three meanings (pipeline `repos.first_seen_at`, first snapshot event, GitHub `created_at`). Documented, not unified.
- `commits_30d` is one REST page, not a true 30-day census. **Out of PR3** (v2 Preview activity, not observation timestamps).

### C — Board / read path

- `/api/board` → `enrich_board_payload` mutates the JSON payload only.
- `/api/repo` → `repo_detail` is SELECT only.
- `build_board_from_db` raises if the `observations` row count changes.
- Observation views have no GitHub imports and no write SQL. GitHub writes are not reachable from these reads.
- Authenticated `/api/board` may still write **other** tables via `reconcile_user_safe`. GET `/api/entry` may persist stale `entry_analyses`. Neither touches `observations`.
- Residual: `load_series` is not truncated to `display_as_of_date`. If today’s snapshots exist while the Board shows yesterday’s Official run, the sparkline can include a later day. **Left out of PR3** — that is Board as-of plumbing, not the 7-day labeling bug.
- Static `--export-html` still skips `enrich_board_payload`. Accept.

### D — Tests

Existing coverage is strong for membership, TTL, NULL≠0 events, no interpolated sparklines, Official `v7`, Board as-of, and GET-only GitHub.

PR3 adds `tests/test_observation_integrity.py` for `observed_at`, actual date ranges, sparse spans, read-only views, and no GitHub write surface. Do not pull draft PR #16’s Gate-2 contract pack onto this branch.

### E — Adversarial maintainer

The title “foundation” is a trap. The data model already shipped. The real bug was naming: `star_delta(days=7)` ignored `days`, and the Board said `7日增长`.

Forbidden in this PR (and not done): `ObservationContract` / `EvidenceProjection`, `observed_at` column, new event tables, unifying Board growth with Official `v7`, interpolating missing days, backfill jobs, repo-wide ruff format of unrelated Gate-2 files.

`window_complete` must not mean “seven snapshot rows exist” or “a 7-day scoring window is satisfied.” This PR keeps the field and sets it **False**.

## Current Observation Model

```
GitHub GET
    → hydrate
    → snapshots (repo_id, snapshot_date) + captured_at
    → scores / intel_scores (derived, same day)
    → observation_events (optional persisted deltas)
    → observations (membership only)

Read path (no writes):
    snapshots.captured_at  →  observed_at
    first/last snapshot_date → calendar span
    consecutive counts       → what changed
```

Three questions, three existing answers:

| Question | Answer |
|---|---|
| What evidence? | `snapshots` counts + `features_json`; events are a derived index |
| When observed? | `snapshot_date` (UTC day) and `captured_at` (run timestamp) |
| What changed? | Consecutive snapshot diffs; stored in `observation_events` or recomputed |

Membership (`observations`) answers “are we still watching?” not “what did we see?”

## Identified Risks

| Risk | Severity | Disposition |
|---|---|---|
| Read path drops `captured_at` | Correctness | Fixed in this PR |
| `star_delta` claims `days=7` on any first→last span | Correctness | Fixed in this PR |
| Board chip `7日增长` on observation deltas | Honesty | Fixed in this PR |
| Same-day upsert overwrites the day’s snapshot | Accept | Daily identity is `(repo_id, date)` |
| `captured_at` is run-start, not per-repo fetch | Accept | Batch provenance |
| REST ETag cache not day-keyed | Accept | One run / UTC day |
| Timeline prefers stored events, else derives | Accept | Same facts |
| Official copy still says “近 7 日” for `windows.v7` | Not a bug | Dated 7-day lookup |
| Long-lived Board process after UTC midnight | Already fixed | v0.4.1 as-of |
| `load_series` not clipped to `display_as_of_date` | Residual | Later Board as-of work |
| `first_seen` name collision (3 clocks) | Residual | Document only |
| GET `/api/entry` may write `entry_analyses` | Residual | Not the observation panel |
| Repo-wide `ruff format --check` | Pre-existing | Red on `main` since two-gate |

## PR3 Decision

**Option B — small implementation PR.**

- **Not A:** existing *storage* is sufficient; existing *read contract* is not. Tests that require preserved `observed_at` and actual date ranges fail on unmodified `main`.
- **Not C:** `captured_at` already exists and is `NOT NULL`. A new column or event table would add maintenance without new facts.

Architecture lock (unchanged):

```
Existing evidence
        +
Reliable timestamps/provenance
        +
Read-time temporal projection
```

## Implementation Scope

In this PR:

- `load_series` keeps `captured_at` and exposes it as `observed_at`. Order is `snapshot_date`, `captured_at`, `id`.
- `observation_span` / `star_delta` report the real calendar span. The `days=` argument is ignored. `window_complete` stays False (not Official `v7`).
- `interpret_growth` no longer says a 7-day trend is pending when the series is simply too short to compare.
- Board `factCells` labels first→last as `观察增长` / `N日变化`, not `7日增长`.
- `card_layers.fact` includes `observed_at`, `first_date`, `last_date`, `calendar_days`.
- Contract tests in `tests/test_observation_integrity.py`.

Out of this PR (intentionally):

- Official `compute_windows` / `windows.v7`
- Observation admission, TTL, seating
- New tables, columns, entities, lifecycle, predictions
- GitHub write behavior / Gate-1 / Gate-2
- Interpolated charts
- Board as-of series clipping
- REST ETag day-scoping
- Reformatting unrelated files to green a pre-existing CI format check

## Non-goals

- Opportunity entities, belief tables, lifecycle engines
- Prediction models, AI memory, vector databases
- New intelligence storage
- Recommendation engines
- Changing Official Top 5 rules (v1 55/35/local v7)
- Assumed seven-day windows on observation comparisons
- Schema migrations
- Docs 000/005 (they were never committed; this audit is the PR3 record)

## STATUS

Implemented on `cursor/observation-integrity-8dc6`.

## CHANGED_FILES

- `docs/architecture/006-observation-integrity-audit.md` (this file)
- `src/foreshadow/observation_view.py`
- `src/foreshadow/board/webapp.py`
- `tests/test_observation_integrity.py`
- `tests/test_observation_view.py`

## TESTS

Focused (this environment, `pytest` 9.1.1):

- `tests/test_observation_integrity.py` — pass
- `tests/test_observation_view.py` — pass
- `tests/test_observation.py` — pass
- `tests/test_features.py`, `tests/test_ttl_timezone.py`, `tests/test_board_as_of.py`, `tests/test_client_get_only.py` — pass
- `tests/test_submission_closure.py` — pass
- `tests/test_two_gate_contribution.py` — Gate-1 / Gate-2 pass; `test_ripwire74_import_appears_on_board` fails on `main` already (tmp persistent-store path). Not introduced here.

Full suite: one pre-existing fail (ripwire import path), four `tests/test_packaging.py` errors because this image has no Hatch/uv build toolchain. Ruff check of the changed files passes. Repo-wide `ruff format --check` already fails on `main`.

## COMMITS

- `3b0088f` — `fix: keep observation timestamps and actual date ranges`
- `82a5e6c` — `test: lock observation span copy and record PR3 results`
