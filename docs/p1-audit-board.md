# P1 — Audit Board / Explainable Screening Pipeline

**Status:** Implemented (Preview first)  
**Date:** 2026-08-25  
**Does not change:** P0 `min_opportunity`, `min_explosion`, v7 official gate, snapshot-first history, dogfood scheduler.

## Modes

| Mode | When | Ranking |
|---|---|---|
| **Official** | `v7` defined (Momentum confidence medium/high) | P0 eligibility ∩ Chair order. May be 0–5. |
| **Preview / Provisional** | `v7` missing | Same pipeline on **real** snapshots. Dimensions that need history are `N/A`. Must not be described as a forecast. |

Preview **must not** insert snapshot rows or invent `S(t-7)`.

Artifacts: `{FORESHADOW_HOME}/preview/YYYY-MM-DD/board.json` and `board.html`.

## Funnel

Discovered (actual N) → shortlist 20 (non-veto) → 3 parallel reviewers → deep 10 → Chair → official Top 5 and/or provisional ranking.

## Reviewers

Independent weighted engines on five dimensions (0–20). Weights live in `[board]` config, not in reviewer code. Scores drop NA terms and **do not** fill 0. LLM may add prose later; it cannot change numbers.

Chair blend default 40/20/20/20 with explicit override + justification.

## P0 relationship

`select.is_official_eligible` is the only official Top 5 gate. Board never lowers it.
