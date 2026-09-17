# Temporal evidence contract

| Field | Value |
|---|---|
| **Document** | `007-temporal-evidence-contract.md` |
| **Product** | Foreshadow (伏笔) |
| **PR** | PR4 — Temporal Evidence Contract |
| **Date** | 2026-09-17 |
| **Status** | Accepted (smallest honest-contract lock) |
| **Base** | `main` at `da5129f` |

This is not a temporal intelligence design. It locks three read-path contracts so later work cannot relabel first→last observation as a fixed window.

Requested v1 docs (`000-v1-architecture-decision.md`, `005-v1-implementation-plan.md`) are not in this repository. PR3 observation integrity is open draft [#17](https://github.com/rainhuang0220/foreshadow/pull/17) and is **not merged**. This PR stands alone on `main` and preserves the same honesty rule: report the span that was observed.

## What Foreshadow has

- Existing snapshot evidence (`snapshots.snapshot_date`, `snapshots.captured_at`)
- Accurate observation time (`captured_at` projected as `observed_at`)
- Read-time interpretation of those points

## What Foreshadow does not have

- A temporal intelligence engine
- A lifecycle / belief / opportunity state machine
- A prediction layer

## Contracts

### 1 — Observation comparisons expose real time spans

`star_delta` / `observation_span` compare the first dated point to the last dated point.

| Snapshots | `calendar_days` | `observed_points` | Forbidden label |
|---|---|---|---|
| 2026-09-01, 2026-09-15 | 14 | 2 | 7 day growth / `7日增长` |
| 2026-09-01, 2026-09-02, 2026-09-03 | 2 | 3 | complete 7-day window |
| one snapshot | `None` (pending) | 1 | 7-day trend formed / pending |
| no snapshots | `None` (pending) | 0 | any growth claim |

`days` and `observed_days` remain aliases for callers. They are not a requested window.

`window_complete` stays **False**. Observation first→last is not Official `v7`.

### 2 — Official windows stay separate

`v7` means exactly `compute_windows` / `windows.v7`: dated `t-7` lookup with slack.

Observation delta means first observed point → last observed point (raw count difference).

The same eight daily snapshots can produce `v7 = 10` and observation `delta = 70`. Those numbers answer different questions. Do not feed one into the other.

Board Official copy that says “近 7 日” for `windows.v7` is correct. Board observation chips must not reuse that label.

### 3 — Read-only temporal views stay read-only

`load_series`, `star_delta`, `observation_span`, `timeline_for`, `card_layers`, `enrich_board_payload`, and `repo_detail` must not:

- write SQLite
- reconcile missions or observations
- import or call GitHub mutation methods

`enrich_board_payload` may mutate the in-memory JSON payload. That is not a database write.

## Implementation

- `load_series` keeps `captured_at` and exposes `observed_at`.
- `observation_span` / `star_delta` report `calendar_days` and `observed_points`.
- Board `factCells` labels first→last as `观察增长` / `N日变化`, never `7日增长`.
- Tests in `tests/test_temporal_evidence_contract.py`.

Out of scope: schema migration, new tables/classes/services, Gate-1 / Gate-2 / submission flow, Official `compute_windows`, Board as-of series clipping, interpolated charts.

## Decisions

See `DECISIONS.md` TE-1, TE-2, TE-3.
