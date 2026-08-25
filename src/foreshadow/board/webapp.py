"""Inlined Chinese Review Board SPA. No frontend build step."""

from __future__ import annotations

APP_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>伏笔 · 今日机会榜</title>
<style>
:root {
  --ink: #f3ead4;
  --ink-dim: #b7aa93;
  --night: #12100c;
  --night-2: #1b1711;
  --rule: rgba(214, 186, 122, .28);
  --cinnabar: #e24a32;
  --cinnabar-dim: #9a2f22;
  --jade: #7ea586;
  --gold: #d6ba7a;
  --paper: #f4ead3;
  --paper-ink: #1a140c;
  --paper-muted: #6d6254;
  --font-display: "Songti SC", "STSong", "Noto Serif CJK SC", "Iowan Old Style", Palatino, serif;
  --font-ui: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Songti SC", sans-serif;
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  background:
    radial-gradient(1200px 500px at 10% -10%, rgba(226,74,50,.16), transparent 50%),
    radial-gradient(900px 400px at 100% 0%, rgba(214,186,122,.08), transparent 45%),
    var(--night);
  color: var(--ink);
  font-family: var(--font-ui);
  letter-spacing: .01em;
}
body::before {
  content: "";
  pointer-events: none;
  position: fixed; inset: 0;
  opacity: .07;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='80' height='80'><filter id='n'><feTurbulence baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  mix-blend-mode: overlay;
}
a { color: inherit; }
button, input, select { font: inherit; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 1.4rem 1.5rem 4rem; }
.brand {
  font-family: var(--font-display);
  letter-spacing: .42em;
  font-size: .72rem;
  color: var(--gold);
}
h1, h2, h3, h4 { font-family: var(--font-display); font-weight: 600; }
.mast h1 { font-size: 2.1rem; margin: .25rem 0 .3rem; letter-spacing: .08em; }
.date { color: var(--ink-dim); }
.ribbon {
  display: inline-flex; align-items: center; gap: .6rem;
  margin: .7rem 0 1rem;
  padding: .35rem .7rem;
  border: 1px solid var(--cinnabar);
  color: var(--cinnabar);
  letter-spacing: .18em;
  font-size: .78rem;
  transform: rotate(-1.2deg);
  background: rgba(226,74,50,.08);
}
.ribbon.official {
  border-color: var(--jade); color: var(--jade);
  background: rgba(126,165,134,.1);
  transform: none;
}
.counts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0,1fr));
  gap: .8rem;
  margin: 1.1rem 0 1.4rem;
}
.counts div {
  border-top: 1px solid var(--rule);
  padding-top: .45rem;
  color: var(--ink-dim);
  font-size: .78rem;
}
.counts b {
  display: block;
  font-family: var(--font-display);
  font-size: 1.55rem;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.toolbar {
  display: flex; flex-wrap: wrap; gap: .6rem;
  align-items: center;
  margin: 0 0 1rem;
}
.toolbar label { color: var(--ink-dim); font-size: .82rem; }
select {
  background: var(--night-2);
  color: var(--ink);
  border: 1px solid var(--rule);
  padding: .35rem .5rem;
}
.list { border-top: 1px solid var(--rule); }
.row {
  display: grid;
  grid-template-columns: 3.2rem minmax(0,1fr) 7.2rem;
  gap: .25rem 1rem;
  padding: .85rem 0;
  border-bottom: 1px solid var(--rule);
  cursor: pointer;
  align-items: start;
}
.row:hover { background: rgba(243,234,212,.03); }
.row.active { background: rgba(226,74,50,.07); }
.rk {
  font-family: var(--font-display);
  color: var(--cinnabar);
  font-size: 1.15rem;
}
.nm { font-size: 1.05rem; word-break: break-all; }
.final {
  font-family: var(--font-display);
  font-size: 1.55rem;
  font-variant-numeric: tabular-nums;
  text-align: right;
  line-height: 1;
}
.sub { grid-column: 2; color: var(--ink-dim); font-size: .86rem; }
.sub b { color: var(--ink); font-weight: 500; }
.gh-mini {
  margin-left: .6rem;
  font-size: .78rem;
  color: var(--gold);
  text-decoration: none;
  border-bottom: 1px solid rgba(214,186,122,.5);
}
.auth {
  max-width: 26rem;
  margin: 3rem auto;
  background: var(--paper);
  color: var(--paper-ink);
  padding: 1.6rem 1.5rem 1.8rem;
  box-shadow: 8px 16px 0 rgba(0,0,0,.35);
}
.auth h2 { margin: 0 0 .8rem; }
.auth input {
  width: 100%;
  margin: .25rem 0 .7rem;
  padding: .55rem .6rem;
  border: 1px solid #cbb890;
  background: #faf6ea;
}
.auth .rowbtns { display: flex; gap: .5rem; }
.auth button, .btn {
  border: 1px solid currentColor;
  background: transparent;
  padding: .4rem .75rem;
  cursor: pointer;
}
.auth button.primary, .btn.primary {
  background: var(--paper-ink);
  color: var(--paper);
  border-color: var(--paper-ink);
}
.err { color: var(--cinnabar-dim); min-height: 1.2rem; }
.who {
  display: flex; justify-content: space-between; align-items: baseline;
  color: var(--ink-dim); font-size: .85rem; margin-bottom: .4rem;
}
.who button { color: var(--gold); background: none; border: 0; cursor: pointer; }
.drawer-bg {
  position: fixed; inset: 0;
  background: rgba(8,6,4,.55);
  opacity: 0; pointer-events: none;
  transition: opacity .18s ease;
}
.drawer-bg.on { opacity: 1; pointer-events: auto; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: min(560px, 100%);
  background: var(--paper);
  color: var(--paper-ink);
  transform: translateX(104%);
  transition: transform .22s ease;
  overflow: auto;
  padding: 1.3rem 1.35rem 3rem;
  box-shadow: -16px 0 40px rgba(0,0,0,.4);
}
.drawer.on { transform: translateX(0); }
.drawer h2 { margin: .2rem 0 .15rem; font-size: 1.35rem; word-break: break-all; }
.close {
  float: right; border: 0; background: none; cursor: pointer; font-size: 1.2rem;
}
.pill {
  display: inline-block;
  border: 1.5px solid var(--cinnabar);
  color: var(--cinnabar);
  padding: 0 .4rem;
  font-size: .72rem;
  letter-spacing: .14em;
  margin-left: .35rem;
}
.pill.ok { border-color: #2f5d45; color: #2f5d45; }
.meta { color: var(--paper-muted); font-size: .88rem; }
.gh {
  display: inline-block;
  margin: .7rem 0 1rem;
  padding: .35rem .7rem;
  background: var(--paper-ink);
  color: var(--paper);
  text-decoration: none;
  letter-spacing: .08em;
}
.dim { margin: .35rem 0 .7rem; }
.dim .lab { display: flex; justify-content: space-between; }
.track {
  height: .55rem;
  background: #e3d6b6;
  margin-top: .2rem;
  overflow: hidden;
}
.fill { height: 100%; background: var(--cinnabar-dim); }
.fill.na { width: 0; }
.ev { margin: .2rem 0 .8rem 0; padding-left: 1rem; color: var(--paper-muted); font-size: .88rem; }
.rev {
  border-top: 1px dashed #cbb890;
  padding: .8rem 0 .2rem;
}
.rev h3 { margin: 0 0 .25rem; }
.focus { color: var(--paper-muted); font-size: .82rem; }
.decide label {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  margin: .25rem .7rem .25rem 0;
  cursor: pointer;
}
.empty { color: var(--ink-dim); padding: 2rem 0; }
button.primary {
  background: var(--paper-ink);
  color: var(--paper);
  border: 1px solid var(--paper-ink);
  padding: .4rem .75rem;
  cursor: pointer;
}
button.ghost, .toolbar button {
  background: transparent;
  color: inherit;
  border: 1px solid var(--rule);
  padding: .35rem .7rem;
  cursor: pointer;
}
.toolbar button { color: var(--ink); }
.mission-list { margin: 0 0 1.2rem; border-top: 1px solid var(--rule); }
.mission-list .row { cursor: default; grid-template-columns: minmax(0,1fr) 7rem; }
details.git-ops { margin: .8rem 0; color: var(--paper-muted); font-size: .86rem; }
.warn {
  border: 1px solid var(--cinnabar);
  color: var(--cinnabar-dim);
  padding: .55rem .7rem;
  margin: .8rem 0;
  font-size: .88rem;
}
@media (max-width: 900px) {
  .counts { grid-template-columns: repeat(2, 1fr); }
  .wrap { padding: 1rem 1rem 5rem; }
  .row { grid-template-columns: 2.4rem minmax(0,1fr); }
  .final { text-align: left; }
}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const $ = (sel, el=document) => el.querySelector(sel);
const state = {
  user: null,
  board: null,
  sort: "final_score",
  filter: "all",
  open: null,
  auth: "login",
  error: "",
  busy: false,
  mission: null,
  missions: [],
  showMissions: false,
  portfolio: null,
};

async function api(path, opts={}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers||{}) },
    ...opts,
  });
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch {}
  if (!res.ok) {
    const err = new Error(data.error || ("HTTP " + res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"
  }[c]));
}
function n(v) { return v == null ? "N/A" : String(v); }

