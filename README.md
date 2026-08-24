# Foreshadow (伏笔)

Find what the future has already foreshadowed.

Foreshadow is not trending. It is a local, explainable short-list of repos you might still be able to help, produced at most once a day, with you as the final decision maker.

**Status:** P0 implemented (`0.1.0`) on branch `p0-implementation`. Not tagged and not published to PyPI. GET-only radar; empty Top 5 is OK; Top 5 needs ~7 daily snapshots (`v7`); human review required.

中文简介见 [`README.zh-CN.md`](README.zh-CN.md)。English README is the source of truth.

## What it does

A local CLI that, at most once per UTC day:

1. Discovers a shortlist of emerging public GitHub repositories (GET-only)
2. Writes a daily star/fork/issue snapshot
3. Scores Opportunity / Explosion / Contribution
4. Emits a markdown report with **at most five** cards
5. Records your Watch / Interested / Reject / Investigate / Enter / Later review

## Non-goals (P0)

- This is not trending.
- No auto PR / issue / comment on third-party repos
- No dashboard, SaaS, or multi-user cloud
- No Reddit / HN / X / Hugging Face ingest
- No ML ranker
- Never pad the Top 5

## Honest caveats

- Empty Top 5 is OK.
- Top 5 requires ~7 daily snapshots (`v7`); day 1 is empty by construction.
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
```

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
