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

Five parallel investigations (schema, pipeline, board/read-path, tests, adversarial maintainer) plus a coordinator pass on `main`.

### A — Database / schema

**Source of truth:** `snapshots` keyed by `(repo_id, snapshot_date)`. Identity is `repos.id` / `repos.node_id`. `full_name` is mutable.

| Table | Role | Time fields |
|---|---|---|
| `repos` | Identity | `created_at`, `first_seen_at`, `last_seen_at` |
| `snapshots` | Daily evidence (star history) | `snapshot_date` (UTC calendar), `captured_at` (ISO run timestamp) |
| `observations` | System panel membership, not evidence | `added_on`, `last_observed_on`, `expires_on` (UTC dates) |
| `observation_events` | Persisted first-seen / deltas | `occurred_on` (UTC date) |
| `scores` / `intel_scores` | Derived interpretations | `scored_at`, `as_of_date` |
| `raw_payloads` | Fetch provenance | `fetched_at`, `etag`, `cache_key` |
| `candidates` | Per-run seating | `discovery_source`, `hydrate_status` |

There is no `observed_at` column. `snapshots.captured_at` already is that timestamp. `occurred_on` is the correct grain for daily events. A new timestamp column would duplicate `captured_at`.

Schema migration is **not required**.

### B — Pipeline

- GraphQL cache is day-keyed (`HttpCache.get_graphql`). REST ETag bodies are process-lifetime; production is one UTC day per `foreshadow run`. `FakeGitHub.begin_day` resets the 7-day soak cache.
- Same-day reruns upsert `(repo_id, snapshot_date)` and refresh `captured_at`. Last write wins. Intended.
- `captured_at` is `clock.now()` at discovery start, shared by every snapshot in that run. That is batch provenance, not per-repo fetch time. Acceptable for a daily radar.
- GitHub `createdAt` / `pushedAt` / `committedDate` are stored (`repos.created_at`, `snapshots.last_pushed_at`, `last_commit_at`).
- `observation_events` compare consecutive snapshots and skip NULL→value so missing counts are not 0.
- Official `compute_windows` uses dated `t-N` lookup with `window_slack_days`. That is the real 7-day window. Do not conflate it with Board first→last deltas.
- Stale-data risk that remains acceptable: REST ETag cache is not day-keyed inside one long-lived process. Observation reads do not call GitHub.

### C — Board / read path

- `/api/board` → `enrich_board_payload` (in-memory only).
- `/api/repo` → `repo_detail` (SELECT only).
- `build_board_from_db` raises if the `observations` row count changes.
- `observation_view` has no GitHub imports and no `INSERT`/`UPDATE`/`DELETE`.
- Temporal evidence can be displayed by projecting `snapshots` + `observation_events` at read time.
- Missing from the old payload: `observed_at`, actual `first_date`/`last_date`/`days`. The chip label `7日增长` assumed a window the read path did not compute.

### D — Tests

Existing coverage is strong for membership, TTL, NULL≠0 events, no interpolated sparklines, Official `v7`, Board as-of, and GET-only GitHub.

Gaps versus PR3:

- no `observed_at` preservation test
- no “actual date range, not assumed 7 days” contract
- no observation-view mutation / GitHub-write contract

Gate-1 / Gate-2 / submission tests stay as regression; PR2’s `tests/test_gate2_contract_pack.py` is not on `main`.

### E — Adversarial maintainer

Overbuild traps: `observed_at` column, belief/lifecycle tables, `ObservationContract` types, changing Official `v7`, new intelligence storage.

`star_delta(days=7)` was not “just copy.” The JSON field `days` and the Board chip were a false contract.

Smallest honest fix: project `captured_at` as `observed_at`, report the real calendar span, stop labeling first→last as 7-day. No migration.

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
- `observation_span` / `star_delta` report the real calendar span. The `days=` argument is ignored (call-site compatibility only).
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

- `tests/test_observation_integrity.py` — `observed_at` preserved; actual date ranges; read-only views; no GitHub write surface; Board chip not hardcoded to 7 days
- `tests/test_observation_view.py` — existing honesty tests plus 3-day span ≠ 7
- Regression: `tests/test_observation.py`, `tests/test_features.py`, `tests/test_two_gate_contribution.py`, `tests/test_submission_closure.py`, `tests/test_client_get_only.py`

## COMMITS

Recorded on the PR3 branch after this audit lands.
