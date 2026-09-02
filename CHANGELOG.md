# Changelog

## [0.2.4] - 2026-09-02

Public Board SPA: anonymous `/api/portfolio` 401 no longer wipes a loaded daily board (the page no longer stays on “正在打开今日机会榜…”). systemd units set `PYTHONUNBUFFERED=1` so daily-run stage lines reach the journal.

## [0.2.3] - 2026-09-02

Public Board: anonymous read of the daily list; clone / mission / review still require login. Remote GitHub writes stay refused. `foreshadow run` prints stage progress. Local `foreshadow board` is unchanged.

## [0.2.2] - 2026-09-02

Recommended version. Fixes clean installation of v0.2.1.

### Fixed

- Hatch wheel duplicate package-data inclusion (`foreshadow/sql/*.sql` and other resources listed twice), which made `uv tool install git+…@v0.2.1` fail to build.
- Package metadata vs git tag mismatch (v0.2.1 was tagged while `pyproject.toml` still said 0.2.0).
- Distribution CI: build wheel, inspect resources, clean-install smoke.

### Unchanged

- Official scoring, Observation policy, remote-write safety.

## [0.2.1] - 2026-09-01

**Superseded by v0.2.2.** Tagged from 0.2.0 metadata. Clean `uv tool install` fails: Hatch adds `foreshadow/sql/001_init.sql` to the wheel twice. Do not install this tag.

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
