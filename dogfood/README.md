# P0 dogfood (7 calendar days)

This is a **real-data** soak of Foreshadow P0. It is not a merge gate by itself.

## Rules (do not break)

1. Do **not** lower `min_opportunity` / `min_explosion` to fill Top 5.
2. Do **not** invent or backfill star history. Snapshots only grow by running the CLI.
3. Empty Top 5 is **success**, not a bug.
4. Do **not** merge `p0-implementation` into `main` until the post-run review.

Window: start **2026-08-24** UTC. Review on or after **2026-08-31** UTC (7 calendar days).

## Where logs live

Local only (gitignored):

```
dogfood/local/JOURNAL.md
dogfood/local/YYYY-MM-DD.md      # copy of the daily report if present
dogfood/local/YYYY-MM-DD.json
dogfood/local/YYYY-MM-DD.meta.json
```

Application data (also local):

```
~/Library/Application Support/foreshadow/
```

## How to run one day

From this worktree:

```bash
./scripts/dogfood-run.sh
```

LaunchAgent (macOS, 08:15 local ≈ 00:15 UTC if you are on UTC+8):

```bash
launchctl load ~/Library/LaunchAgents/ai.foreshadow.dogfood.plist
```

## Anomalies to record

Record these as anomalies. **Do not** treat empty Top 5 as one.

- CLI exit ≠ 0
- Missing token
- Rate limit / budget abort
- Degraded run (`search_truncated`, `hydrate_failed`, `watchlist_truncated`)
- Crash leftover (`status=running`/`failed`)
- Config scoring weights changed (forbidden)
