# TODO

## Now

- [x] Owner review of [`docs/p0-architecture.md`](docs/p0-architecture.md)
- [x] Confirm: Python 3.12; GitHub remote `rainhuang0220/foreshadow`; `gh auth token` fallback
- [x] Write P0 implementation plan
- [x] Execute plan Tasks 1–11 — P0 on branch `p0-implementation` (`0.1.0`, not tagged / not on PyPI)
- [x] P1 Preview Audit Board (`foreshadow board --preview`)
- [x] P1 interactive Chinese Board + minimal users (list/drawer, localhost, per-user reviews)
- [ ] Keep P0 dogfood through 2026-08-31 UTC
- [ ] P0 post-run review, then decide PR #1 merge
- [x] Opportunity Engine 2.0 research + scoring audit (no formula changes)
- [x] Owner accepted E2-0…E2-22; plan in `docs/opportunity-engine-v2-plan.md`
- [x] **PR-D** Discovery: pools A/B/C, no `sort:stars`, pre_rank without raw stars, reserved seats
- [ ] PR-V `score_version` dual-write (`003_score_version.sql`)
- [ ] PR-T counterexample tests (E2-16)
- [ ] PR-S1…S5 scoring / preview (not before D+V+T)
- [ ] PR-R Replay 120; ask whether 10–300★ can enter shortlist

## P0 implementation

Plan Tasks 1–11 complete on `p0-implementation`. Version is `0.1.0` in tree only — no git tag, no PyPI/Homebrew publish unless the owner asks.

## Explicitly not now

- Auto PR / issue / comment on third-party repos
- SaaS, OAuth, cloud multi-tenant (P1 is a local Board with optional local accounts)
- Reddit / HN / X / Hugging Face ingest
- GH Archive WatchEvent as official `v7` (labeled P1 only)
- Stargazer listing / fake star-history reconstruction
- Lowering 55/35 to fill Top 5
- ML ranker
- Padding Top 5
- Tagging / publishing 0.1.0 to PyPI