function applySortFilter(cands) {
  let rows = cands.slice();
  const f = state.filter;
  if (f === "top20") rows = rows.slice(0, 20);
  if (f === "top10") rows = rows.filter(c => c.rank && c.rank <= 10);
  if (f === "top5") rows = rows.filter(c => c.status === "official" || c.status === "preview_top");
  if (f === "excluded") rows = rows.filter(c => c.status !== "official" && c.status !== "preview_top");
  if (f === "high") rows = rows.filter(c => c.detail && c.detail.disagreement.level === "HIGH");
  const key = state.sort;
  rows.sort((a,b) => {
    const av = key === "rank" ? (a.rank||999) : -(a[key] ?? -1);
    const bv = key === "rank" ? (b.rank||999) : -(b[key] ?? -1);
    if (av !== bv) return av - bv;
    return (a.rank||0) - (b.rank||0);
  });
  return rows;
}

function bar(val, max=20) {
  if (val == null) return `<div class="track"><div class="fill na"></div></div>`;
  const pct = Math.max(0, Math.min(100, (val/max)*100));
  return `<div class="track"><div class="fill" style="width:${pct}%"></div></div>`;
}

function authView() {
  const t = state.auth === "register";
  return `
  <header class="mast">
    <div class="brand">FORESHADOW · 伏笔</div>
    <h1>今日机会审查</h1>
    <p class="date">人审工作台。先登录，再看今日候选榜。</p>
  </header>
  <form class="auth" onsubmit="return submitAuth(event)">
    <h2>${t ? "注册" : "登录"}</h2>
    ${t ? `<label>用户名</label><input name="username" autocomplete="username" required>` : `<label>用户名或邮箱</label><input name="username" autocomplete="username" required>`}
    ${t ? `<label>邮箱</label><input name="email" type="email" autocomplete="email" required>` : ""}
    <label>密码</label><input name="password" type="password" autocomplete="${t?"new-password":"current-password"}" required minlength="8">
    <p class="err">${esc(state.error)}</p>
    <div class="rowbtns">
      <button class="primary" type="submit">${t ? "注册并进入" : "登录"}</button>
      <button type="button" onclick="state.auth='${t?"login":"register"}';state.error='';render()">${t ? "已有账号" : "注册"}</button>
    </div>
  </form>`;
}

