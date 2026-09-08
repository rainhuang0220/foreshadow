# ADR: Maintainer-facing output safety

**Status:** Accepted (2026-09-09)
**Product:** Foreshadow v0.5

## Context

A production #1551 package put Foreshadow-internal prose on a maintainer-facing PR:

- `人工确认` / Official Top 5 ranking notes from Entry Strategy
- acceptance bullets invented from another issue (`Do not fail when the related tool is not installed`)

YOLO / autonomous submit must not depend on a human noticing that. False-negative blocks are cheaper than a reputation-damaging send.

Style evidence (read-only): [GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue), vshulcz/deja-vu CONTRIBUTING + recent merged PRs (short English `fix(scope): …` titles, prose problem/change, `Closes #N`, named tests, no contributor-process notes).

## Decision

Two layers, deny-by-default:

| Layer | Audience | Examples |
|---|---|---|
| Internal / user | Operator Dashboard | Official Top 5, human confirm, scores, mission/job/artifact ids, executor provenance |
| Maintainer | Third-party GitHub | PR title/body, future comments |

`MaintainerDraftContext` is the only input to draft generation: repo, issue title/body, diff, files, executed tests, CONTRIBUTING / PR template. Entry Strategy why, ranking, and task extras do not flow. Executor prompts also omit ranking `why` so Official notes cannot be pasted into the patch and then echoed into a PR. Leak allowlists come from the issue and repo guidelines, not from the diff. Semantic `ok` is JSON `true` only; `"false"` or a missing field is FAIL.

`MAINTAINER_OUTPUT_GATE` is deterministic (leak / privacy / grounding / cross-issue / language / style / claim match) plus an isolated semantic reviewer that sees only issue, diff, tests, guidelines, and the draft. Any FAIL → `MAINTAINER_OUTPUT_UNSAFE` and remote submission is refused. Regenerations cap at 3.

Unsafe historical packages are not overwritten. A later `package` artifact is a PR-draft revision; Dashboard shows the latest current draft and keeps superseded bodies in Technical Details.

Third-party auto-submit stays off. The only future write entry is
`prepare_remote_submission`: it re-evaluates the current draft and raises
`RemoteWriteRefused("MAINTAINER_OUTPUT_UNSAFE")` on any FAIL. There is no
submit path that reads `pr_body` without that gate.

## Consequences

- `extras_from_issue` no longer invents #1828-shaped acceptance criteria.
- `build_package` composes from the safe context, not `StructuredTask.why`.
- Board PR Preview shows a compact Draft safety banner; check details stay on Checks.
