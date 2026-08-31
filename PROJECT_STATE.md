# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | P1 Persistent Observation Panel (P0 shipped on `main`) |
| **Current Goal** | Keep discovering new repos **and** keep hydrating a bounded panel so real `t-7` pairs can form. Do not change 55/35/local v7. Do not cut over Official to v2. |
| **Scoring version** | **Official v1**. Preview **v2** dual-written; never Official. |
| **Discovery version** | v2 recall (14 queries, pools A/B/C). Seats: operator watchlist → system observations → fresh search (`fresh_discovery_floor=24`). |
| **Known API limits** | Third-party stargazer listing / `starred_at` admin-only. Daily snapshots are star history. |
| **Workspace** | `/Users/rainhuang/Desktop/Foreshadow/.worktrees/p1-observation-panel` |
| **Canonical spec** | [`docs/p0-architecture.md`](docs/p0-architecture.md), [`docs/p1-observation.md`](docs/p1-observation.md) |
| **Package** | `foreshadow-radar` `0.1.0` |
| **Date** | 2026-08-31 |

## Completed

- P0 merged to `main` as PR #1 (`4f4386e`) after 2026-08-31 UTC dogfood review.
- P1-A: system `observations` table, watchlist-first seating with a fresh-search floor, TTL 14 days, admission (opportunity ≥ 25, max 24/day, Official pins), longitudinal metrics, Day0–Day7 integration test that yields `v7=10` after Search misses.

## In Progress

- P1 real-data dogfood of observation continuity (`dogfood/README.md`). Empty Top 5 remains success.

## Blocked

- None for P1-A implementation. Do not paginate GitHub search to 1000 in this phase.

## Next Action

Run `./scripts/dogfood-run.sh` daily from this worktree. Watch `retained_from_previous_day` and `v7_coverage_rate`. Do not fabricate snapshots.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md), P0 K1–K18, and [`docs/p1-observation.md`](docs/p1-observation.md).