function header(board) {
  const preview = board.mode !== "official";
  const c = board.counts;
  return `
  <div class="who">
    <span>${esc(state.user.username)}</span>
    <button type="button" onclick="logout()">退出</button>
  </div>
  <header class="mast">
    <div class="brand">FORESHADOW · 伏笔</div>
    <h1>今日机会审查</h1>
    <p class="date">${esc(board.date)}</p>
    <div class="ribbon ${preview ? "" : "official"}">
      ${preview ? "预览模式｜历史不足 v7｜不是正式预测" : "正式模式｜v7 历史完整"}
    </div>
    <p class="meta">${state.portfolio ? ("已进入任务 " + n(state.portfolio.entered) + " · 任务总数 " + n(state.portfolio.missions) + " · 远程 GitHub 写入默认关闭") : ""}</p>
    <p class="meta">扫描由每日命令运行，本页不会在后台写 GitHub。不要把「停止」当成「进入」。</p>
    <div class="counts">
      <div><b>${c.discovered}</b>发现项目</div>
      <div><b>${c.shortlisted}</b>候选项目</div>
      <div><b>${c.deep_reviewed}</b>深度评审</div>
      <div><b>${c.official_top5}</b>正式 Top 5</div>
      <div><b>${c.provisional}</b>预览候选</div>
    </div>
  </header>`;
}

