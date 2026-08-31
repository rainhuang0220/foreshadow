# Foreshadow（伏笔）

本地 GitHub 机会雷达 CLI。

**完整说明以英文 [`README.md`](README.md) 为准。** 本文仅为短简介。

## 一句话

Foreshadow 不是 trending。它是一个本地、可解释的短名单：每天最多一次，找出你或许还能帮上忙的公开仓库，最终由你决定。

## 现状

P0 已合入 `main`（`0.1.0`）。P1 增加**持续观察池**：Search 用来发现，Observation 用来留下 longitudinal 证据。正式评分仍是 v1（55 / 35 / 本地 `v7`）。空 Top 5 合法。需人工 review。

## 必读约定（与英文 README 一致）

- Empty Top 5 is OK.
- Top 5 需要**同一仓库**的本地 `v7`（`t-7` ± 1 天），不是全局 snapshot 天数凑满 7。
- Lifetime `stars/age` is not Explosion.
- Token stays on the machine.
- We only GET public GitHub.
- This is not trending.

## 今日机会榜

```bash
uv sync --group dev
FORESHADOW_HOME=… uv run foreshadow board --preview
```

浏览器打开 **http://127.0.0.1:8765/**（仅本机）。先注册/登录，点开项目看阶段 / 证据 / 进入通道 / 推荐入口，再点 **开始进入**。系统会生成本地 Entry Mission，并可 `git clone --depth 1`。**不会**自动向第三方仓库发 Issue / PR。远程操作会停在「等待你的确认」。点 **查看任务** 看已进入的项目。

静态导出：`foreshadow board --preview --export-html`。

当前仍是预览模式：本地快照还不足 v7，正式 Top 5 为空是成功，不是故障。

## 开发

```bash
uv sync --group dev
uv run pytest
```

详见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 与英文 README。
