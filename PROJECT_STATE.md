# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | Project Intelligence |
| **Current Goal** | Board shows project summary + four scores and ranks by Expected Entry Value. Do not change Official Top 5 (v1 55/35/local v7). Empty Top 5 is success. Champion stays `formula-v1`. No PPO. |
| **Scoring version** | **Official v1** for Top 5. Board default sort is stored formula-v1 EEV (Potential + Entry Fit required; unknown Openness ranked conservatively). Preview **v2** dual-written; never Official. Champion **formula-v1** until explicit promotion. |
| **Discovery version** | v2 recall (14 queries, pools A/B/C). Seats: operator watchlist → system observations → fresh search (`fresh_discovery_floor=24`). |
| **Known API limits** | Third-party stargazer listing / `starred_at` admin-only. Daily snapshots are star history. Creator + openness live on HydrateB (30). Medium REST cap 15. Deep commits `max_pages=1`. No extra owner REST. No collaborators fetch. |
| **Workspace** | `/Users/rainhuang/Desktop/Foreshadow/.worktrees/project-intelligence` |
| **Canonical spec** | [`docs/p0-architecture.md`](docs/p0-architecture.md), [`docs/p1-observation.md`](docs/p1-observation.md), [`DECISIONS.md`](DECISIONS.md) PI-1…PI-15 |
| **Package** | `foreshadow-radar` `0.4.0` |
| **Date** | 2026-09-03 |

## Completed

- P0 merged to `main` as PR #1 (`4f4386e`) after 2026-08-31 UTC dogfood review.
- P1-A: system `observations` table, watchlist-first seating with a fresh-search floor, TTL 14 days, admission (opportunity ≥ 25, max 24/day, Official pins), longitudinal metrics, Day0–Day7 integration test that yields `v7=10` after Search misses.
- v0.3.0 / v0.3.1: Opportunity → Contribution Agent (OAuth, Entry Strategy, sandbox). Draft PR stays disabled.

## In Progress

- Project Intelligence + Learning (PI-1…PI-11). Board ranks by Expected Entry Value. Official Top 5 remains v1. Empty Top 5 is success.

## Blocked

- None for this phase. Do not write `selected_rank` from EEV. Do not fetch collaborators. Do not enable draft PR. Do not cut over Official to v2.

## Next Action

Ship Board summary + four scores + EEV sort from this worktree. Trainer is SQLite RO only; optional extra `[learn]`. Do not fabricate snapshots.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md) P0 K1–K18, Opportunity Engine E2-0…E2-22, and Project Intelligence PI-1…PI-11.
