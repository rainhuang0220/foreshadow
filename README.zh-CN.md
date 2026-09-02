# Foreshadow（伏笔）

**Beta 0.2.4** — 找出未来已经埋伏下的项目。

Foreshadow 不是 trending。它是装在你自己机器上的每日雷达：发现新兴的公开 GitHub 仓库，持续观察还来得及进入的项目，在 Board 上告诉你今天值得看什么、以及为什么。点 **开始进入** 后，它只做本地准备（clone 和计划），然后停下。它不会替你在别人的 GitHub 上发 Issue、评论、PR，也不会 push。

完整说明以英文 [README.md](README.md) 为准。明早走查：[docs/PRODUCT.md](docs/PRODUCT.md)。

## 安装

需要 Python 3.12+。要进入仓库还需要 `git`。

```bash
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4"
# 或
pip install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4"
```

Git 安装不会靠 `uv tool upgrade` 跟到新 tag。换版本：

```bash
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.2.4" --reinstall
```

## Token

只读公开仓库。Token 留在本机，不要写进配置文件。

```bash
export GITHUB_TOKEN=ghp_…    # 无 scope 的 classic PAT，或 gh auth login
```

## 开始

```bash
foreshadow init
foreshadow schedule install    # 可选，本机每日自动跑
foreshadow run                 # 没有装 schedule 就自己跑
foreshadow board               # 打开 http://127.0.0.1:8765/
```

今天已经跑过会跳过，这是正常的。空的正式 Top 5 是成功，不是故障。Explosion 需要同一仓库大约 7 天的观察。

进入：打开候选 → **开始进入**（不要点「记入观察清单」）→ 等本地 clone → 状态变成「等待你确认远程操作」。点「尝试创建 PR」应被拒绝。

```bash
foreshadow doctor
foreshadow status
```
