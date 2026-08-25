# 12-HOUR ITERATION REPORT

Elapsed: started `2026-08-25T17:14:36Z`; this checkpoint ~`2026-08-25T18:20Z`. Official still **v1 / 55 / 35 / local v7 / empty Top 5**. No third-party GitHub writes.

## Stages completed

### S2 Community Access
Access Score 0–100 from external PR merge/review, maintainer TTR, onboarding. Independent of Contributor Gap. UNKNOWN ≠ 0.

Replay 2026-08-25 (existing hydrate): 30/120 known (Phase B); 90 UNKNOWN until the next run picks up the new medium closed-PR page.

Commit: `e89853c` `feat: add community access scoring`

### S3 Contribution Strategy
Default path is Issue / Discussion / Reproduction / Docs / Tests — **not PR**. Experimental pool → Discussion. Hard languages do not get a core-rewrite entry. Long-term potential is explainable and NA when unknown.

### Entry Mission
Board **开始进入** and CLI `foreshadow enter owner/repo` create `entry_missions`, write `FORESHADOW.md`, and `git clone --depth 1` into `$FORESHADOW_HOME/work/{owner}__{repo}/repo`.

Verified: `foreshadow enter rainhuang0220/foreshadow` → `clone=cloned`, status `WAITING_USER_APPROVAL`. Board POST `/api/mission` + `/setup` cloned `eigenpal/docx-editor`.

### S4 Human-in-the-loop
`/api/mission/remote` always returns blocked. Transitions cannot jump to `SUBMITTED`. Copy: 等待你的确认才能执行任何远程 GitHub 操作.

Review radio **进入** is now **记入观察清单（不是创建任务）** so it is not confused with **开始进入**.

### S5 Contribution Learning
`contribution_events` records `entered` / `local_setup` / `clone_ok` plus user-marked outcomes. `observed_access` is a **visible overlay**. Formula Access weights are unchanged. Fewer than 3 outcomes → UNKNOWN, not 0.

### S6 Reputation / Portfolio
`GET /api/portfolio` counts missions/events and includes `observed_access`. Does not scrape third-party GitHub.

## Tests
`uv run pytest` → **313 passed**.

## Real experiments
- Dogfood sqlite run_id=2 (2026-08-25): 120 candidates, Phase B 30 / medium 30 / lightweight 60. Access terms only on the 30 Phase B rows until the next hydrate.
- Local clone of `rainhuang0220/foreshadow` and `eigenpal/docx-editor` succeeded (`--depth 1`).
- Board on `:8767`: register → board → 开始进入 → clone → remote create_pr blocked.
- Live GET of closed PRs on 6 medium-tier dogfood repos (GET-only, not written back): Access became known across 20–300 / 300–1000 / 1000+ (VERY_LOW and LOW). HIGH still needs Phase B review/TTR. Known 0% external merge is a real 0, not UNKNOWN.

## What you can do tomorrow morning

```bash
cd .worktrees/p0-implementation
FORESHADOW_HOME=dogfood/local/home uv run foreshadow board --preview
```

1. Open http://127.0.0.1:8765/
2. Log in
3. Open `eigenpal/docx-editor` (or `curie-eng/curie` / `bobmatnyc/trusty-tools`)
4. Read 阶段 / 证据 / 进入通道 / **推荐入口**
5. Click **开始进入** (not the review radio 记入观察清单)
6. Wait for local clone; read FORESHADOW.md
7. Confirm the banner: the system will not post Issues/PRs until you say so
8. **查看任务** lists what you entered; **停止任务** abandons

CLI equivalent: `FORESHADOW_HOME=dogfood/local/home uv run foreshadow enter owner/repo`

## What remains
- Re-run hydrate so medium closed-PR samples fill Access on ~30 more repos
- Optional: GraphQL `prsMerged` on Phase A for full-pool Access (budget/complexity tradeoff)
- S5 overlay is not blended into rank
- Local PR draft / patch attach still later
- Official v2 cutover (not this window)

Checkpoint notes: Board now shows `strategy_why`, open issues carry `#N`, `ISSUE_DRAFT.md` is rewritten after GET, list refreshes to **查看任务** after 开始进入.

Replay of `recommend_entry` on the 2026-08-25 120 (no GitHub writes): ISSUE 41 / DISCUSSION 69 / REPRODUCTION 6 / TEST 2 / BUG_FIX 2 / direct PR 0. Lightweight 60 → DISCUSSION; medium 30 → ISSUE; Phase B mixed. Docs/tests/CI paths now require known merge rate.

Tests: **322 passed**.

## Top remaining bottlenecks
1. Access UNKNOWN on 90/120 until the next dogfood hydrate
2. Mission is not yet joined onto every board card (list still offers 开始进入 even if a mission exists)
3. No automatic GitHub merge tracking — user marks `pr_merged`
