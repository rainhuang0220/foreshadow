# Changelog

## [0.4.0] - 2026-09-03

Project Intelligence + Learning. The Board ranks by expected entry value; Official Top 5 stays v1.

### Added

- Board: extractive project summary, cached by default-branch SHA. Optional LLM narrative must not invent.
- Four scores: Potential, Creator Prior, Contributor Openness, Entry Fit.
- Expected Entry Value (EEV) = geometric mean of available core scores (need ≥2 of Potential / Openness / Entry Fit). NA omitted, never 0-fill.
- Homepage default sort is Expected Entry Value. Rank is ordinal, not a quality grade.
- Creator prior from HydrateB `owner.repositories` (top ~30). No followers, no sum-of-stars celebrity boost.
- Contributor Openness = Wilson lower bound of external closed PRs (merged + unmerged). Not Access Score. `n_ext<8` → NA.
- Stars enter Potential only as damped growth (`star_trust`). Stars are not a sort key.
- Schema 8: `model_runs`, `intel_scores`, `outcome_labels`. Labels 7/30/90; missing horizon is NULL. No JOIN at score time.
- Offline trainer: SQLite read-only, never GitHub. Optional sklearn HistGradientBoosting via extra `[learn]`.
- Shadow ε-greedy logs only. Champion remains `formula-v1` until explicit promotion.

### Unchanged

- Official Top 5 still v1 55/35/local v7. Empty Top 5 is success. EEV never writes `selected_rank`.
- Draft PR still disabled. No third-party GitHub writes.
- No PPO / RL.

## [0.3.1] - 2026-09-03

### Fixed

- Board CSRF origin check treated a `Host` header without a port as HTTP :80, so browser POSTs from `https://foreshadow.plainlist.space` (implied :443) were rejected. Honor `X-Forwarded-Proto` behind nginx.

## [0.3.0] - 2026-09-03

Opportunity → Contribution Agent. Not another radar patch.

### Added

- GitHub OAuth identity login, 30-day hashed server sessions, operator allowlist (`FORESHADOW_OPERATORS`). OAuth tokens are discarded after identifying the user.
- HTTPS vhost for `foreshadow.plainlist.space` (`contrib/nginx/foreshadow-https.conf`).
- Observation timeline, honest sparklines (no interpolated 7-day curves), clickable pool filters, fact / interpretation / decision layers.
- Entry Strategy: Plan A + B/C with evidence-backed issue/PR ids, contribution policy, cached `entry_analyses`.
- `ContributionExecutor` protocol, native Docker/local sandbox, quality gate. OpenHands and mini-SWE-agent are optional adapters, not hard deps.
- Real third-party golden path: Entry Strategy Plan A/B/C → mini-SWE in Docker → tests + QA → contribution package. Stops at `WAITING_USER_APPROVAL`. No GitHub remote write.
- Board: analyze entry, run sandbox job with live progress, show Files changed / Tests / QA / diff. Draft PR button is visible and disabled.
- Bounded concurrent HydrateANode (default 6).

### Unchanged

- Remote GitHub writes remain refused until a later dogfood of Contribution Ready.
- Official Top 5 still needs local v7. Empty Top 5 is success.

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
