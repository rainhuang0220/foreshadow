# 从发现到进入

Foreshadow 不替你在别人的 GitHub 上发言。它把一个仓库变成一份**本地进入任务**。

## 明天早上

```bash
cd .worktrees/p0-implementation
FORESHADOW_HOME=dogfood/local/home uv run foreshadow board --preview
```

打开 http://127.0.0.1:8765/ ，登录，看今日候选榜。

1. 看 **阶段 / 机会 / 通道 / 推荐入口**（不是 Star 榜）。
2. 点 **开始进入**（不要点评审里的「记入观察清单」——那只是个人立场，不会创建任务）。
3. 等本地 `git clone --depth 1`。工作目录在 `$FORESHADOW_HOME/work/{owner}__{repo}/`。
4. 读 `FORESHADOW.md` 和 `ISSUE_DRAFT.md`。
5. 系统会停在 **等待你的确认才能执行任何远程 GitHub 操作**。

命令行等价：

```bash
FORESHADOW_HOME=dogfood/local/home uv run foreshadow enter owner/repo
FORESHADOW_HOME=dogfood/local/home uv run foreshadow outcome owner/repo --event maintainer_replied
```

## 本地会做的

- clone（失败也保留任务）
- 本地分支 `foreshadow/entry`（不 push）
- 读 README 标题、CONTRIBUTING 是否存在
- 若策略引用了 Issue `#N`，GET 该 Issue 正文进计划
- 写 Issue/讨论草稿

## 不会做的

不会自动：开 Issue、开 Discussion、push、开 PR、评论、review、merge。

点「尝试创建 PR」会被拒绝。你自己在 GitHub 提交之后，可以用「我已自行提交」或 `foreshadow outcome --event user_submitted` 记账。

## 任务状态（人话）

| 状态 | 意思 |
|---|---|
| 任务已就绪 | 计划写好了 |
| 正在准备本地环境 | clone / 读仓库 |
| 等待你确认远程操作 | 可以改代码，不能代发 |
| 本地草稿已好 | 草稿留在磁盘上 |
| 等待维护者 | 你已经自己去沟通了 |
| 已停止 | 放弃这个仓库 |