function listView(board) {
  const rows = applySortFilter(board.candidates || []);
  if (!rows.length) return `<p class="empty">今日没有可展示的候选。空 Top 5 是成功。</p>`;
  return rows.map(c => `
    <div class="row ${state.open===c.full_name?"active":""}" onclick="openCard('${esc(c.full_name)}')">
      <div class="rk">#${esc(c.rank)}</div>
      <div>
        <div class="nm">${esc(c.full_name)}
          <a class="gh-mini" href="${esc(c.html_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">打开 GitHub ↗</a>
        </div>
      </div>
      <div class="final">${n(c.final_score)}</div>
      <div class="sub">趋势 <b>${n(c.trend)}</b>　社区 <b>${n(c.community)}</b>　贡献 <b>${n(c.contributor)}</b></div>
      <div>
        <button type="button" class="primary" onclick="event.stopPropagation(); ${c.mission_id ? `openExisting(${Number(c.mission_id)||0})` : `startEnter('${esc(c.full_name)}')`}">${c.mission_id ? "查看任务" : "开始进入"}</button>
      </div>
      <div class="sub">${esc(c.headline)} · ${esc(c.status_zh)} · 阶段 ${esc(c.s1_stage || "—")} · 早期 ${n(c.s1_earlyness)} · 证据 ${n(c.s1_evidence)} · 窗口 ${n(c.s1_window)} · ${esc(c.s1_pool_zh || "")} · 活跃度 ${esc(c.activity_class_zh || "未知")}${c.activity_momentum != null ? " " + n(c.activity_momentum) + " / 100" : ""}</div>
    </div>`).join("");
}

function dimBlock(d) {
  const val = d.na ? "N/A" : `${d.value} / ${d.max}`;
  const ev = (d.evidence||[]).map(x => `<li>${esc(x)}</li>`).join("");
  return `<div class="dim">
    <div class="lab"><strong>${esc(d.label)}</strong><span>${val}</span></div>
    ${bar(d.na ? null : d.value)}
    ${d.na ? `<p class="meta">${esc(d.na_note)}</p>` : ""}
    ${ev ? `<ul class="ev">${ev}</ul>` : ""}
  </div>`;
}

