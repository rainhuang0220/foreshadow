# Changelog

## [0.6.1] - 2026-09-11

Live Gate-2 readiness. One human Submit click may create exactly one PR.

### Changed

- `READY_FOR_HUMAN_SUBMIT` is computed, not an alias for `WAITING_USER_APPROVAL`. The Board shows it only when the exact approved commit is available, the dedicated write credential can perform the allowed operations, the approval snapshot still matches the package, and upstream still equals the validated base.
- `ApprovedGitHubPort` performs the three allowed writes: fork if needed, exact non-force branch push, and PR create. Lost-response recovery reuses the existing fork or PR.
- Schema 10: one durable submission row per approval snapshot.
- Historical `MERGED` / non-queueable missions stay out of the actionable review queue.

### Safety

- Submit remains user-scoped, snapshot-matched, and maintainer-output gated.
- Force-push, comments, review, and merge stay denied.
- `FORESHADOW_WRITE_TOKEN` is required before READY. Radar `GITHUB_TOKEN` stays GET-only. OAuth stays identity-only.
- This release does not submit ripwire #74.

## [0.6.0] - 2026-09-11

Two human gates. Mission identity is `mission_id` + issue, never “latest row for this repo.”

### Added

- Gate 1 **进入** authorizes local work on one issue. Local phases (investigate → package) do not stop for extra approval.
- Gate 2 **提交到 GitHub** authorizes only the immutable approval snapshot on screen (`approval_digest`).
- Approval snapshots hash patch, base, title, body, and the remote action plan. Any change invalidates approval.
- One-shot submission engine (fork / push branch / create one PR) with GET-only preflight and idempotent retries. Comments, review, merge, and force-push stay denied.
- Outcome reconciliation binds the exact submitted PR to `mission_id`. A merged PR moves the mission to `MERGED` (the #1551 stale-state class).
- Import path for a validated contribution store. ripwire #74 is the golden review package.

### Changed

- Board review queue is one card per mission, not one card per repository.
- `WAITING_USER_APPROVAL` renders as `READY_FOR_HUMAN_SUBMIT`.
- Schema 9: `contribution_jobs.mission_id`, `approval_snapshots`, `submissions`.
- Radar `GITHUB_TOKEN` stays GET-only. Gate 2 writes require a separate `FORESHADOW_WRITE_TOKEN`.

### Safety

- Gate 2 refuses drafts that fail maintainer-output leak / privacy / AI-attribution checks.
- Same-repo Board actions pass `mission_id`. Gate 1 without an issue refuses when multiple open missions exist.
- Submit is step-resumable. A second click after success does not write again.
- Import will not resurrect a `MERGED`/`ABANDONED` mission. `set_status` honors `ALLOWED` unless forced for abandon/merge events.
- Third-party remote writes remain 0 until a human confirms Gate 2 on one snapshot.
- This release does not submit ripwire #74.

## [0.5.1] - 2026-09-09

### Fixed

- Maintainer-facing PR titles take short quoted literals from the patch (for example `undefined symbol`) instead of pasting a whole added Go/test line.

## [0.5.0] - 2026-09-09

Guarded autonomous contribution, a review workspace, and a maintainer-facing output gate. Remote GitHub writes stay refused.

### Added

- End-to-end local contribution on a confirmed issue: live recertification, sandbox executor, tests, QA, and a package that stops at user review.
- Contribution Review Dashboard: Overview / Changes / PR Preview / Checks, with active vs history missions on the same repo.
- Maintainer-output safety gate on every PR draft: internal metadata, privacy, grounding, cross-issue isolation, language, repo style, and an isolated semantic reviewer.
- Unsafe drafts are `MAINTAINER_OUTPUT_UNSAFE` and cannot be submitted. Historical packages are revised by appending a new artifact, not overwritten.
- PR Preview shows a compact Draft safety status. Check details stay on Checks / Technical Details.

### Unchanged

- Official Top 5 remains v1. Empty Top 5 is success.
- Third-party GitHub writes remain refused. YOLO auto-submit is not enabled.
- No PPO / RL.

## [0.4.1] - 2026-09-04

### Fixed

- Board reads the latest `complete`/`degraded` Official `daily_runs` row on each request. A long-lived `foreshadow-board` process no longer stays on the startup date after the next UTC daily run finishes.

## [0.4.0] - 2026-09-03

Project Intelligence + Learning. The Board ranks by expected entry value; Official Top 5 stays v1.

### Added

- Board: extractive project summary, cached by default-branch SHA. Optional LLM narrative must not invent.
- Four scores: Potential, Creator Prior, Contributor Openness, Entry Fit.
- Expected Entry Value (EEV) requires Potential and Entry Fit. Unknown Openness is ranked conservatively (not omitted, not 0-filled). Displayed Openness stays NA.
- Homepage default sort is Expected Entry Value. Rank is ordinal, not a quality grade.
- Creator prior from HydrateB `owner.repositories` (top ~30). No followers, no sum-of-stars celebrity boost.
- Contributor Openness = Wilson lower bound of external closed PRs (merged + unmerged). Not Access Score. `n_ext<8` → NA.
- Stars enter Potential only as damped growth (`star_trust`). Stars are not a sort key.
- Schema 8: `model_runs`, `intel_scores`, `outcome_labels`. Labels 7/30/90; missing horizon is NULL. No JOIN at score time.
- Offline trainer fits `growth_sign_30d` (30-day local star-delta sign), not Potential. SQLite read-only. Optional sklearn HistGradientBoosting via extra `[learn]`.
- Openness UI is a recent closed-PR sample, not full history.
- Board chips and EEV sort read stored `formula-v1` `intel_scores`. Live rescore is fallback only.
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
