# ADR 0009 — Two human gates, mission_id authority

Date: 2026-09-11
Status: accepted

## Decision

A contribution is identified by `mission_id` plus `issue_number`, never by
“latest mission for this repository.”

There are exactly two human gates:

1. **Enter** — authorize local work on one issue.
2. **Submit** — authorize one immutable approval snapshot (fork if needed,
   push one branch, create one PR). Comments, reviews, merge, and force-push
   stay denied.

An approval snapshot hashes the patch, base, title, body, and planned remote
actions. Any change invalidates it.

Remote writes default to refused. The only exception is a current Gate-2
snapshot. This run must not invoke that exception against third-party GitHub.

## Consequences

- Review queue lists missions, not one card per repo.
- MERGED history must not hide a sibling WAITING mission on the same repo.
- Outcome reconciliation binds the submitted PR to `mission_id`.
- Gate 2 only runs from `WAITING_USER_APPROVAL` and only if the maintainer-output
  leak / privacy / AI-attribution checks pass.
- Import never reopens `MERGED` or `ABANDONED` history. Re-import of the same
  open issue reuses that mission; a later import after merge creates a new one.
- GET review may show a package, but it does not remint the current snapshot
  when the digest moved. A stale package requires Gate 2 again.
