# Contributing

P0 is a small local CLI. Keep changes honest and scoped.

## Setup

```bash
uv sync --group dev
```

Python **3.12+** (CI also runs 3.13).

## Checks

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

## Rules

- **No live GitHub in CI.** Tests use fixtures (`respx` / recorded payloads). Do not call `api.github.com` from the test suite.
- Do not commit `.env`, tokens, local `data/`, `reports/`, or `*.sqlite3`.
- Prefer small PRs that match the P0 plan tasks. Do not pad Top 5 behavior or invent P1 features in P0.
- English README is the product source of truth; keep `README.zh-CN.md` as a short pointer.

## Commit style

Imperative summary, e.g. `chore: …`, `feat: …`, `test: …`.
