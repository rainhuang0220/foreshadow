# Foreshadow (伏笔)

**Beta 0.2.4** — find what the future has already foreshadowed.

Foreshadow is a local daily radar for public GitHub, not a trending feed. Once a day it discovers emerging repos, keeps observing the ones that might still be enterable, and shows a Board of what is worth looking at — with why. If you choose to enter, it prepares a local clone and a plan, then **stops**. It never opens Issues, comments, or PRs, and it never pushes to someone else’s GitHub.

中文说明见 [README.zh-CN.md](README.zh-CN.md)。明早走查见 [docs/PRODUCT.md](docs/PRODUCT.md)。

## Install / update

Python **3.12+**. `git` is needed if you will enter a repo.

```bash
# uv (recommended) — pin a release tag
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4"

# pip
pip install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4"
```

Update to a newer tag (git installs do **not** follow new tags via `uv tool upgrade`):

```bash
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4" --reinstall
# or: uv tool uninstall foreshadow-radar && uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4"
```

## GitHub token

Foreshadow only **reads** public GitHub. Keep the token on this machine — never in a config file.

```bash
export GITHUB_TOKEN=ghp_…     # classic PAT with no scopes
# or GH_TOKEN
# or: gh auth login           # Foreshadow uses `gh auth token`
```

A fine-grained token should be public-repo read only. Do not grant `repo` or write access.

## Start

```bash
foreshadow init                 # default config; you usually do not edit it
foreshadow schedule install     # optional: daily auto-run on this machine
foreshadow run                  # run today yourself if you skipped the schedule
foreshadow board                # opens http://127.0.0.1:8765/
```

`run` is at most once per day. If today already finished, it skips — that is normal.

**Local mode:** `foreshadow board` on this machine (localhost). Register a local Board account, then look at **今日候选榜**.

**Cloud deployment:** run Official `foreshadow run` and the Board as a systemd service behind nginx. See [`docs/deploy.md`](docs/deploy.md). The Board process itself still binds loopback; the public URL is deployment config, not a package constant.

Register a local Board account (username, email, password). It stays on this machine. Then look at **今日候选榜**.

## Empty Top 5 is success

Official Top 5 is allowed to be **empty**. Foreshadow will not pad the list.

The Board can still show candidates to watch. Explosion for a repo needs about seven days of Foreshadow’s own observations of **that same repo**. In the first week, expect an empty Official Top 5.

## Enter a repo

1. Open a candidate. Read **为什么现在** / **进入通道** / **推荐入口**.
2. Click **开始进入**. Do not use **记入观察清单** — that only saves a personal stance.
3. Wait for local prep: shallow clone, `FORESHADOW.md`, `ISSUE_DRAFT.md`.
4. Status becomes **等待你确认远程操作**. Nothing is posted to GitHub.

CLI equivalent: `foreshadow enter owner/repo`.

## Safety

- No automatic GitHub writes in this beta.
- **尝试创建 PR（应被拒绝）** is refused on purpose.
- The Board binds localhost only.
- Discovery is GET-only. Clone is local. Remote writes stay blocked until you do them yourself.

## Check

```bash
foreshadow doctor    # token, config, ready to run
foreshadow status    # last daily run
```

## Known limitations

- Search is truncated by design: first 25 hits × 14 queries. Not a bug.
- Explosion needs t-7 data (a week of snapshots for that repo). Lifetime stars/age is not Explosion.
- 7-day deterministic integration: **VERIFIED**.
- Real 7-day soak: **IN PROGRESS**.

## Tomorrow morning

1. `foreshadow doctor`
2. `foreshadow run` (skip if it already ran today)
3. `foreshadow board`
4. Look at observation / empty Official Top 5 — empty Top 5 is success
5. Open a candidate and read why
6. **开始进入**
7. See local prep (clone + plan)
8. Confirm remote write is blocked (**尝试创建 PR**)

## License

MIT. Engineer internals live in [`docs/`](docs/).
