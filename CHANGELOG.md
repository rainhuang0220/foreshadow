# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- P1 Preview Audit Board (`foreshadow board [--preview] [--date]`). Funnel discovered → 20 → 3 independent reviewers → 10 → Chair → ≤5. Official Top 5 still requires P0 `v7`. Preview writes `preview/YYYY-MM-DD/` and does not insert snapshots or invent history.
- Interactive Chinese Review Board on localhost (`foreshadow board` → http://127.0.0.1:8765/). List + drawer, sort/filter, GitHub outbound link, per-user register/login, reviews isolated by `user_id`. Static HTML remains available via `--export-html`. P0 thresholds, v7, and snapshots are unchanged.
- Engine 2.0 Discovery (PR-D): 14-query pools A/B/C, quota as max exposure (underfill OK, no FIFO fill to 120), `lightweight_keep`, `sort:updated` only. Official `score.py` / `select.py` / 55 / 35 / local v7 unchanged.
- Engine 2.0 dual-write (PR-V): `scores.score_version` v1+v2, `score_compare` rank deltas, preview scorer in `score_v2.py`. Official Top 5 / `select.py` / 55 / 35 / local v7 / `score.py` still v1.
- Real 2026-08-25 PR-D dogfood experiment report: [`docs/opportunity-engine-v2-real-experiment.md`](docs/opportunity-engine-v2-real-experiment.md). Official Top 5 still 0.
- Engine 2.0 hydration (PR-H): Phase B seats allocated by pool (default A15/B10/C5), medium REST tier (30), merged-PR acceptance sample, maintainer first-response hours, activity raw counts. `data_completeness` HIGH/MEDIUM/LOW on the Preview Board. Report: [`docs/opportunity-engine-v2-hydration-report.md`](docs/opportunity-engine-v2-hydration-report.md). Official `score.py` / `select.py` / 55 / 35 / local v7 unchanged.
- Engine 2.0 Activity Momentum Preview (PR-A): v2-only 0–100 AM + VERY_LOW…VERY_HIGH, Board 活跃度 evidence. Not star growth, not `windows.v7`. Report: [`docs/opportunity-engine-v2-activity-report.md`](docs/opportunity-engine-v2-activity-report.md).
- Engine 2.0 S1 Preview: Earlyness × Evidence × Opportunity Window, lifecycle stage, experimental pool. Stars are a weak evidence term only. Official v1 / 55 / 35 / v7 unchanged. Report: [`docs/opportunity-engine-v2-s1-report.md`](docs/opportunity-engine-v2-s1-report.md).
- Engine 2.0 S2 Community Access: Access Score from external PR merge/review, maintainer TTR, onboarding. Not Contributor Gap. Board 进入通道.
- Engine 2.0 S3 + Entry Mission: per-repo entry path (Issue / 复现 / 文档 / 讨论…). Board **开始进入** writes `entry_missions`. No automatic GitHub writes.
- Engine 2.0 S4–S6: mission status transitions, contribution_events, `/api/portfolio`, CLI `foreshadow enter`. Remote GitHub writes still refused.

### Changed

- Phase B `pre_rank_key` no longer ranks by raw stars or the 50–8000 star band. Magnet search terms (`llama.cpp`, `ollama`, `vllm`, `cuda`, `rocm`, `tensor rt`) removed from discovery templates.
- Phase B is pool budget allocation rather than a global Top-30. Empty PR samples stay UNKNOWN (not 0). Activity counts are not star velocity.

## [0.1.0] - 2026-08-24

P0 implemented on branch `p0-implementation`. Not tagged and not published to PyPI.

### Added

- Local GET-only GitHub opportunity radar CLI (`foreshadow-radar`).
- Daily star/fork/issue snapshots; Top 5 requires ~7-day star velocity (`v7`); empty Top 5 is valid.
- Explainable Opportunity / Explosion / Contribution scores with H1–H10 hard gates.
- Human review actions (Watch / Interested / Reject / Investigate / Enter / Later) and watchlist.
- Commands: `run`, `report`, `show`, `review`, `watchlist`.
- Optional LLM narrative (`--llm`), off by default; cannot change scores or rank.
