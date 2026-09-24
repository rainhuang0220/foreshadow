# ADR 006: Local repository registry

Status: accepted for the minimum viable local registry.

## Decision

Foreshadow keeps an explicit, versioned `repositories.toml` in its existing
machine-local data directory (`resolve_data_dir()`). It is an address book for
GitHub upstream names and optional checkout paths, not a second identity or
intelligence store. The existing SQLite `repos.id` / `node_id`, `repo_aliases`,
observations, reviews, and missions retain their current ownership. Registry
commands only read that database when showing a known identity. They do not
create repository rows or run migrations.

The file has `version = 1`, an absolute `workspace_root`, and one
`[[repository]]` table per explicitly enrolled repository. `upstream` is a
GitHub `owner/name`; `path` is optional and relative to `workspace_root`.
Remote-only entries and paths to checkouts that do not yet exist are valid.
Unknown schema fields and duplicate names or paths are errors. Paths must stay
inside the resolved workspace root, including through symlinks.

Enrollment does not clone, fetch, or modify Git. Validation reads the checkout
root and its configured `origin` and `upstream` remotes. It reports a personal
fork separately from the canonical upstream. A fork with no matching upstream
remote is *unverified*, not assumed to be the canonical repository. Validation
does not use GitHub access and cannot prove a remote repository's current fork
parent or detect a GitHub rename that has not reached SQLite.

Registered everyday checkouts are never passed to the mission executor by this
feature. Existing mission clone and writable workspace behavior remains a
separate concern. The registry is not an instruction to execute code in a
checkout or to alter ranking, watchlist membership, or mission state.

## Use

Example: [repositories.toml](../../examples/repositories.toml). On the first
enrollment, supply the workspace root. Later entries reuse it:

```sh
foreshadow repos enroll owner/project --workspace-root "$HOME/Desktop/open-source" --path project
foreshadow repos enroll owner/remote-only-project
foreshadow repos list
foreshadow repos validate
foreshadow repos validate owner/project
```

`FORESHADOW_HOME` may override the existing data directory. Keep it outside the
source checkout for normal use. `validate` returns status `ok`, `fork`,
`remote-only`, `missing`, or `upstream-unverified` for inspectable entries;
`mismatch` and `not-checkout` return exit code 1. Malformed registry or command
input returns exit code 2. The registry is written atomically with local file
permissions and can be backed up with the other Foreshadow data.

## Consequences

The TOML file stays easy to review at hundreds of entries. Relocating the
workspace requires editing the one root path. Removing an entry does not erase
SQLite history. If registry queries later become slow or require joins, measure
that specific need before adding an index or table.
