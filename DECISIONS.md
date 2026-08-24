# DECISIONS

Locked in the P0 spec (`docs/p0-architecture.md`). Reopen only with a written reason.

| ID | Decision | Why |
|---|---|---|
| K1 | Python 3.12 only in P0. CLI `foreshadow`, PyPI `foreshadow-radar`. **No Go. No dual-language stack.** | Owner lock 2026-08-24: scoring, history, optional LLM HTTP, pytest are the core. Go is a future single-binary/distribution migration only. |
| K2 | Opportunity = 20/15/15/20/15/10/5 mix from the product brief | Rejected a second 0–1 scoring system. |
| K3 | SQLite; `node_id` is identity; `full_name` is mutable | Rename / velocity / reviews need real constraints. |
| K4 | GraphQL-first GET-only `httpx` client | Split issue vs PR counts. No PyGithub. No mutations. |
| K5 | Our daily snapshots **are** star history | Stargazer listing restricted 2026-06-30; GH Archive WatchEvent degraded. |
| K6 | Cap 120 candidates first; Phase B ≤20 rankable watchlist then fill to 30; `enter` is Phase A only | Unbounded hydrate blows the 800/400 budget. |
| K7 | Top 5 requires defined `v7` | Lifetime `stars/age` must not pretend to be Explosion. Day-1 Top 5 is empty. |
| K8 | Direction fit is scored, not a hard gate | Exceptional override at ~60% fit. |
| K9 | Reviews filter eligibility; they do not nudge scores | Opportunity stays a pure function of evidence + config. |
| K10 | LLM off by default; narrative only | Cannot change numbers. |
| K11 | UTC calendar dates | Reproducible runs. |
| K12 | Token: `GITHUB_TOKEN` → `GH_TOKEN` → `gh auth token` | No-scope PAT. Never in TOML/SQLite/logs. |
| K13 | MIT, no telemetry, DB mode 0600 | Local-first. |
| K14 | REST 400 / GraphQL 800 points per run | Phase B on ~30 repos. |
| K15 | Do not send `fork:false`; H2 always vetoes forks from Top 5 | Not an official search qualifier. |
| K16 | GraphQL search primary; REST search fallback | Avoid the 30/min REST search bucket when possible. |
| K17 | Fake growth = H1–H10 + P1–P8 | Not a separate architecture veto table. |
| K18 | Stop contributor pagination early | Thresholds are at C=25/80/500, not page 5. |

**Invariants:** no GitHub writes; max 5; no padding; no commit-count KPI; NA ≠ 0; empty Top 5 is success.
