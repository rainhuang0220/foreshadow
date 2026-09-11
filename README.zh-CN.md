# Foreshadow（伏笔）

**Beta 0.6.1** — 找出未来已经埋伏下的项目，并准备好一份完整贡献包，只等你点一次提交。

Foreshadow 不是 trending。它是装在你自己机器上的每日雷达：发现新兴的公开 GitHub 仓库，持续观察还来得及进入的项目，在 Board 上告诉你今天值得看什么、以及为什么。**进入**（第一道门）授权本机针对某一个 Issue 工作。**提交到 GitHub**（第二道门）只批准你眼前这一版：必要时 fork、推一个 branch、开一个 PR。评论、review、merge、force push 仍然禁止。

Board 现在展示项目摘要和四项分数（潜力 / 作者先验 / 开放度 / 进入契合），并按期望进入价值排序。名次是序位，不是质量分。正式 Top 5 规则不变；空榜仍是成功。

完整说明以英文 [README.md](README.md) 为准。明早走查：[docs/PRODUCT.md](docs/PRODUCT.md)。

## 安装

需要 Python 3.12+。要进入仓库还需要 `git`。

```bash
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.6.1"
# 或
pip install "git+https://github.com/rainhuang0220/foreshadow.git@v0.6.1"
```

Git 安装不会靠 `uv tool upgrade` 跟到新 tag。换版本：

```bash
uv tool install "git+https://github.com/rainhuang0220/foreshadow.git@v0.6.1" --reinstall
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

进入：打开候选 → **进入**（第一道门，不要点「记入观察清单」）→ 等本机准备到 READY_FOR_HUMAN_SUBMIT → 审核这一版 → **提交到 GitHub**（第二道门，只批准眼前快照）。

```bash
foreshadow doctor
foreshadow status
```
