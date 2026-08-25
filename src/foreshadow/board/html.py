"""Static HTML export. Interactive Board lives in server.py + static/index.html."""

from __future__ import annotations

import html
from datetime import UTC, datetime

from foreshadow.board.present import present_board
from foreshadow.board.schema import BoardDocument


def _e(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _bar(value: int | None, max_v: int = 20) -> str:
    if value is None:
        return '<span class="na">N/A</span>'
    filled = max(0, min(max_v, value))
    return (
        f'<span class="bar" aria-hidden="true">'
        f"{'█' * filled}{'░' * (max_v - filled)}</span>"
        f" <b>{value}</b> / {max_v}"
    )


def _score(v: object) -> str:
    if v is None:
        return "N/A"
    return str(v)


def _activity_score(card: dict) -> str:
    raw = card.get("activity_momentum")
    if raw is None:
        return ""
    return f" {_score(raw)} / 100"


def render_board_html(board: BoardDocument) -> str:
    view = present_board(board)
    preview = view["mode"] != "official"
    mode_class = "prov" if preview else "off"
    rows: list[str] = []
    for card in view["candidates"]:
        detail = card["detail"]
        dims = "".join(
            f"<tr><th>{_e(d['label'])}</th>"
            f"<td>{_bar(d['value'])}</td></tr>"
            + (
                "".join(
                    f"<tr class='ev'><td colspan='2'>{_e(line)}</td></tr>"
                    for line in d["evidence"][:4]
                )
                if d["evidence"]
                else ""
            )
            for d in detail["dimensions"]
        )
        reviewers = []
        for rev in detail["reviewers"]:
            rdims = "".join(
                f"<li>{_e(d['label'])} "
                f"{'N/A' if d['na'] else str(d['value']) + '/20'}</li>"
                for d in rev["dimensions"]
            )
            reviewers.append(
                f"<section class='reviewer'><h4>{_e(rev['label'])} · "
                f"{_score(rev['score'])} / 100</h4>"
                f"<p class='muted'>关注：{' · '.join(_e(x) for x in rev['focus'])}</p>"
                f"<ul>{rdims}</ul></section>"
            )
        why = detail.get("why_selected") or detail.get("why_excluded") or []
        why_title = (
            "为什么推荐" if detail.get("why_selected") else "为什么没有进入 Top 5"
        )
        why_html = "".join(f"<li>{_e(x)}</li>" for x in why)
        gh = _e(card["html_url"])
        disagree = detail["disagreement"]
        chair = detail["chair"]
        rows.append(
            f"""
<details class="row" id="{_e(card["full_name"])}">
  <summary>
    <span class="rk">#{card["rank"]}</span>
    <span class="name">{_e(card["full_name"])}</span>
    <span class="final">{_score(card["final_score"])}</span>
    <span class="mini">趋势 {_score(card["trend"])} · 社区 {_score(card["community"])} · 贡献 {_score(card["contributor"])}</span>
    <span class="head">{_e(card["headline"])}</span>
    <span class="st">{_e(card["status_zh"])}</span>
  </summary>
  <div class="drawer">
    <p><strong>当前排名：</strong>#{card["rank"]}
       · <strong>最终综合评分：</strong>{_score(card["final_score"])}
       · <span class="stamp">{_e(card["rank_kind_zh"])}</span>
       {" · 不是正式预测" if card["not_official"] else ""}</p>
    <p>数据完整度：{_e(card.get("data_completeness_zh") or "低")} · 置信度：{_e(card.get("p0_confidence_zh") or "低")}（完整度低不是低分）</p>
    <p>活跃度：{_e(card.get("activity_class_zh") or "未知")}{_activity_score(card)}</p>
    <p>近 7 天提交：{_score(card.get("commits_7d"))} · 近 30 天提交：{_score(card.get("commits_30d"))}
       · 近 30 天 Release：{_score(card.get("releases_30d"))} · 近 7 天贡献者：{_score(card.get("recent_contributors_7d"))}
       · 活动集中度：{_score(card.get("activity_concentration"))}</p>
    <p class="muted">{_e(card.get("activity_note") or "活跃度反映开发与社区活动，不代表 Star 增长。")}</p>
    <p>阶段：{_e(card.get("s1_stage") or "—")} · {_e(card.get("s1_pool_zh") or "")}</p>
    <p>早期程度：{_score(card.get("s1_earlyness"))} · 证据强度：{_score(card.get("s1_evidence"))}
       · 机会窗口：{_score(card.get("s1_window"))}</p>
    <p>早期加分：{_e("；".join(card.get("s1_earlyness_plus") or []) or "—")}</p>
    <p>早期扣分：{_e("；".join(card.get("s1_earlyness_minus") or []) or "—")}</p>
    <p>证据加分：{_e("；".join(card.get("s1_evidence_plus") or []) or "—")}</p>
    <p>证据不足：{_e("；".join(card.get("s1_evidence_minus") or []) or "—")}</p>
    <p class="muted">Star 只是规模观察，不是区间门槛，也不是否决。</p>
    <p><a class="gh" href="{gh}" target="_blank" rel="noopener noreferrer">打开 GitHub ↗</a>
       Stars {_e(card["stars"])} · Forks {_e(card["forks"])} · 贡献者 {_e(card["contributors"])}
       · Open Issues {_e(card["open_issues"])}</p>
    <h4>五维评分</h4>
    <table class="dims">{dims}</table>
    <h4>三个独立评审视角</h4>
    {"".join(reviewers)}
    <h4>评审分歧：{_e(disagree["level_zh"])}</h4>
    <p>趋势 {_score(disagree["trend"])} · 社区 {_score(disagree["community"])} · 贡献 {_score(disagree["contributor"])}</p>
    <p>{_e(disagree["explain"])}</p>
    <h4>主审</h4>
    <p>趋势 {_score(card["trend"])} · 社区 {_score(card["community"])} · 贡献 {_score(card["contributor"])} · 主审 {_score(card["chair"])}。{_e(chair["weight_note"])}</p>
    <p>{_e(chair["judgment"])}</p>
    <h4>{_e(why_title)}</h4>
    <ul>{why_html}</ul>
    <p><strong>风险：</strong>{_e(chair["main_risk"])}</p>
  </div>
</details>
"""
        )
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    counts = view["counts"]
    body = "".join(rows) or "<p>今日没有候选。空 Top 5 是成功。</p>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>伏笔 · 今日机会榜 · {_e(view["date"])}</title>
<style>
:root {{
  --ink: #1a140c;
  --paper: #f3ead4;
  --rule: #cbb890;
  --cinnabar: #b8392a;
  --jade: #2f5d45;
  --muted: #6d6254;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.5 "Songti SC", "STSong", "Iowan Old Style", Palatino, serif;
}}
header {{
  padding: 1.6rem 7vw 1rem;
  border-bottom: 3px double var(--ink);
}}
.brand {{ letter-spacing: .28em; font-size: .78rem; }}
h1 {{ margin: .2rem 0 .4rem; font-size: 1.8rem; }}
.mode.prov {{ color: var(--cinnabar); font-weight: 700; }}
.mode.off {{ color: var(--jade); font-weight: 700; }}
.counts {{ display: flex; gap: 1.4rem; flex-wrap: wrap; font-variant-numeric: tabular-nums; }}
.counts b {{ display: block; font-size: 1.45rem; }}
main {{ padding: 1rem 7vw 4rem; }}
.row {{
  border-bottom: 1px solid var(--rule);
  padding: .2rem 0;
}}
.row summary {{
  display: grid;
  grid-template-columns: 3rem 1fr 3.2rem;
  gap: .15rem 1rem;
  cursor: pointer;
  list-style: none;
  padding: .7rem 0;
}}
.row summary::-webkit-details-marker {{ display: none; }}
.rk {{ font-weight: 700; color: var(--cinnabar); }}
.final {{ font-variant-numeric: tabular-nums; font-size: 1.3rem; text-align: right; }}
.name {{ font-size: 1.05rem; }}
.mini, .head, .st {{ grid-column: 2; color: var(--muted); font-size: .88rem; }}
.st {{ color: var(--ink); }}
.drawer {{ padding: 0 0 1.2rem 3rem; max-width: 52rem; }}
.na {{ color: var(--cinnabar); font-style: italic; }}
.stamp {{
  display: inline-block;
  border: 1.5px solid var(--cinnabar);
  color: var(--cinnabar);
  padding: 0 .35rem;
  font-size: .75rem;
  letter-spacing: .12em;
}}
.{mode_class} .stamp {{ border-color: {"var(--cinnabar)" if preview else "var(--jade)"}; color: {"var(--cinnabar)" if preview else "var(--jade)"}; }}
.gh {{
  display: inline-block;
  border-bottom: 1px solid var(--ink);
  text-decoration: none;
  color: inherit;
}}
.bar {{ letter-spacing: -.05em; font-size: .85rem; }}
.muted {{ color: var(--muted); }}
table.dims th {{ text-align: left; padding: .2rem .6rem .2rem 0; }}
footer {{ padding: 1rem 7vw 3rem; color: var(--muted); font-size: .85rem; }}
@media (max-width: 800px) {{
  header, main, footer {{ padding-left: 1rem; padding-right: 1rem; }}
  .drawer {{ padding-left: 0; }}
}}
</style>
</head>
<body class="{mode_class}">
<header>
  <div class="brand">FORESHADOW · 伏笔</div>
  <h1>今日机会审查</h1>
  <p>{_e(view["date"])} · <span class="mode {mode_class}">{_e(view["mode_zh"])}｜{_e(view["mode_reason_zh"])}</span>
     {" · 不是正式预测" if preview else ""}</p>
  <div class="counts">
    <div><b>{counts["discovered"]}</b>发现项目</div>
    <div><b>{counts["shortlisted"]}</b>候选项目</div>
    <div><b>{counts["deep_reviewed"]}</b>深度评审</div>
    <div><b>{counts["official_top5"]}</b>正式 Top 5</div>
    <div><b>{counts["provisional"]}</b>预览候选</div>
  </div>
  <p class="muted">默认按综合评分从高到低。展开一行才看详情。静态导出不含登录状态。</p>
</header>
<main>
<h2>今日候选榜</h2>
{body}
</main>
<footer>生成于 {generated} UTC · 快照天数 {board.snapshot_days} · 交互式工作台请运行 <code>foreshadow board</code></footer>
</body>
</html>
"""
