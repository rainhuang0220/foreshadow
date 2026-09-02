# ADR: Contribution executor (orchestrator, not a new coding agent)

**Status:** Accepted (2026-09-02)
**Product:** Foreshadow v0.3

## Context

Users want Foreshadow to choose an entry task, implement it, run tests, and produce a contribution package. Rebuilding a full SWE agent is out of scope. OpenHands (MIT SDK + `github-issue-to-pr` / `iterate` / `qa-changes` skills), mini-SWE-agent (MIT, docker/podman, bash-only, SWE-bench >74%), and SWE-ReX (MIT sandbox) already exist. Copilot coding agent is not self-hosted.

Foreshadow already clones shallow, writes `FORESHADOW.md` / `ISSUE_DRAFT.md`, and refuses remote GitHub writes.

## Decision

Foreshadow owns **discovery → observation → entry strategy → QA → human approval → (later) GitHub gateway**.

Coding is behind `ContributionExecutor`:

```python
prepare() -> analyze() -> implement() -> test() -> iterate() -> produce_patch()
```

Backends:

| Name | Role in v0.3 |
|---|---|
| `native` | Default. Docker (required for untrusted third-party code). Clone, apply agent edits or a constrained local loop, run detected tests, emit unified diff. |
| `mini_swe_agent` | First external backend if the extra is installed. Same sandbox contract. |
| `openhands` | Optional adapter around Software Agent SDK. Not a hard dependency of `foreshadow-radar`. |

Rules:

- No GitHub write token in the sandbox. Host `GITHUB_TOKEN` is GET-only and stays on the host.
- No `docker.sock` inside the sandbox. No host HOME mount. Git hooks disabled (`core.hooksPath=/dev/null`).
- Network in the sandbox: off by default; package installs only if the operator opted in for that job.
- Output is a **contribution package** (diff, test log, PR title/body, risk, QA). Remote remains refused.
- Quality gate runs on the host, on the artifact, before `WAITING_USER_APPROVAL`.

## Why not lock to OpenHands

The SDK is the right long-term coding engine (MIT, Docker Agent Server, issue-to-PR skills). It is also a moving V1 platform with optional enterprise-licensed trees. Foreshadow’s product value is **which task and whether it is worth sending**, not the file editor. An interface lets us ship a native/mini PoC this release without taking a monorepo dependency.

## Consequences

- New tables: `entry_analyses`, `contribution_jobs`, `contribution_artifacts` (schema 7).
- Board shows job progress and the package. Approve & Draft PR is visible and disabled.
- Golden path uses a real shortlisted repo, stops before `git push`.

## REAL POC RESULT (2026-09-03)

Compared by actually running a third-party repo, not by architecture preference.

| | mini-SWE-agent 2.4.6 + Docker | OpenHands adapter |
|---|---|---|
| setup | `pip install mini-swe-agent`; image `python:3.12-slim-bookworm` (the `python:3.12-bookworm-slim` tag does not exist) | still unwired; SDK/monorepo too heavy for this PoC |
| wall time | 178s clone → install → agent → tests → QA on Cyrax321/CONTINUUM #582 | not run |
| token usage | 15 model calls; cost tracker 0 (DeepSeek not in LiteLLM registry) | n/a |
| patch quality | 3 files: serve.py + 2 regression tests; QA PASS; 37→39 tests | n/a |
| test reliability | targeted `test_serve.py` + `test_serve_http.py` stable in 4s | n/a |
| sandbox | Docker volume mount, no GitHub token, network only for pip install then disconnected | n/a |
| integration difficulty | v2 tool-calling; DeepSeek Anthropic-compat rejects custom tools, OpenAI-compat works | high |

**v0.3 default coding backend: `mini_swe_agent` when the extra is installed, else `native`.** OpenHands stays an optional stub.

Blockers found and kept:

- Observation-24 Python repos were too heavy, license-unclear, or had overlapping PRs. CONTINUUM is outside the 24; screening is in `docs/real-contribution-poc.md`.
- Raw Entry Strategy preferred a README star-badge GFI that already had open PR #604. Overlap filter + bug-weighting selected #582.
- `git` is missing in `python:3.12-slim-bookworm`; the agent still edited with Python/sed. Host `git diff` produces the package.
