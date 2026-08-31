# Foreshadow (伏笔)

Find what the future has already foreshadowed.

Foreshadow is not trending. It is a local, explainable short-list of repos you might still be able to help, produced at most once a day, with you as the final decision maker.

**Status:** P0 shipped on `main` (`0.1.0`). P1 adds a **persistent observation panel** so yesterday's repos can still be hydrated when Search misses them. Official scoring is still v1 (55 / 35 / local `v7`). Empty Top 5 is OK. Human review required.

中文简介见 [`README.zh-CN.md`](README.zh-CN.md)。English README is the source of truth.

## What it does

A local CLI that, at most once per UTC day:

1. **Discovers** emerging public GitHub repositories (GET-only search)
2. **Observes** a persistent panel (operator watchlist + system-promoted repos) even if Search does not return them again
3. Writes a daily star/fork/issue snapshot for seated repos
4. Scores Opportunity / Explosion / Contribution (Official v1; Explosion needs local `v7`)
5. Emits a markdown report with **at most five** cards
6. Records your Watch / Interested / Reject / Investigate / Enter / Later review

Search answers “what appeared today?”. Observation answers “what have we been watching?”. Scoring answers “is it worth entering now?”. See [`docs/p1-observation.md`](docs/p1-observation.md).

## Non-goals (P0)

- This is not trending.
- No auto PR / issue / comment on third-party repos
- No dashboard, SaaS, or multi-user cloud
- No Reddit / HN / X / Hugging Face ingest
- No ML ranker
- Never pad the Top 5

## Honest caveats

- Empty Top 5 is OK.
- Top 5 requires a local `v7` window (`t-7` ± 1 day) on **the same repo**, not merely “7 calendar days of global snapshots”.
- Lifetime `stars/age` is not Explosion.
- Token stays on the machine.
- We only GET public GitHub.

## Security

- Token stays on the machine. Prefer `GITHUB_TOKEN` or `GH_TOKEN` in the environment, or `gh auth token`. Never put the token in config, SQLite, reports, or logs.
- Use a classic PAT with **no scopes**, or a fine-grained token with public read only. Do not request `repo` / `public_repo`.
- We only GET public GitHub. The client must not write to third-party repos.

## Install (dev)

Requires Python 3.12+.

```bash
uv sync --group dev
uv run foreshadow --help
```

## Commands

```text
foreshadow run [--force] [--date YYYY-MM-DD] [--llm]
foreshadow report [--date YYYY-MM-DD] [--json]
foreshadow show <owner/repo>
foreshadow review <owner/repo> <action> [-m note]
foreshadow watchlist [action]
foreshadow board [--preview] [--date YYYY-MM-DD] [--no-open] [--export-html] [--port 8765]
foreshadow enter <owner/repo>
```

### Daily Review Board (interactive)

```bash
uv run foreshadow board --preview --no-open
```

Then open **http://127.0.0.1:8765/** in a browser (the command also opens a tab unless `--no-open`).

The server binds **127.0.0.1 only**. Register with username + email + password (hashed, never stored in plaintext). The first screen is a ranked list (composite score, descending). Click a row for the drawer: stage, earlyness, evidence, opportunity window, access, recommended entry path, five dimensions, Chair, and **开始进入**. That button creates an Entry Mission, writes `FORESHADOW.md`, and may `git clone --depth 1` into `$FORESHADOW_HOME/work/`. It never opens Issues/PRs or pushes. **查看任务** lists missions. Review radio **进入** only records a personal stance (hydrate / watchlist) — it does not start a mission.

CLI: `foreshadow enter owner/repo`, `foreshadow missions`, `foreshadow outcome owner/repo --event maintainer_replied`. Walkthrough: [`docs/entry-mission.md`](docs/entry-mission.md).

`--export-html` still writes a static Chinese list (accordion) under `preview/YYYY-MM-DD/` or `reports/`. It is an export, not the product.

`board --preview` reads **real** snapshots. Missing `v7` shows as N/A / 预览模式. It does not write fake history. Official Top 5 stays empty until ~7 days of snapshots exist.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version:

```bash
uv sync --group dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

CI runs ruff + pytest on Python 3.12 and 3.13 with **no** live calls to `api.github.com`.

## License

MIT — see [`LICENSE`](LICENSE).
