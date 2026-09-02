# Real contribution PoC (2026-09-03)

Foreshadow prepared a third-party patch locally. It did not fork, push, comment, or open a PR.

## Observation 24 (2026-09-02 board) — why not those Python repos

| Repo | Why not this PoC |
|---|---|
| jjang-ai/vmlx | MLX GPU serving, 132MB, hardware-specific |
| caura-ai/caura | 23 open PRs; #1138 is EOF/format; collision risk |
| Human-Agent-Society/reef | continual-learning / training features, not a small bug |
| rlaope/oh-my-hermes | real cost bugs (#1272/#1273) but 89MB coding harness |
| hyeonsangjeon/gdpval-realworks | single proposal issue, large benchmark corpus |
| memtomem/memtomem | #2243 is a design question, not an agreed code task |
| aws-samples/sample-agent-platform-with-agentcore | 0 issues |
| AmirhosseinHonardoust/Sentiment-Analysis-BERT | 0 issues, training notebook |

Non-Python observation repos were skipped for environment size or language (Rust/Go/C++/TS/OCaml).

Selected **Cyrax321/CONTINUUM** (Apache-2.0, Python, pydantic-only core, pytest, active, public). Not in the 24; used as an executor integration target after the 24 failed the PoC constraints.

## Entry Strategy (live GitHub evidence, 2026-09-03)

Raw ranking without PR overlap preferred #547 (star badge, help wanted / GFI). Open PR #604 already says `Fixes #547`.

After skipping issues claimed by open PRs and weighting labeled bugs above cosmetic GFI:

- **Plan A** ISSUE #582 — stdio/HTTP crash on JSON non-object
- **Plan B** REPRO #582
- **Plan C** FIX #582

Policy: PRs welcome, no CLA/DCO, good-first-issue alive. CONTRIBUTING.md + AGENTS.md present.

PR #577 is HTTP *framing* (#533), not this payload-shape hole.

## Selected task

Issue #582. Verified on clone `2e0ef3e`: `req.get("id")` at `src/continuum/serve/server.py:282` AttributeErrors on `[]` / `null`. HTTP `BadParams` for non-object body escaped `do_POST`.

## Executor

- backend: mini-SWE-agent 2.4.6 + Docker `python:3.12-slim-bookworm`
- sandbox remotes: none; no GitHub token in container
- network: pip install only, then `docker network disconnect bridge`
- wall time: 178s
- model: DeepSeek `deepseek-v4-pro` via OpenAI-compat (`https://api.deepseek.com`). Anthropic-compat at `/anthropic` rejects custom tools.
- 15 model calls; LiteLLM cost 0 (unregistered model)

## Baseline / tests

```
BASELINE  python -m pytest tests/test_serve.py tests/test_serve_http.py -o addopts= --tb=short -q
          37 passed, 1 skipped   exit 0

AFTER     same command
          39 passed, 1 skipped   exit 0
```

Two new regression tests. Existing failures were not involved.

## Implementation

Files changed: 3

- `src/continuum/serve/server.py` — stdio: reject non-dict JSON with `bad_request` and continue; HTTP: 400 JSON instead of raising out of the handler
- `tests/test_serve.py` — `[]` then a valid line still answers
- `tests/test_serve_http.py` — `[]` / `null` → 400, server still serves

## QA

PASS. Non-empty relevant diff, no secrets, no lockfile churn, tests exit 0, no duplicate active PR for #582.

## Contribution package

- PR title (generated): Fix serve: a valid-JSON non-object request kills the stdio loop and closes HTTP unanswered (#582)
- Related issue: #582
- Risk: local sandbox only; remote GitHub writes are refused
- Estimated acceptance: medium-high
- remote writes: 0
- remote status: WAITING_USER_APPROVAL

## Board

Job `Cyrax321/CONTINUUM` status `ready` persisted in local `contribution_jobs`. Project detail / jobs panel shows Files changed, Tests, QA, expandable diff. Draft PR button remains disabled.

## Failures / limitations worth keeping

- Observation 24 had no small, licensed, low-env Python bug without an overlapping PR.
- Entry Strategy without PR-overlap would have sent the user to a README badge.
- Docker tag `python:3.12-bookworm-slim` does not exist.
- DeepSeek Anthropic-compat cannot host mini-SWE's bash tool.
- Slim image has no `git`; host git builds the diff.
- Install ~2 min of the 178s wall time.
- Cost tracking is blind on DeepSeek.
- OpenHands was not needed and was not wired.
