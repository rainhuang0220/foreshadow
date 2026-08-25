# Foreshadow（伏笔）

本地 GitHub 机会雷达 CLI。

**完整说明以英文 [`README.md`](README.md) 为准。** 本文仅为短简介。

## 一句话

Foreshadow 不是 trending。它是一个本地、可解释的短名单：每天最多一次，找出你或许还能帮上忙的公开仓库，最终由你决定。

## 现状

P0 已在分支 `p0-implementation` 实现（`0.1.0`）。尚未打 tag，也未发布到 PyPI。GET-only；空 Top 5 合法；Top 5 需约 7 天快照（`v7`）；需人工 review。

## 必读约定（与英文 README 一致）

- Empty Top 5 is OK.
- Top 5 requires ~7 daily snapshots (`v7`); day 1 is empty by construction.
- Lifetime `stars/age` is not Explosion.
- Token stays on the machine.
- We only GET public GitHub.
- This is not trending.

## 今日机会榜

```bash
uv sync --group dev
FORESHADOW_HOME=… uv run foreshadow board --preview
```

浏览器打开 **http://127.0.0.1:8765/**（仅本机）。先注册/登录，点开项目看阶段 / 证据 / 进入通道 / 推荐入口，再点 **开始进入** 生成 Entry Mission。系统只做本地准备，不会自动向第三方仓库发 Issue / PR。

静态导出：`foreshadow board --preview --export-html`。

当前仍是预览模式：本地快照还不足 v7，正式 Top 5 为空是成功，不是故障。

## 开发

```bash
uv sync --group dev
uv run pytest
```

详见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 与英文 README。
