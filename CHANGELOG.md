# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-08-24

P0 implemented on branch `p0-implementation`. Not tagged and not published to PyPI.

### Added

- Local GET-only GitHub opportunity radar CLI (`foreshadow-radar`).
- Daily star/fork/issue snapshots; Top 5 requires ~7-day star velocity (`v7`); empty Top 5 is valid.
- Explainable Opportunity / Explosion / Contribution scores with H1–H10 hard gates.
- Human review actions (Watch / Interested / Reject / Investigate / Enter / Later) and watchlist.
- Commands: `run`, `report`, `show`, `review`, `watchlist`.
- Optional LLM narrative (`--llm`), off by default; cannot change scores or rank.
