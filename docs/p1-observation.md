# P1 Persistent Observation Panel

P0 shipped on `main`. Official scoring is unchanged: v1, `min_opportunity=55`, `min_explosion=35`, local `v7` at `t-7` ± 1 day.

P0 dogfood showed search-only 120-seat days churn so hard that **8/24 ∩ 8/31 = 0**, so `v7` stayed NA even when real repos grew. That was not a scoring bug.

## Split

| Stage | Question |
|---|---|
| **Discovery** | What appeared in today's GitHub search? |
| **Observation** | What have we been watching, including repos search missed today? |
| **Scoring** | Is it worth entering *now*? (Official v1) |

Search discovers. Observation collects longitudinal evidence. Scoring still requires real snapshots — never fabricated history.

## Two memberships

**User watchlist** (existing `reviews` for the CLI operator): watch / interested / investigate / enter. Highest seat priority. System TTL does **not** evict it. Board user stances stay per-user and do not become Official operator watchlist.

**System observation** (table `observations`): the pipeline promotes a capped slice of scored repos that are not yet Official-eligible but worth another look. This is `observe`, not `recommend`, and never a user `interested` row.

## Seats (default 120)

1. Operator watchlist (may consume the full cap; existing truncation).
2. Active system observations, oldest `added_on` then `node_id`, leaving `fresh_discovery_floor` (24) seats.
3. Fresh search fills the remainder with existing A/B/C quotas.

Panel cap for system rows = `max_candidates - fresh_discovery_floor` (96). Admission: not vetoed, opportunity ≥ `observation_admit_min` (25), at most `observation_admit_max` (24) new rows per day, plus any Official Top 5 pins (`previous_official`). TTL is **14 days from `added_on`**, not sliding: `expires_on = added_on + 14` calendar days, live while `today <= expires_on` (inclusive of the expiry date), gone the UTC day after. Last observation does not extend membership. Expired rows stop seating.

Preview / Board **read** the table. They do not insert, expire, or refresh it.

## Metrics

`source_health` now includes panel size, watch vs system counts, fresh discovery, previous-day retention and overlap, `v7_available`, `v7_coverage_rate`, t-7 baseline eligible count, explosion available, expired-this-run.

`snapshot_days` (distinct calendar dates globally) remains, but coverage is the longitudinal KPI.

## Dogfood

See [`../dogfood/README.md`](../dogfood/README.md). Next soak measures retention and `v7` coverage, not prettier Top 5. Do not backfill stars.
