# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | P0 dogfood + P1 Board. Engine 2.0 **PR-D + PR-V + PR-H landed**. Official scoring still **v1**. Next: owner reads the hydration report, then choose Activity vs S1. Do **not** start S1 in this step. |
| **Current Goal** | Dogfood through 2026-08-31 UTC. Do not merge to main. Do not change 55/35/local v7. Do not cut over Official to v2. |
| **Scoring version** | **Official v1**. Preview **v2** dual-written; never Official. |
| **Discovery version** | **v2 recall** (14 queries, pools A/B/C, exposure quotas, no star pre-rank). Official scoring still v1. Plan: [`docs/opportunity-engine-v2-plan.md`](docs/opportunity-engine-v2-plan.md). |
| **Known API limits** | Third-party stargazer listing / `starred_at` admin-only (2026-06-30). Activity windows ≠ star growth. |
| **Workspace** | `/Users/rainhuang/Desktop/Foreshadow/.worktrees/p0-implementation` |
| **Canonical spec** | [`docs/p0-architecture.md`](docs/p0-architecture.md) |
| **Package** | `foreshadow-radar` `0.1.0` (local / branch only) |
| **Date** | 2026-08-25 |

## Completed

- Read empty workspace (no files, no git history).
- Parallel research: GitHub API inventory, computable scoring metrics, P0 architecture patterns.
- Critical 2026 constraint locked: third-party stargazer listing is admin/collaborator-only (changelog 2026-06-30). **Daily snapshots are star history.**
- P0 Architecture & Technical Specification written and reviewed to **0 open issues** (5 review rounds).
- Spec copied to `docs/p0-architecture.md`.
- Owner locked: Python 3.12 only (no Go in P0, no dual stack); remote `rainhuang0220/foreshadow`; token `GITHUB_TOKEN` → `GH_TOKEN` → `gh auth token`.
- Implementation plan: [`docs/superpowers/plans/2026-08-24-foreshadow-p0.md`](docs/superpowers/plans/2026-08-24-foreshadow-p0.md) (Tasks 1–11).
- Tasks 1–11 on `p0-implementation`: skeleton through 0.1.0 hygiene (GET-only client, scores, Top 5 / empty OK, v7 required, human review, optional LLM narrative).
- P1 Preview Audit Board: 120→20→3 reviewers→10→Chair, HTML Daily Board, official Top 5 still 0 without v7. Preview does not insert snapshots.
- P1 round 2: localhost Chinese list+drawer Board, register/login, per-user reviews. P0 thresholds unchanged.
- Opportunity Engine 2.0 research + audit. **No formula changes.**
- Owner accepted E2-0…E2-22. Implementation plan: `docs/opportunity-engine-v2-plan.md`.
- **PR-D Discovery:** pools A/B/C, no `sort:stars`, no magnet keywords, `pre_rank_key` without raw stars, quota exposure not FIFO fill. `score.py` / `select.py` untouched.
- **PR-V dual-write:** `score_version` v1+v2, `score_compare` rank deltas, preview `score_v2.py`. Official Top 5 still v1. Review: `docs/opportunity-engine-v2-v1v2.md`.
- **PR-H Hydration Expansion:** pool-allocated Phase B (A15/B10/C5) + medium REST 30; PR acceptance sample; maintainer TTR hours; activity raw (`commits_7d` etc.) **not** in `windows.v7`; `data_completeness` HIGH/MEDIUM/LOW for Board/audit only. Report: [`docs/opportunity-engine-v2-hydration-report.md`](docs/opportunity-engine-v2-hydration-report.md).

## In Progress

- 7-day dogfood: `./scripts/dogfood-run.sh` (gitignored). Empty Top 5 is success.
- Next: owner review of the PR-H hydration report. Do **not** start PR-S1 / Entry Window / Activity *scoring* until that read. Do not cut over Official.

## Blocked

- Merge to `main` blocked until post-run review on/after 2026-08-31 UTC.

## Next Action

Keep the worktree. Dogfood daily. Do **not** change `min_opportunity` / `min_explosion` or fabricate snapshots. Engine 2.0: **PR-D, PR-V, and PR-H are in tree.** Official remains v1. After hydration: if 1★ youth still dominate Preview, then S1; if ranks look reasonable, then Activity scoring. Owner decides.

## Known Bugs

See deferred minors in `.superpowers/sdd/2026-08-24-foreshadow-p0/progress.md`. Spec risks are listed in `docs/p0-architecture.md` § Risks.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md) and spec **Key Decisions K1–K18**.