function drawerView(card) {
  if (!card) return "";
  const d = card.detail;
  const preview = card.not_official;
  const whyTitle = d.why_selected ? "为什么推荐" : "为什么没有进入 Top 5";
  const why = (d.why_selected || d.why_excluded || []).map(x => `<li>${esc(x)}</li>`).join("");
  const revs = d.reviewers.map(r => `
    <section class="rev">
      <h3>${esc(r.label)}：${n(r.score)} / 100</h3>
      <p class="focus">关注：${r.focus.map(esc).join(" · ")}</p>
      ${r.dimensions.map(x => `<div class="lab"><span>${esc(x.label)}</span><span>${x.na?"N/A":x.value+"/20"}</span></div>${bar(x.na?null:x.value)}`).join("")}
    </section>`).join("");
  const dg = d.disagreement;
  const ch = d.chair;
  const actions = d.review_actions.map(a => `
    <label><input type="radio" name="decision" value="${esc(a.id)}"
      ${card.my_action===a.id?"checked":""}
      onchange="saveReview('${esc(card.full_name)}','${esc(a.id)}')"> ${esc(a.label)}</label>`).join("");
  return `
  <div class="drawer-bg ${state.open?"on":""}" onclick="closeCard()"></div>
  <aside class="drawer ${state.open?"on":""}" role="dialog" aria-label="项目详情">
    <button class="close" type="button" onclick="closeCard()">关闭</button>
    <p class="meta">${esc(card.rank_kind_zh)} · ${preview ? "不是正式预测" : "正式排名"}</p>
    <h2>#${esc(card.rank)} ${esc(card.full_name)}</h2>
    <p><strong>最终综合评分：</strong>${n(card.final_score)}
      <span class="pill ${preview?"":"ok"}">${esc(card.rank_kind_zh)}</span></p>
    <p class="meta">数据完整度：${esc(card.data_completeness_zh || "低")} · 置信度：${esc(card.p0_confidence_zh || "低")}（完整度低不是低分）</p>
    <p class="meta">活跃度：${esc(card.activity_class_zh || "未知")}${card.activity_momentum != null ? "　" + n(card.activity_momentum) + " / 100" : ""}</p>
    <p class="meta">近 7 天提交：${n(card.commits_7d)} · 近 30 天提交：${n(card.commits_30d)} · 近 30 天 Release：${n(card.releases_30d)} · 近 7 天贡献者：${n(card.recent_contributors_7d)}${card.activity_concentration != null ? " · 活动集中度：" + n(card.activity_concentration) : ""}</p>
    <p class="meta">${esc(card.activity_note || "活跃度反映开发与社区活动，不代表 Star 增长。")}</p>
    <p class="meta">阶段：${esc(card.s1_stage || "—")} · ${esc(card.s1_pool_zh || "")}</p>
    <p class="meta">早期程度：${n(card.s1_earlyness)} · 证据强度：${n(card.s1_evidence)} · 机会窗口：${n(card.s1_window)}</p>
    <p class="meta">早期加分：${esc((card.s1_earlyness_plus || []).join("；") || "—")}</p>
    <p class="meta">早期扣分：${esc((card.s1_earlyness_minus || []).join("；") || "—")}</p>
    <p class="meta">证据加分：${esc((card.s1_evidence_plus || []).join("；") || "—")}</p>
    <p class="meta">证据不足：${esc((card.s1_evidence_minus || []).join("；") || "—")}</p>
    <p class="meta">Star 只是规模观察，不是区间门槛，也不是否决。</p>
    <p class="meta">进入通道：${esc(card.access_class_zh || "未知")}${card.access_score != null ? "　" + n(card.access_score) + " / 100" : ""}（不是贡献者缺口）</p>
    <p class="meta">外部 PR 接受率：${n(card.access_merge_rate)} · 外部 PR 评审率：${n(card.access_review_rate)}</p>
    <p class="meta">
      Stars ${n(card.stars)} · Forks ${n(card.forks)} · 贡献者 ${n(card.contributors)}
      · Open Issues ${n(card.open_issues)}<br/>
      最近活动 ${n(card.last_pushed_at)} · 最近 Release ${n(card.last_release)}
      · 首次发现 ${n(card.first_seen_at)}
    </p>
    <p class="meta"><strong>推荐入口：</strong>${esc(card.strategy_summary_zh || "先阅读再决定")}（${esc(card.strategy_path || "")}） · 难度 ${esc(card.strategy_difficulty || "—")} · 预计 ${esc(card.strategy_effort || "—")}</p>
    <p class="meta">长期参与潜力：${card.strategy_long_term && card.strategy_long_term.score != null ? n(card.strategy_long_term.score) + " / 100" : "N/A"}（不是承诺）</p>
    <ol class="ev">${(card.strategy_steps_zh||[]).map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    <p>
      <button type="button" class="primary" onclick="event.stopPropagation(); ${card.mission_id ? `openExisting(${Number(card.mission_id)||0})` : `startEnter('${esc(card.full_name)}')`}">${card.mission_id ? "查看任务" : "开始进入"}</button>
      <a class="gh" href="${esc(card.html_url)}" target="_blank" rel="noopener noreferrer">查看项目 ↗</a>
    </p>
    <h3>五维评分</h3>
    ${d.dimensions.map(dimBlock).join("")}
    <h3>三个独立评审视角</h3>
    ${revs}
    <h3>评审分歧：${esc(dg.level_zh)}</h3>
    <p>趋势 ${n(dg.trend)} · 社区 ${n(dg.community)} · 贡献 ${n(dg.contributor)}</p>
    <p>${esc(dg.explain)}</p>
    <h3>最终综合评分：${n(card.final_score)}</h3>
    <p>趋势评审 ${n(card.trend)} · 社区评审 ${n(card.community)} · 贡献评审 ${n(card.contributor)} · 主审 ${n(card.chair)}</p>
    <p class="meta">${esc(ch.weight_note)}</p>
    <p><strong>综合判断：</strong>${esc(ch.judgment)}</p>
    <h3>${esc(whyTitle)}</h3>
    <ul>${why}</ul>
    <p><strong>风险：</strong>${esc(ch.main_risk)}</p>
    <h3>我的决定</h3>
    <div class="decide">${actions}</div>
  </aside>`;
}

