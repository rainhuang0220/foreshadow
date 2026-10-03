# Engineering audit — 2026-10-03

Baseline: 11b5c4c, package 0.6.1, origin/main de0edce; current source branch carries seven unpushed commits and user edits. Work happens on engineering/opportunity-handoff from committed HEAD. No user edits are copied or discarded. Registry worktrees include obsolete Desktop locations; they are left alone.

Foreshadow discovers public repositories, retains local observations, evaluates entry opportunities, and explains them on a Board. Observation membership, measured snapshot, score, entry recommendation, mission authorization, and execution attempt are distinct. Preserve Official eligibility, GET-only collection, SQLite identities, conservative missing-data rules, and exact human approval gates.

The debt is execution ownership: contribution backends, subprocess lifecycle and sandbox code live beside decision preparation; CLI is over 1,100 lines. EntryStrategy and StructuredTask are useful existing abstractions. Dated evidence remains loosely structured and unvalidated at the export boundary. Observation star_delta confuses number of samples with a calendar window; separate upstream temporal branches exist and remain unmerged. No new opportunity tables or scheduler are justified.

Chosen slice: introduce immutable decision types, reuse StructuredTask via a compatibility import, read retained entry/snapshot records through a read-only adapter, validate freshness/provenance/actionability, rank deterministically, and export a generic versioned work order. Coding backends remain a deprecated compatibility surface during migration; new decision/export paths never launch them. Removal of Board contribution paths would conflict with uncommitted user work and requires a separate migration.

Full baseline: 807 passed, 3 existing optional skips. CI runs Ruff, format, pytest, version and wheel checks. Tag release workflow is reused; no replacement pipeline. Last tag v0.6.1. No credential/network writes are part of collection or export.

Implementation and real canary findings: [engineering dogfood](engineering-dogfood.md). Domain vocabulary: [CONTEXT](../CONTEXT.md). The release candidates retain the limitations stated there; no production release is claimed.

Validation: 833 passed, 8 subtests passed and 3 pre-existing environment skips (Docker image and two sklearn checks); 836 collected. Ruff lint/format, lock consistency, 0.7.0 wheel/sdist and independent install boundary checks pass.
