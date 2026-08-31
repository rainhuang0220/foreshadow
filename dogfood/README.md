# Dogfood

## P0 (done)

Seven calendar days of real GitHub data on `p0-implementation`, reviewed 2026-08-31 UTC. Empty Official Top 5 was success. Missing 2026-08-26 and 2026-08-29 were not backfilled. Search-only 120-seat days produced **0 v7** because 8/24 ∩ 8/31 = 0.

## P1 observation soak

Goal: prove the **system observation panel** keeps repos hydrating after Search misses them, until a real `t-7` snapshot pair exists.

### Rules

1. Do **not** lower `min_opportunity` / `min_explosion`.
2. Do **not** invent or backfill star history.
3. Empty Top 5 is still success.
4. Do **not** treat `search_truncated` as a P1 failure (known P2).
5. Success is **retention and v7 coverage > 0**, not a prettier board.

### How to run one day

From this worktree:

```bash
./scripts/dogfood-run.sh
```

`FORESHADOW_HOME` defaults to `dogfood/local/home`. Existing P0 sqlite migrates forward (`006_observations.sql`); do not `rm` the db.

### Daily Observation Health

Each run's JSON `source_health` and `dogfood/local/YYYY-MM-DD.meta.json` should record:

```text
observation_panel_size
user_watchlist_count
system_observed_count
fresh_discovery_count
retained_from_previous_day
daily_overlap_rate
v7_baseline_eligible_count
v7_available / v7_coverage_rate
explosion_available
observation_expired_count
official top5_count
```

### 7-day checklist

| Day | Expect |
|---|---|
| 1 | System promotions > 0 if any scored repo clears admit min; panel persists |
| 2 | `retained_from_previous_day` > 0 even if Search churns |
| 3–6 | Panel hydrates without requiring the same search hits |
| 7/8 | Some scored repos have a `t-7` snapshot; `v7_available` > 0 if those repos still sit in the panel |

Do not pick a coverage percentage target on the first soak.

### Anomalies (still)

- CLI exit ≠ 0
- Missing token / budget abort / hydrate systemic failure
- Crash leftover `status=running`/`failed`
- Scoring weights changed (forbidden)