function boardView() {
  const b = state.board;
  return `
  ${header(b)}
  <div class="toolbar">
    <label>排序
      <select onchange="state.sort=this.value;render()">
        <option value="final_score" ${state.sort==="final_score"?"selected":""}>综合评分</option>
        <option value="trend" ${state.sort==="trend"?"selected":""}>趋势评分</option>
        <option value="community" ${state.sort==="community"?"selected":""}>社区评分</option>
        <option value="contributor" ${state.sort==="contributor"?"selected":""}>贡献评分</option>
        <option value="rank" ${state.sort==="rank"?"selected":""}>排名</option>
      </select>
    </label>
    <label>筛选
      <select onchange="state.filter=this.value;render()">
        <option value="all" ${state.filter==="all"?"selected":""}>全部</option>
        <option value="top20" ${state.filter==="top20"?"selected":""}>Top 20</option>
        <option value="top10" ${state.filter==="top10"?"selected":""}>Top 10</option>
        <option value="top5" ${state.filter==="top5"?"selected":""}>Top 5</option>
        <option value="excluded" ${state.filter==="excluded"?"selected":""}>未入选</option>
        <option value="high" ${state.filter==="high"?"selected":""}>高分歧</option>
      </select>
    </label>
    <span class="date">当前按${state.sort==="final_score"?"综合评分":"所选指标"}排序</span>
    <button type="button" onclick="loadMissions()">查看任务</button>
  </div>
  ${state.showMissions ? missionListView() : ""}
  <h2>今日候选榜</h2>
  <div class="list">${listView(b)}</div>
  ${drawerView((b.candidates||[]).find(c => c.full_name === state.open))}
  ${missionView(state.mission)}
  `;
}

function missionListView() {
  const rows = state.missions || [];
  if (!rows.length) return `<p class="empty">还没有进入任务。在榜上点「开始进入」。</p>`;
  return `<div class="mission-list">${rows.map(m => `
    <div class="row">
      <div>
        <div class="nm">${esc(m.full_name)}</div>
        <div class="sub">状态 ${esc(m.status||"—")} · ${esc(m.next_step_zh || "")}</div>
      </div>
      <div>
        <button type="button" class="primary" onclick="openMission(${Number(m.id)||0})">打开</button>
      </div>
    </div>`).join("")}</div>`;
}

function missionView(m) {
  if (!m) return "";
  const steps = (m.steps_zh||[]).map((x,i) => `<li><strong>第 ${i+1} 步</strong> ${esc(x)}</li>`).join("");
  const git = (m.git_ops_zh||[]).map(x => `<li>${esc(x)}</li>`).join("");
  const clone = m.clone && m.clone.status ? m.clone.status : "尚未 clone";
  const id = m.id;
  return `
  <div class="drawer-bg on" onclick="state.mission=null;render()"></div>
  <aside class="drawer on" role="dialog" aria-label="进入任务">
    <button class="close" type="button" onclick="state.mission=null;render()">关闭</button>
    <p class="brand">FORESHADOW ENTRY MISSION</p>
    <h2>${esc(m.full_name)}</h2>
    <p class="meta">阶段 ${esc(m.stage||"—")} · 机会 ${n(m.opportunity_window)} · 进入通道 ${n(m.access)}</p>
    <p><strong>为什么现在进入：</strong>${esc((m.why_now||[]).join("；") || "—")}</p>
    <p><strong>推荐入口：</strong>${esc(m.strategy && m.strategy.summary_zh || m.strategy && m.strategy.path || "—")}</p>
    <p class="meta">难度 ${esc(m.difficulty||"—")} · 预计 ${esc(m.effort||"—")} · 状态 ${esc(m.status_zh || m.status || "—")}</p>
    <p class="meta"><strong>下一步：</strong>${esc(m.next_step_zh || "先阅读推荐入口")}</p>
    <p class="warn">${esc(m.remote_blocked || "等待你的确认才能执行任何远程 GitHub 操作。")}</p>
    <p><strong>第一步：</strong>${esc((m.steps_zh && m.steps_zh[0]) || "阅读本地 FORESHADOW.md")}</p>
    <h3>行动计划</h3>
    <ol>${steps}</ol>
    <p class="meta">本地目录：${esc(m.local_path || "尚未准备")} · clone：${esc(clone)}</p>
    <p class="meta">本地分支：${esc((m.branch && m.branch.name) || (m.clone && m.clone.ok ? "foreshadow/entry" : "—"))} · 草稿：${esc(m.draft_path || "ISSUE_DRAFT.md")}</p>
    <p>
      <button type="button" class="primary" onclick="setupLocal(${id})">准备本地环境</button>
      <button type="button" onclick="markEvent(${id}, 'abandoned')">停止任务</button>
    </p>
    <p>
      <button type="button" onclick="markEvent(${id}, 'maintainer_replied')">维护者已回复</button>
      <button type="button" onclick="markEvent(${id}, 'pr_merged')">我看到已被合并</button>
      <button type="button" onclick="markEvent(${id}, 'user_submitted')">我已自行提交</button>
    </p>
    <details class="git-ops">
      <summary>展开底层 Git 操作</summary>
      <ul>${git || "<li>仅本地 clone / 分支 / commit</li>"}</ul>
    </details>
    <button type="button" onclick="refuseRemote()">尝试创建 PR（应被拒绝）</button>
  </aside>`;
}

