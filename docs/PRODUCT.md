# Foreshadow Beta — one-pager

Local daily radar. Not trending. You decide. It does not write to GitHub for you.

## Path

Install (`uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.6.0"`) → token → `foreshadow init` → `foreshadow schedule install` (optional) or `foreshadow run` → `foreshadow board` → read why → **进入** → autonomous local prep → **READY_FOR_HUMAN_SUBMIT** → review the snapshot → **提交到 GitHub**.

## Empty Top 5

Success. The Board may still list candidates. Official Top 5 stays empty until a repo has about a week of Foreshadow’s own snapshots. Explosion needs t-7 data.

## Safety

Radar token is GET-only. Gate 2 is the only remote-write exception, and it is bound to one approval snapshot (fork / one branch / one PR). Comments, review, merge, and force-push stay denied.

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
3. **进入**. Wait for the local package to reach READY_FOR_HUMAN_SUBMIT.
4. Review the snapshot. Click **提交到 GitHub** only for that exact version.

CLI: `foreshadow enter owner/repo`
