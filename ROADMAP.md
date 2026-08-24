# ROADMAP

## P0 — GitHub Opportunity Radar (implemented, not released)

**Goal:** Every UTC day, discover a shortlist of emerging public GitHub repos, score them explainably, emit **at most 5** cards (empty is success), and record a human review. No GitHub writes. No dashboard. No ML.

**Done on branch `p0-implementation`:** package `foreshadow-radar` `0.1.0` — GET-only radar, empty Top 5 OK, `v7` required for Top 5, human review / Enter / watchlist, optional LLM narrative. Spec: `docs/p0-architecture.md`.

**Not done:** git tag, PyPI / Homebrew publish. Do not start P1 until after about a week of real daily use.

P0 success: `GITHUB_TOKEN` + `foreshadow run` produces a markdown Top 5 (or honest empty list) with component scores, evidence, confidence, and risk; `foreshadow review` records Watch / Interested / Reject / Investigate / Enter / Later; same-day re-run does not duplicate reviews; CI never talks to `api.github.com`.

**Hard product rule:** Top 5 requires a defined 7-day star velocity from *our* snapshots. Day 1 of a fresh install emits **zero** Top 5 by construction.

## P1 — after a week of real daily use

Multi-source discovery (HN / Reddit / … with source degradation), GH Archive backfill of `v7` for newly seen names (labeled, not mixed silently into acceleration), maintainer first-response time, user starred-repos as seeds, `gh` extension, Windows CI.

## P2 — contribution assistance (human still submits)

On **entered** repos only: clone, issue clustering, local PR draft. Still never auto-push to third-party repos.

## P3 — portfolio

Personalized ranking (explainable), ecosystem graphs, “how many Enter decisions 10×d?”

Do not start P1 until P0 has been used for a week.
