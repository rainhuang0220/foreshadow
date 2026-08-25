# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | P0 dogfood + P1 Board. Engine 2.0 **locks accepted**. Next code: **Discovery multi-pool (PR-D)**. Scoring still **v1**. |
| **Current Goal** | Dogfood through 2026-08-31 UTC. Do not merge to main. Do not change 55/35/local v7. Implement Discovery before `score.py`. |
| **Scoring version** | **v1**. v2 not implemented. |
| **Discovery version** | **v1** (12 queries, `stars:50..8000`, FIFO, star pre-rank). v2 plan: [`docs/opportunity-engine-v2-plan.md`](docs/opportunity-engine-v2-plan.md). |
| **Known API limits** | Third-party stargazer listing / `starred_at` admin-only (2026-06-30). Activity windows ≠ star growth. |
| **Workspace** | `/Users/rainhuang/Desktop/Foreshadow/.worktrees/p0-implementation` |
| **Canonical spec** | [`docs/p0-architecture.md`](docs/p0-architecture.md) |
| **Package** | `foreshadow-radar` `0.1.0` (local / branch only) |
| **Date** | 2026-08-24 |

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

## In Progress

- 7-day dogfood: `./scripts/dogfood-run.sh` (gitignored). Empty Top 5 is success.
- Next: PR-D Discovery multi-pool (not `score.py`).

## Blocked

- Merge to `main` blocked until post-run review on/after 2026-08-31 UTC.

## Next Action

Keep the worktree. Dogfood daily. Do **not** change `min_opportunity` / `min_explosion` or fabricate snapshots. Engine 2.0: implement **PR-D Discovery** next; `score.py` only after dual-write + counterexample tests.

## Known Bugs

See deferred minors in `.superpowers/sdd/2026-08-24-foreshadow-p0/progress.md`. Spec risks are listed in `docs/p0-architecture.md` § Risks.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md) and spec **Key Decisions K1–K18**.
