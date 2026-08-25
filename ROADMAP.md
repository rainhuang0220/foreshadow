# ROADMAP

## P0 — GitHub Opportunity Radar (implemented, not released)

**Goal:** Every UTC day, discover a shortlist of emerging public GitHub repos, score them explainably, emit **at most 5** cards (empty is success), and record a human review. No GitHub writes. No dashboard. No ML.

**Done on branch `p0-implementation`:** package `foreshadow-radar` `0.1.0` — GET-only radar, empty Top 5 OK, `v7` required for Top 5, human review / Enter / watchlist, optional LLM narrative. Spec: `docs/p0-architecture.md`.

**Not done:** git tag, PyPI / Homebrew publish. Merge to `main` still waits for the 7-day dogfood review.

P0 success: `GITHUB_TOKEN` + `foreshadow run` produces a markdown Top 5 (or honest empty list) with component scores, evidence, confidence, and risk; `foreshadow review` records Watch / Interested / Reject / Investigate / Enter / Later; same-day re-run does not duplicate reviews; CI never talks to `api.github.com`.

**Hard product rule:** Top 5 requires a defined 7-day star velocity from *our* snapshots. Day 1 of a fresh install emits **zero** Top 5 by construction.

## P1 — Audit Board (Preview implemented)

HTML Daily Board + 100→20→3 reviewers→10→Chair. Official Top 5 still requires `v7`. No extra data sources in this slice.

## Opportunity Engine 2.0 (research 2026-08-25)

**Not implemented.** v1 remains official. Plan: [`docs/opportunity-engine-v2-audit.md`](docs/opportunity-engine-v2-audit.md).

Goal: rank **early window × real contribution**, not 1k–5k star AI incumbents. Official Top 5 still needs **local** `v7`. Day-1 GitHub **star** history is not available (stargazer listing admin-only). Activity windows (forks/issues/PRs) may label movement; they must not become `windows.v7`.

Order after owner OK: discovery quota → `score_version` dual-write → counterexample tests → Entry Window + acceptance → preview reads v2 / official stays v1 → replay 120 → cutover.

## P1 later / P0+ 

Multi-source discovery (HN / Reddit / …), GH Archive backfill of `v7` (**labeled only**, WatchEvent is degraded), maintainer first-response time. Not this PR.

## P2 — contribution assistance (human still submits)

On **entered** repos only: clone, issue clustering, local PR draft. Still never auto-push to third-party repos.

## P3 — portfolio

Personalized ranking (explainable), ecosystem graphs, “how many Enter decisions 10×d?”

Do not merge to `main` until the 7-day dogfood post-run review.
