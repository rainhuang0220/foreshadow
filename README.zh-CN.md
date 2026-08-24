# Foreshadow（伏笔）

本地 GitHub 机会雷达 CLI。

**完整说明以英文 [`README.md`](README.md) 为准。** 本文仅为短简介。

## 一句话

Foreshadow 不是 trending。它是一个本地、可解释的短名单：每天最多一次，找出你或许还能帮上忙的公开仓库，最终由你决定。

## 现状

P0 骨架（`0.0.0`）。可安装，`foreshadow --help` 可用；业务流水线尚未实现。

## 必读约定（与英文 README 一致）

- Empty Top 5 is OK.
- Top 5 requires ~7 daily snapshots (`v7`); day 1 is empty by construction.
- Lifetime `stars/age` is not Explosion.
- Token stays on the machine.
- We only GET public GitHub.
- This is not trending.

## 开发

```bash
uv sync --group dev
uv run pytest
```

详见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 与英文 README。
