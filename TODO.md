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
- [ ] Owner accepts Engine 2.0 locks in `docs/opportunity-engine-v2-audit.md` / DECISIONS E2-*
- [ ] Then: discovery v2 (quota, star strata) — still no official score change
- [ ] Then: `score_version` dual-write + counterexample tests + v2 formulas
- [ ] Replay 2026-08-24 120 in-memory; compare lists; do not write fake snapshots

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
