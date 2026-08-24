# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | P0 — implemented on branch `p0-implementation`; **not tagged / not on PyPI** |
| **Current Goal** | 7-day real dogfood on `p0-implementation` (2026-08-24 → 2026-08-31 UTC). **Do not merge to main** until post-run review. Do not change scoring thresholds. |
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

## In Progress

- 7-day dogfood: `./scripts/dogfood-run.sh` (logs in `dogfood/local/`, gitignored). Empty Top 5 is success.

## Blocked

- Merge to `main` blocked until post-run review on/after 2026-08-31 UTC.

## Next Action

Keep the worktree. Run the dogfood script daily. Do **not** change `min_opportunity` / `min_explosion`. Do **not** fabricate snapshots. After 7 calendar days, review `dogfood/local/JOURNAL.md` and decide merge.

## Known Bugs

See deferred minors in `.superpowers/sdd/2026-08-24-foreshadow-p0/progress.md`. Spec risks are listed in `docs/p0-architecture.md` § Risks.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md) and spec **Key Decisions K1–K18**.
