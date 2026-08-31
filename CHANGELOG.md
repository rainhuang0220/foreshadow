# Changelog

## [0.2.0] - 2026-09-01

Foreshadow Beta. Local daily radar: discover → observe → Board → enter locally. No automatic GitHub writes.

### Added

- Persistent observation: yesterday’s repos stay watched even if search misses them today.
- Daily Board (`foreshadow board`) on localhost: why, 开始进入, local prep.
- Entry Mission: shallow clone + `FORESHADOW.md` / `ISSUE_DRAFT.md`. Stops at `WAITING_USER_APPROVAL`. **尝试创建 PR** is refused.
- Product CLI: `foreshadow init`, `foreshadow schedule install`, `foreshadow doctor`, `foreshadow status`.

### Honest

- Empty Official Top 5 is success. Explosion needs t-7 data for that repo.
- Search is truncated by design: first 25 hits × 14 queries.
- 7-day deterministic integration: **VERIFIED**.
- Real 7-day soak: **IN PROGRESS**.

## [0.1.0] - 2026-08-24

Local GET-only GitHub opportunity radar CLI (`foreshadow-radar`). Daily snapshots; Top 5 requires ~7-day star velocity; empty Top 5 is valid. Commands: `run`, `report`, `show`, `review`, `watchlist`. Optional LLM narrative (`--llm`) cannot change scores.
