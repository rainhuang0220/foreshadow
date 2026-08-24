# PROJECT_STATE

| Field | Value |
|---|---|
| **Product** | Foreshadow (伏笔) |
| **Current Phase** | P0 — implemented on branch `p0-implementation`; **not tagged / not on PyPI** |
| **Current Goal** | Use the tool for a week of real daily runs before starting P1 |
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

- None in code. Real-world daily use before P1.

## Blocked

- None.

## Next Action

Run `foreshadow run` daily for about a week. Do **not** tag a release or publish to PyPI unless the owner asks. Do not start P1 until then.

## Known Bugs

See deferred minors in `.superpowers/sdd/2026-08-24-foreshadow-p0/progress.md`. Spec risks are listed in `docs/p0-architecture.md` § Risks.

## Architecture Decisions

See [`DECISIONS.md`](DECISIONS.md) and spec **Key Decisions K1–K18**.
