# Foreshadow · 伏笔

You are looking at **`main`**, which currently holds only the P0 spec and planning docs.

The running implementation is **not on this folder’s checkout**.

| What | Where |
|---|---|
| Code + CLI (`0.1.0`) | `.worktrees/p0-implementation` (branch `p0-implementation`) |
| Spec | [`docs/p0-architecture.md`](docs/p0-architecture.md) |
| GitHub | will be `https://github.com/rainhuang0220/foreshadow` after the remote exists |

```bash
cd .worktrees/p0-implementation
uv sync --group dev
uv run foreshadow --help
```

`p0-implementation` is **not merged** into `main` yet. That wait is intentional: a 7-day real run comes first.