function render() {
  const root = document.getElementById("app");
  if (!state.user) root.innerHTML = authView();
  else if (!state.board) root.innerHTML = `<p class="empty">正在打开今日机会榜…</p>`;
  else root.innerHTML = boardView();
}

async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;
    if (state.user) await loadBoard();
  } catch (e) {
    state.user = null;
  }
  render();
}

async function loadBoard() {
  state.board = await api("/api/board");
  try { state.portfolio = await api("/api/portfolio"); } catch { state.portfolio = null; }
}

async function submitAuth(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const body = Object.fromEntries(fd.entries());
  state.error = "";
  try {
    const path = state.auth === "register" ? "/api/register" : "/api/login";
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    state.user = data.user;
    await loadBoard();
  } catch (e) {
    state.error = e.message;
  }
  render();
  return false;
}

async function logout() {
  await api("/api/logout", { method: "POST", body: "{}" });
  state.user = null;
  state.board = null;
  state.open = null;
  render();
}

function openCard(name) { state.open = name; render(); }
function closeCard() { state.open = null; render(); }

async function startEnter(name) {
  try {
    const data = await api("/api/mission", { method: "POST", body: JSON.stringify({ full_name: name }) });
    state.mission = data.mission;
    render();
    if (data.mission && data.mission.id) await setupLocal(data.mission.id);
  } catch (e) { alert(e.message); }
}

async function setupLocal(id) {
  try {
    const data = await api("/api/mission/setup", { method: "POST", body: JSON.stringify({ id }) });
    state.mission = data.mission;
    if (state.portfolio) try { state.portfolio = await api("/api/portfolio"); } catch {}
    render();
  } catch (e) { alert(e.message); }
}

async function loadMissions() {
  try {
    const data = await api("/api/missions");
    state.missions = data.missions || [];
    state.showMissions = true;
    render();
  } catch (e) { alert(e.message); }
}

function openMission(id) {
  const found = (state.missions || []).find(x => x.id === id);
  if (found) { state.mission = found; render(); }
}

async function openExisting(id) {
  try {
    const data = await api("/api/missions");
    state.missions = data.missions || [];
    state.showMissions = true;
    openMission(id);
  } catch (e) { alert(e.message); }
}

async function markEvent(id, event) {
  try {
    const data = await api("/api/mission/event", { method: "POST", body: JSON.stringify({ id, event }) });
    state.mission = data.mission;
    try { state.portfolio = await api("/api/portfolio"); } catch {}
    render();
  } catch (e) { alert(e.message); }
}

async function refuseRemote() {
  try {
    const data = await api("/api/mission/remote", { method: "POST", body: JSON.stringify({ action: "create_pr" }) });
    alert(data.error || data.remote_blocked || "已阻止远程操作");
  } catch (e) { alert(e.message); }
}

async function saveReview(repo, action) {
  try {
    await api("/api/review", { method: "POST", body: JSON.stringify({ repo, action }) });
    const card = (state.board.candidates||[]).find(c => c.full_name === repo);
    if (card) { card.my_action = action; }
  } catch (e) {
    alert(e.message);
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeCard();
});
boot();
</script>
</body>
</html>
"""


def render_app_html() -> str:
    return APP_HTML
