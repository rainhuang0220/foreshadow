# Foreshadow Beta — one-pager

Local daily radar. Not trending. You decide. It does not write to GitHub for you.

## Path

Install (`uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.3"`) → token → `foreshadow init` → `foreshadow schedule install` (optional) or `foreshadow run` → `foreshadow board` → read why → **开始进入** → local prep → **等待你确认远程操作**.

## Empty Top 5

Success. The Board may still list candidates. Official Top 5 stays empty until a repo has about a week of Foreshadow’s own snapshots. Explosion needs t-7 data.

## Safety

No auto Issue / PR / comment / push. **尝试创建 PR（应被拒绝）** is refused. Board is localhost only. Token stays on this machine.

## Honest

Search truncated by design (first 25 × 14 queries). 7-day deterministic integration **VERIFIED**. Real 7-day soak **IN PROGRESS**.

## Tomorrow morning

```bash
foreshadow doctor
foreshadow run          # skip if today already ran
foreshadow board        # http://127.0.0.1:8765/
```

1. Look at observation / empty Official Top 5.
2. Open a candidate. Read 为什么现在.
3. **开始进入**. Wait for clone + `FORESHADOW.md`.
4. Confirm remote write is blocked.

CLI: `foreshadow enter owner/repo`
