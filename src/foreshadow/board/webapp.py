"""Inlined Chinese Review Board SPA. No frontend build step."""

from __future__ import annotations

APP_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>伏笔 · 今日机会</title>
<link rel="preconnect" href="https://fonts.bunny.net"/>
<link href="https://fonts.bunny.net/css?family=source-serif-4:400,600,700|source-sans-3:400,500,600" rel="stylesheet"/>
<style>
:root {
  --paper: #f6f3ec;
  --ink: #1c1917;
  --ink-dim: #6f6860;
  --ink-faint: #8a837b;
  --rule: rgba(28, 25, 23, .12);
  --rule-strong: rgba(28, 25, 23, .22);
  --cinnabar: #a63d32;
  --cinnabar-dim: #8b342c;
  --ink-blue: #243b55;
  --jade: #3d5c4a;
  --wash: rgba(246, 243, 236, .84);
  --panel: #f8f5ee;
  --gold: #8a6a2f;
  --focus: #8a6a2f;
  --font-display: "Source Serif 4", "Newsreader", "Iowan Old Style", "Songti SC", serif;
  --font-ui: "PingFang SC", "Hiragino Sans GB", "Source Sans 3", sans-serif;
}
* { box-sizing: border-box; }
html, body { min-height: 100%; }
body {
  margin: 0;
  color: var(--ink);
  font-family: var(--font-ui);
  line-height: 1.55;
  background-color: #f6f3ec;
  background-image: url("/static/board-bg.jpg");
  background-size: cover;
  background-attachment: fixed;
  background-position: center;
  background-repeat: no-repeat;
}
body::before {
  content: "";
  pointer-events: none;
  position: fixed;
  inset: 0;
  background: var(--wash);
  z-index: 0;
}
a { color: inherit; }
button, input, select { font: inherit; color: inherit; }
.skip {
  position: absolute;
  left: -999px;
  top: 0;
  z-index: 40;
  padding: .35rem .7rem;
  background: var(--ink);
  color: var(--paper);
  text-decoration: none;
}
.skip:focus, .skip:focus-visible {
  left: 1rem;
  top: 1rem;
}
.wrap {
  position: relative;
  z-index: 1;
  width: min(1080px, 100%);
  margin: 0 auto;
  padding: 2.25rem 2rem 5.5rem;
}
.brand {
  font-family: var(--font-display);
  letter-spacing: .22em;
  font-size: .68rem;
  color: var(--ink-dim);
}
h1, h2, h3, h4 {
  font-family: var(--font-display);
  font-weight: 600;
}
.mast { margin: 0 0 1.7rem; }
.mast h1 {
  font-size: 1.7rem;
  margin: .1rem 0 .45rem;
  letter-spacing: .03em;
  line-height: 1.25;
}
.kicker {
  margin: 0 0 .8rem;
  color: var(--ink-dim);
  font-size: .88rem;
}
.date { color: var(--ink-dim); font-size: .9rem; margin: 0 .85rem 0 0; }
.mast-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .4rem .55rem;
  margin: .1rem 0 .85rem;
}
.ribbon {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  margin: 0;
  padding: .14rem .5rem;
  border: 1px solid var(--cinnabar);
  color: var(--cinnabar);
  letter-spacing: .06em;
  font-size: .7rem;
  background: transparent;
  max-width: 100%;
  line-height: 1.35;
}
.ribbon.official {
  border-color: var(--jade);
  color: var(--jade);
}
.counts {
  display: flex;
  flex-wrap: wrap;
  gap: 1.05rem 1.55rem;
  margin: 1.1rem 0 0;
  padding-top: .85rem;
  border-top: 1px solid var(--rule);
}
.counts div {
  color: var(--ink-dim);
  font-size: .7rem;
  letter-spacing: .04em;
}
.counts b {
  display: block;
  font-family: var(--font-display);
  font-size: 1rem;
  color: var(--ink);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  margin-bottom: .08rem;
}
.counts button.count {
  appearance: none;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  text-align: left;
  cursor: pointer;
  color: var(--ink-dim);
  font-size: .7rem;
  letter-spacing: .04em;
}
.counts button.count.on b { color: var(--cinnabar); }
.spark { font-family: ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: .08em; }
.interp { color: var(--ink-dim); }
.timeline ul { list-style: none; padding: 0; margin: .4rem 0 0; }
.timeline li { display: flex; gap: .7rem; font-size: .86rem; padding: .2rem 0; border-bottom: 1px solid var(--rule); }
.timeline time { color: var(--ink-dim); min-width: 6.5rem; font-variant-numeric: tabular-nums; }
.layers { display: grid; gap: .55rem; margin: .8rem 0 1rem; }
.layers p { margin: 0; font-size: .9rem; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: .55rem .7rem;
  align-items: center;
  margin: 0 0 1.35rem;
}
.toolbar label { color: var(--ink-dim); font-size: .82rem; }
select {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--rule);
  padding: .28rem .45rem;
}
h2 { font-size: 1.05rem; margin: 0 0 .55rem; }
.list { border-top: 1px solid var(--rule); }
.row {
  display: grid;
  grid-template-columns: 2.4rem minmax(0,1fr) auto;
  gap: .2rem 1.05rem;
  padding: 1.15rem .35rem 1.15rem 0;
  border-bottom: 1px solid var(--rule);
  cursor: pointer;
  align-items: start;
}
.row:hover { background: rgba(28, 25, 23, .03); }
.row.active { background: rgba(28, 25, 23, .045); }
.rk {
  font-family: var(--font-display);
  color: var(--cinnabar);
  font-size: .95rem;
  font-variant-numeric: tabular-nums;
  padding-top: .12rem;
}
.nm {
  font-size: 1.02rem;
  word-break: break-all;
  font-weight: 500;
}
.final {
  font-family: var(--font-ui);
  font-size: .78rem;
  font-variant-numeric: tabular-nums;
  text-align: left;
  line-height: inherit;
  font-weight: 400;
  color: var(--ink-faint);
}
.why {
  margin-top: .38rem;
  font-size: .94rem;
  line-height: 1.45;
  color: var(--ink);
}
.why .lbl {
  display: block;
  color: var(--ink-dim);
  font-size: .7rem;
  letter-spacing: .08em;
  margin-bottom: .12rem;
}
.sub {
  color: var(--ink-dim);
  font-size: .82rem;
  margin-top: .22rem;
  line-height: 1.45;
}
.sub.entry { color: var(--ink-dim); }
.sub.entry b { color: var(--ink); }
.sub.scores {
  color: var(--ink-faint);
  font-size: .75rem;
  font-variant-numeric: tabular-nums;
  margin-top: .28rem;
}
.obs {
  display: inline-block;
  margin-left: .45rem;
  font-size: .68rem;
  letter-spacing: .05em;
  color: var(--gold);
  border: 1px solid var(--gold);
  padding: .02rem .34rem;
  vertical-align: .12rem;
  font-weight: 400;
}
.obs.yours {
  color: var(--jade);
  border-color: var(--jade);
}
.row .act {
  grid-column: 3;
  grid-row: 1 / span 2;
  text-align: right;
  align-self: center;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: .4rem;
}
.row .act button { margin-top: 0; }
.row .act button.primary {
  background: var(--ink);
  color: var(--paper);
  border-color: var(--ink);
}
.sub b { color: var(--ink); font-weight: 500; }
.gh-mini {
  margin-left: .55rem;
  font-size: .75rem;
  color: var(--ink-dim);
  text-decoration: none;
  border-bottom: 1px solid var(--rule-strong);
  font-weight: 400;
}
.auth {
  max-width: 24rem;
  margin: 2.4rem auto 0;
  background: var(--panel);
  color: var(--ink);
  padding: 1.5rem 1.4rem 1.6rem;
  border: 1px solid var(--rule);
}
.auth h2 { margin: 0 0 .8rem; font-size: 1.2rem; }
.auth input {
  width: 100%;
  margin: .25rem 0 .7rem;
  padding: .5rem .55rem;
  border: 1px solid var(--rule-strong);
  background: #fffdf8;
}
.auth .rowbtns { display: flex; gap: .5rem; }
.auth button, .btn {
  border: 1px solid currentColor;
  background: transparent;
  padding: .4rem .75rem;
  cursor: pointer;
}
.auth button.primary, .btn.primary {
  background: var(--ink);
  color: var(--paper);
  border-color: var(--ink);
}
.err { color: var(--cinnabar-dim); min-height: 1.2rem; }
.who {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  color: var(--ink-dim);
  font-size: .82rem;
  margin-bottom: 1.35rem;
  padding-bottom: .7rem;
  border-bottom: 1px solid var(--rule);
}
.who button {
  color: var(--ink);
  background: none;
  border: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: .18em;
}
.drawer-bg {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, .2);
  opacity: 0;
  pointer-events: none;
  transition: opacity .18s ease;
  z-index: 20;
}
.drawer-bg.on { opacity: 1; pointer-events: auto; }
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(540px, 100%);
  background: var(--panel);
  color: var(--ink);
  border-left: 1px solid var(--rule-strong);
  transform: translateX(104%);
  transition: transform .22s ease;
  overflow: auto;
  padding: 1.5rem 1.5rem 3.2rem;
  z-index: 21;
}
.drawer.on { transform: translateX(0); }
.drawer h2 { margin: .2rem 0 .35rem; font-size: 1.28rem; word-break: break-all; }
.close {
  float: right;
  border: 0;
  background: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--ink-dim);
}
.pill {
  display: inline-block;
  border: 1px solid var(--cinnabar);
  color: var(--cinnabar);
  padding: 0 .35rem;
  font-size: .7rem;
  letter-spacing: .1em;
  margin-left: .35rem;
}
.pill.ok { border-color: var(--jade); color: var(--jade); }
.meta { color: var(--ink-dim); font-size: .86rem; }
.gh {
  display: inline-block;
  margin: .7rem .5rem 1rem 0;
  padding: .32rem .65rem;
  background: var(--ink);
  color: var(--paper);
  text-decoration: none;
  letter-spacing: .04em;
  font-size: .82rem;
}
.dim { margin: .35rem 0 .7rem; }
.dim .lab { display: flex; justify-content: space-between; }
.track {
  height: .35rem;
  background: rgba(28, 25, 23, .08);
  margin-top: .25rem;
  overflow: hidden;
}
.fill { height: 100%; background: var(--ink); }
.fill.na { width: 0; }
.ev { margin: .2rem 0 .8rem 0; padding-left: 1rem; color: var(--ink-dim); font-size: .86rem; }
.rev {
  border-top: 1px dashed var(--rule-strong);
  padding: .8rem 0 .2rem;
}
.rev h3 { margin: 0 0 .25rem; }
.focus { color: var(--ink-dim); font-size: .82rem; }
.decide label {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  margin: .25rem .7rem .25rem 0;
  cursor: pointer;
}
.empty { color: var(--ink-dim); padding: 2.4rem 0; }
.empty-state {
  padding: 2rem 0 2.6rem;
  max-width: 36rem;
}
.empty-state h2 { font-size: 1.2rem; margin: 0 0 .45rem; }
.empty-state p { color: var(--ink-dim); margin: 0 0 .7rem; }
.empty-state.ok h2 { color: var(--jade); }
.empty-state pre, .banner pre {
  margin: .2rem 0 .8rem;
  padding: .45rem .65rem;
  background: rgba(28, 25, 23, .04);
  border: 1px solid var(--rule);
  overflow-x: auto;
  font-size: .9rem;
}
.banner {
  border: 1px solid var(--rule-strong);
  padding: .85rem 1rem;
  margin: 0 0 1.2rem;
}
.banner h3 { margin: 0 0 .3rem; font-size: 1rem; }
.banner p { margin: .2rem 0; }
.banner ul { margin: .25rem 0 .4rem; padding-left: 1.2rem; }
.banner.ok { border-color: var(--jade); }
.banner.warn {
  border-color: var(--cinnabar);
  color: var(--cinnabar-dim);
}
button.primary {
  background: var(--ink);
  color: var(--paper);
  border: 1px solid var(--ink);
  padding: .38rem .72rem;
  cursor: pointer;
}
button.primary:hover { filter: brightness(1.08); }
:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
button:focus-visible, a:focus-visible, select:focus-visible, input:focus-visible, .row:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
button:disabled {
  opacity: .45;
  cursor: not-allowed;
  filter: none;
}
button.ghost, .toolbar button {
  background: transparent;
  color: inherit;
  border: 1px solid var(--rule-strong);
  padding: .32rem .65rem;
  cursor: pointer;
}
button.ghost:hover, .toolbar button:hover:not(:disabled) {
  background: rgba(28, 25, 23, .04);
}
.toolbar button { color: var(--ink); }
.gh-mini:hover, a.gh:hover { border-bottom-color: var(--ink); }
.mission-list { margin: 0 0 1.4rem; border-top: 1px solid var(--rule); }
.mission-list .row { cursor: default; grid-template-columns: minmax(0,1fr) 7rem; }
details.git-ops { margin: .8rem 0; color: var(--ink-dim); font-size: .86rem; }
.enter-plan {
  background: transparent;
  border: 1px solid var(--rule);
  padding: .85rem .9rem 1rem;
  margin: .7rem 0 1.15rem;
}
.enter-plan h3 { margin: 0 0 .4rem; }
.now {
  font-size: 1.05rem;
  line-height: 1.5;
  margin: .45rem 0 .55rem;
}
ol.plan {
  margin: .55rem 0 1.1rem;
  padding-left: 2.1rem;
  font-size: 1.02rem;
  line-height: 1.55;
  color: var(--ink);
}
ol.plan > li {
  margin: .42rem 0;
  padding-left: .2rem;
}
ol.plan > li::marker {
  color: var(--cinnabar);
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 1.05em;
}
ol.plan > li strong {
  color: var(--ink-blue);
  font-family: var(--font-display);
  letter-spacing: .03em;
  margin-right: .35rem;
}
.drawer button.ghost { border-color: var(--rule-strong); color: var(--ink); }
pre.meta {
  white-space: pre-wrap;
  background: rgba(28, 25, 23, .04);
  border: 1px solid var(--rule);
  padding: .6rem .7rem;
  max-height: 12rem;
  overflow: auto;
}
.warn {
  border: 1px solid var(--cinnabar);
  color: var(--cinnabar-dim);
  padding: .55rem .7rem;
  margin: .8rem 0;
  font-size: .86rem;
  background: transparent;
}
.enter-brief {
  background: transparent;
  border: 1px solid var(--rule);
  padding: .85rem .9rem 1rem;
  margin: .55rem 0 .8rem;
}
.enter-brief p { margin: .28rem 0; }
.enter-brief .now { margin: .5rem 0 .35rem; }
.row .sub.entry {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
ul.checklist {
  list-style: none;
  margin: .35rem 0 1rem;
  padding: 0;
  font-size: .95rem;
}
ul.checklist li { margin: .3rem 0; font-variant-numeric: tabular-nums; }
.obs-panel {
  border: 1px solid var(--rule);
  padding: .7rem .8rem;
  margin: .55rem 0 .9rem;
}
.obs-panel h3 { margin: 0 0 .25rem; font-size: 1rem; }
.contrib-pack, .entry-strat {
  border: 1px solid var(--rule);
  padding: .75rem .85rem;
  margin: .55rem 0 .9rem;
}
.contrib-pack h3, .entry-strat h3 { margin: 0 0 .35rem; font-size: 1rem; }
.chips {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .4rem .55rem;
  margin: .42rem 0 .28rem;
}
.chip {
  border: 1px solid var(--rule);
  padding: .28rem .45rem;
  font-size: .8rem;
  font-variant-numeric: tabular-nums;
  min-width: 0;
  background: transparent;
}
.chip .k {
  display: block;
  color: var(--ink-dim);
  font-size: .68rem;
  letter-spacing: .04em;
  margin-bottom: .04rem;
}
.chip b { font-weight: 600; }
.chip.na, .na { opacity: .7; }
.footnote {
  color: var(--ink-faint);
  font-size: .72rem;
  margin: .32rem 0 0;
  letter-spacing: .02em;
}
.eev {
  margin-top: .22rem;
  font-size: .86rem;
  font-variant-numeric: tabular-nums;
}
.drawer .intro {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: .3rem 0 .5rem;
  font-size: .92rem;
  line-height: 1.5;
}
.score-block { margin: .55rem 0 .85rem; }
.fact-cells {
  display: flex;
  flex-wrap: wrap;
  gap: .35rem;
  margin: .2rem 0 .4rem;
}
.fact-cells .chip { flex: 0 1 auto; }
details.audit {
  margin: 1.1rem 0 0;
  border-top: 1px solid var(--rule);
  padding-top: .7rem;
}
details.audit > summary {
  cursor: pointer;
  font-family: var(--font-display);
  font-size: 1.05rem;
  margin-bottom: .45rem;
}
ol.job-log { margin: .4rem 0 .7rem; padding-left: 1.2rem; font-size: .86rem; }
ol.job-log li { margin: .18rem 0; }
pre.diff {
  white-space: pre-wrap;
  background: rgba(28, 25, 23, .04);
  border: 1px solid var(--rule);
  padding: .6rem .7rem;
  max-height: 22rem;
  overflow: auto;
  font-size: .78rem;
}
@media (min-width: 1440px) {
  .wrap { width: min(1080px, 100%); padding: 2.5rem 2rem 5.5rem; }
}
@media (max-width: 1280px) {
  .wrap { width: min(960px, 100%); }
}
@media (max-width: 1024px) {
  .wrap { width: 100%; padding: 1.6rem 1.4rem 5rem; }
  .mast h1 { font-size: 1.5rem; }
  .drawer { width: min(480px, 100%); }
}
@media (max-width: 768px) {
  body { background-attachment: scroll; }
  .wrap { padding: 1.2rem 1.05rem 5rem; }
  .row { grid-template-columns: 2.1rem minmax(0,1fr); padding-right: 0; }
  .row .act {
    grid-column: 1 / -1;
    grid-row: auto;
    text-align: left;
    align-items: flex-start;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .final { text-align: left; }
  .drawer { width: 100%; border-left: 0; }
  .counts { gap: .85rem 1.2rem; }
  .mast-meta { flex-direction: column; align-items: flex-start; }
}
@media (max-width: 640px) {
  .row { grid-template-columns: 2.1rem minmax(0,1fr); padding-right: 0; }
  .row .act {
    grid-column: 1 / -1;
    grid-row: auto;
    text-align: left;
    align-items: stretch;
    align-self: stretch;
    flex-direction: column;
    width: 100%;
  }
  .row .act button { width: 100%; }
  .chips { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 390px) {
  .wrap { padding: .95rem .8rem 4.5rem; }
  .mast h1 { font-size: 1.22rem; }
  .nm { font-size: .95rem; }
  .why { font-size: .88rem; }
  .toolbar { flex-direction: column; align-items: stretch; }
  .toolbar label, .toolbar button { width: 100%; }
  .who { font-size: .78rem; }
  .row .act { gap: .35rem; }
  .row .act button { flex: 1 1 auto; width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .drawer, .drawer-bg { transition: none; }
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
  public: false,
  allowRegister: true,
  showAuth: false,
  sort: "eev",
  _sortInited: false,
  filter: "all",
  open: null,
  auth: "login",
  githubOAuth: false,
  error: "",
  actionError: "",
  busy: false,
  mission: null,
  missions: [],
  showMissions: false,
  portfolio: null,
  pausedIds: {},
  contributionJobs: [],
  openJob: null,
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
    if (res.status === 401 && path !== "/api/login" && path !== "/api/register") {
      state.user = null;
      // Public anonymous /api/portfolio and /api/missions are 401 by design.
      // Do not wipe a board that already loaded.
      if (!state.public && (path === "/api/board" || path === "/api/me")) {
        state.board = null;
        clearWorkState();
      }
    }
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
function intelOf(c) {
  return (c && c.intel && typeof c.intel === "object") ? c.intel : {};
}
function intelScore(c, key) {
  const intel = intelOf(c);
  let v = (intel[key] != null && intel[key] !== "") ? intel[key]
    : (c && c[key] != null && c[key] !== "" ? c[key] : null);
  if (v != null && typeof v === "object") {
    if (v.score != null && v.score !== "") return v.score;
    if (v.value != null && v.value !== "") return v.value;
    return null;
  }
  return v;
}
function naText(v) {
  return v == null || v === "" ? `<span class="na">N/A</span>` : esc(String(v));
}
function chipsView(c) {
  const items = [
    ["潜力", intelScore(c, "potential")],
    ["创作者先验", intelScore(c, "creator_prior")],
    ["开放度", intelScore(c, "openness")],
    ["进入匹配", intelScore(c, "entry_fit")],
  ];
  return `<div class="chips">${items.map(([k, v]) => {
    const na = v == null || v === "";
    return `<div class="chip${na ? " na" : ""}"><span class="k">${k}</span><b>${na ? "N/A" : esc(String(v))}</b></div>`;
  }).join("")}</div>`;
}
function eevLine(c) {
  const eev = intelScore(c, "eev");
  const dec = c && c.decision ? String(c.decision) : "";
  return `<div class="eev">预期进入 ${naText(eev)}${dec ? " · " + esc(dec) : ""}</div>`;
}
function rankFootnote(c) {
  const official = c && c.status === "official";
  return `<p class="footnote">序 ≠ 质量 · ${official ? "正式入选" : "参考排名"}</p>`;
}
function sortLabel(key) {
  return ({
    eev: "预期进入价值",
    potential: "潜力",
    openness: "开放度",
    entry_fit: "进入匹配",
    rank: "排名",
    final_score: "综合评分",
  })[key] || "所选指标";
}
function sortOptions() {
  const opts = [
    ["eev", "预期进入价值"],
    ["potential", "潜力"],
    ["openness", "开放度"],
    ["entry_fit", "进入匹配"],
    ["rank", "排名"],
    ["final_score", "综合评分"],
  ];
  return opts.map(([v, lab]) =>
    `<option value="${v}" ${state.sort===v?"selected":""}>${lab}</option>`
  ).join("");
}
function opennessSample(c) {
  const intel = intelOf(c);
  const stats = (c && c.community_stats)
    || (intel.community && typeof intel.community === "object" ? intel.community : null)
    || intel.openness_stats
    || {};
  const keys = ["openness_sample_n", "openness_sample", "closed_ext", "sample_n"];
  let found = null;
  for (const k of keys) {
    if (intel[k] != null && intel[k] !== "") { found = intel[k]; break; }
    if (c && c[k] != null && c[k] !== "") { found = c[k]; break; }
    if (stats && stats[k] != null && stats[k] !== "") { found = stats[k]; break; }
  }
  if (found == null && intel.openness && typeof intel.openness === "object" && intel.openness.sample != null) {
    found = intel.openness.sample;
  }
  const nFound = Number(found);
  const openScore = (intel.openness != null && typeof intel.openness !== "object") ? intel.openness : (c && c.openness);
  if ((found == null || nFound === 0) && (openScore == null || openScore === "")) return null;
  return found;
}
function fmtList(v) {
  if (v == null || v === "") return "";
  if (Array.isArray(v)) {
    return v.map(x => {
      if (x == null) return "";
      if (typeof x === "string" || typeof x === "number") return String(x);
      return x.full_name || x.login || x.name || x.title || "";
    }).filter(Boolean).join("、");
  }
  return String(v);
}
function factCells(c) {
  if (!c) return "";
  const d = c.star_delta || {};
  const cells = [];
  if (c.stars != null) {
    cells.push(`<div class="chip"><span class="k">Stars</span><b>${esc(n(c.stars))}</b></div>`);
  }
  if (d.pending) {
    cells.push(`<div class="chip"><span class="k">7日增长</span>${esc((d.observed_days || 0) + " 日观察 · 待确认")}</div>`);
  } else if (d.delta != null) {
    cells.push(`<div class="chip"><span class="k">7日增长</span><b>${esc((d.delta >= 0 ? "+" : "") + d.delta)}</b></div>`);
  }
  return cells.length ? `<div class="fact-cells">${cells.join("")}</div>` : "";
}
function factLine(c) {
  if (!c) return "";
  const bits = [];
  if (c.fact_zh) bits.push(c.fact_zh);
  else if (c.observation_zh) bits.push(c.observation_zh);
  const f = c.fact || {};
  if (f.open_issues != null) bits.push("Issues " + f.open_issues);
  if (f.open_prs != null) bits.push("PRs " + f.open_prs);
  return bits.join(" · ");
}
function entryView(card) {
  const e = card.entry;
  if (!e || !e.recommended) {
    return `<section class="entry-strat">
      <h3>最佳切入点</h3>
      <p class="meta">尚未分析贡献文化与 Issue。分析只用已有快照，不会编造编号。</p>
      ${state.user ? `<button type="button" onclick="analyzeEntry('${esc(card.full_name)}')">分析切入点</button>` : ""}
    </section>`;
  }
  const rec = e.recommended;
  const conf = rec.confidence != null ? Math.round(Number(rec.confidence) * 100) + "%" : "—";
  const alts = (e.alternatives || []).map(p => `<li>备选 ${esc(p.route)}：${esc(p.title)}</li>`).join("");
  const why = (rec.why || []).map(x => `<li>${esc(x)}</li>`).join("");
  const pol = e.policy || {};
  return `<section class="entry-strat">
    <h3>最佳切入点</h3>
    <p><strong>${esc(rec.title || rec.summary_zh)}</strong></p>
    <p class="meta">推荐 ${esc(rec.route)} · 信心 ${esc(conf)} · ${esc(rec.effort || "")} · 风险 ${esc(rec.risk || "")}</p>
    ${why ? `<ul>${why}</ul>` : ""}
    <p class="meta">贡献规范：${pol.wants_issue_first ? "先 Issue 后 PR" : "未强制先 Issue"} · CLA ${pol.cla == null ? "未知" : (pol.cla ? "需要" : "不需要")} · DCO ${pol.dco == null ? "未知" : (pol.dco ? "需要" : "不需要")}</p>
    ${alts ? `<ul>${alts}</ul>` : ""}
    ${state.user ? `<button type="button" class="primary" onclick="startContribution('${esc(card.full_name)}')">开始准备贡献（沙箱，不推送）</button>` : ""}
  </section>`;
}
function logLabel(step) {
  const map = {
    analyzing_repository: "Analyzing repository",
    selected_task: "Selected task",
    preparing_sandbox: "Preparing sandbox",
    install: "Install",
    baseline_tests: "Baseline tests",
    implementing: "Implementing",
    agent_action: "Agent action",
    agent_result: "Agent result",
    agent_finished: "Agent finished",
    tests: "Tests",
    iteration_1: "Iteration 1",
    iteration_1_tests: "Iteration 1 tests",
    iteration_2: "Iteration 2",
    iteration_2_tests: "Iteration 2 tests",
    produce_patch: "Patch",
    qa: "QA",
    ready: "Ready",
    failed: "Failed",
  };
  return map[step] || step || "";
}
function contributionView(card) {
  const pack = (card && card.contribution) || {};
  const job = pack.job || (card && card.contribution_job) || {};
  if (!job.id && !pack.package && !job.status) return "";
  const art = pack.artifact || {};
  const pkg = pack.package || {};
  const log = (job.log || []).map(x => {
    const mark = x.ok === false ? " ✕" : (x.ok === true ? " ✓" : "");
    const cmd = x.command ? ` <code>${esc(String(x.command).slice(0, 160))}</code>` : "";
    const extra = x.returncode != null ? ` exit ${esc(x.returncode)}` : "";
    const out = x.output ? ` <span class="meta">${esc(String(x.output).slice(0, 180))}</span>` : "";
    return `<li>${esc(logLabel(x.step))}${mark}${cmd}${extra}${out}</li>`;
  }).join("");
  const filesN = pkg.files_changed_n != null ? pkg.files_changed_n : (art.files||[]).length;
  const testsOk = pkg.tests && pkg.tests.ok != null ? pkg.tests.ok : art.tests_passed;
  const qa = pkg.qa || (art.qa_ok ? "PASS" : (job.status === "ready" ? "PASS" : (job.status === "failed" ? "FAIL" : "…")));
  const diff = pkg.diff || art.diff || "";
  return `<section class="contrib-pack">
    <h3>贡献准备</h3>
    <p><strong>${esc(job.status_zh || job.status || "")}</strong> · ${esc(pkg.task || art.why || job.full_name || "")}</p>
    <p class="meta">Files changed: ${esc(filesN)} · Tests: ${testsOk ? "passed" : (testsOk === false ? "failed" : "…")} · QA: ${esc(qa)}</p>
    ${pkg.pr_title ? `<p><strong>PR title:</strong> ${esc(pkg.pr_title)}</p>` : ""}
    ${log ? `<ol class="job-log">${log}</ol>` : ""}
    ${diff ? `<details open><summary>Diff</summary><pre class="diff">${esc(String(diff).slice(0, 12000))}</pre></details>` : ""}
    <p class="meta">${esc(pkg.risk || art.risk || "远程 GitHub 写入仍关闭。")} · remote writes: 0 · ${esc(pkg.remote_status || job.remote_status || "WAITING_USER_APPROVAL")}</p>
    <button type="button" disabled>批准并创建 Draft PR（本版关闭）</button>
  </section>`;
}
function timelineView(events) {
  if (!events || !events.length) return "";
  const items = events.map(e => {
    const delta = e.payload && e.payload.delta != null ? e.payload.delta : "";
    return `<li><time>${esc(e.date)}</time> ${esc(e.label_zh || e.kind)}${delta !== "" ? " " + (delta > 0 ? "+" : "") + delta : ""}</li>`;
  }).join("");
  return `<section class="timeline"><h3>观察时间线</h3><ul>${items}</ul></section>`;
}
function accessLine(card) {
  if (!card || card.access_unknown || card.access_score == null) return "未知";
  const zh = card.access_class_zh || "极低";
  const zero = Number(card.access_score) === 0 ? "（已知为 0，不是未知）" : "";
  return zh + "　" + n(card.access_score) + " / 100" + zero;
}

function applySortFilter(cands) {
  let rows = cands.slice();
  const f = state.filter;
  if (f === "observing") rows = rows.filter(c => c.pool === "observing" || c.observation_kind === "watching");
  else if (f === "candidate") rows = rows.filter(c => c.pool === "candidate" || c.status === "preview_top" || c.status === "shortlist" || c.status === "deep");
  else if (f === "official") rows = rows.filter(c => c.status === "official");
  else if (f === "entered") rows = rows.filter(c => c.pool === "entered" || c.mission_id);
  else if (f === "expired") rows = rows.filter(c => c.pool === "expired");
  else if (f === "rising") rows = rows.filter(c => c.star_delta && c.star_delta.delta > 0 && !c.star_delta.pending);
  else if (f === "top20") rows = rows.slice(0, 20);
  else if (f === "top10") rows = rows.filter(c => c.rank && c.rank <= 10);
  else if (f === "top5") rows = rows.filter(c => c.status === "official" || c.status === "preview_top");
  else if (f === "excluded") rows = rows.filter(c => c.status !== "official" && c.status !== "preview_top");
  else if (f === "high") rows = rows.filter(c => c.detail && c.detail.disagreement.level === "HIGH");
  const key = state.sort;
  const intelKeys = { potential: 1, openness: 1, entry_fit: 1, eev: 1 };
  rows.sort((a,b) => {
    if (key === "rank") return (a.rank||999) - (b.rank||999);
    const av = intelKeys[key] ? intelScore(a, key) : a[key];
    const bv = intelKeys[key] ? intelScore(b, key) : b[key];
    const aN = av == null || av === "" || Number.isNaN(Number(av));
    const bN = bv == null || bv === "" || Number.isNaN(Number(bv));
    if (aN && bN) return (a.rank||0) - (b.rank||0);
    if (aN) return 1;
    if (bN) return -1;
    const d = Number(bv) - Number(av);
    if (d) return d;
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
  const gh = state.githubOAuth
    ? `<p><a class="primary" href="/api/auth/github" style="display:inline-flex;text-decoration:none;padding:.45rem .9rem">使用 GitHub 登录</a></p>
       <p class="meta">登录一次即可，会话约 30 天。GitHub 只用来确认你是谁，不会因此获得写仓库权限。</p>`
    : `<p class="meta">公网 GitHub 登录尚未配置。本地开发仍可用密码。</p>`;
  return `
  <header class="mast">
    <div class="brand">伏笔</div>
    <h1>FORESHADOW · 今日机会</h1>
    <p class="kicker">匿名可看今日名单。操作者请用 GitHub 登录一次。</p>
  </header>
  <form class="auth" onsubmit="return submitAuth(event)">
    <h2>${t ? "注册" : "操作者登录"}</h2>
    ${gh}
    ${t ? `<label>用户名</label><input name="username" autocomplete="username" required>` : `<details><summary class="meta">本地密码登录（备用）</summary>
    <label>用户名或邮箱</label><input name="username" autocomplete="username">`}
    ${t ? `<label>邮箱</label><input name="email" type="email" autocomplete="email" required>` : ""}
    <label>密码</label><input name="password" type="password" autocomplete="${t?"new-password":"current-password"}" ${t?"required minlength=8":"minlength=8"}>
    ${t ? "" : `</details>`}
    <p class="err">${esc(state.error)}</p>
    <div class="rowbtns">
      ${t ? `<button class="primary" type="submit">注册并进入</button>` : `<button type="submit">密码登录</button>`}
      ${state.allowRegister ? `<button type="button" onclick="state.auth='${t?"login":"register"}';state.error='';render()">${t ? "已有账号" : "注册"}</button>` : ""}
    </div>
  </form>`;
}

function header(board) {
  const preview = board.mode !== "official";
  const c = board.counts || {};
  const labels = board.count_labels || {};
  const ribbon = board.ribbon_zh || (preview ? "参考排名 · 不是正式入选" : "正式入选");
  return `
  <a class="skip" href="#board-list">跳到今日名单</a>
  <div class="who">
    <span>${state.user ? esc(state.user.github_login || state.user.username) : "只读浏览"}</span>
    ${state.user
      ? `<button type="button" onclick="logout()">退出</button>`
      : (state.githubOAuth
          ? `<a href="/api/auth/github">GitHub 登录</a>`
          : `<button type="button" onclick="state.showAuth=true;render()">登录</button>`)}
  </div>
  <header class="mast">
    <div class="brand">伏笔</div>
    <h1>FORESHADOW · 今日机会</h1>
    <div class="mast-meta">
      <p class="date">${esc(board.date)}</p>
      <div class="ribbon ${preview ? "" : "official"}">${esc(ribbon)}</div>
    </div>
    <p class="meta">${state.portfolio ? ("已进入任务 " + n(state.portfolio.entered) + " · 任务总数 " + n(state.portfolio.missions) + " · 远程 GitHub 写入默认关闭" + (state.portfolio.observed_access ? (state.portfolio.observed_access.score == null ? " · 亲历通道未知（样本少，不是 0，也不改公式）" : " · 亲历通道 " + n(state.portfolio.observed_access.score) + "（不改公式）") : "")) : ""}</p>
    <p class="meta">最近扫描 ${esc((board.run && (board.run.finished_at || board.run.status_zh || board.run.status)) || board.date)} · 本页不会在后台写 GitHub。</p>
    ${state.busy ? `<p class="meta">正在准备本地环境（clone）…</p>` : ""}
    ${state.actionError ? `<p class="warn" role="alert">${esc(state.actionError)}</p>` : ""}
    <div class="counts">
      <button type="button" class="count ${state.filter==="all"?"on":""}" onclick="state.filter='all';render()"><b>${c.discovered ?? 0}</b>${esc(labels.discovered || "发现项目")}</button>
      <button type="button" class="count ${state.filter==="observing"?"on":""}" onclick="state.filter='observing';render()"><b>${c.observing ?? 0}</b>${esc(labels.observing || "持续观察")}</button>
      <button type="button" class="count ${state.filter==="candidate"?"on":""}" onclick="state.filter='candidate';render()"><b>${c.shortlisted ?? 0}</b>${esc(labels.shortlisted || "候选项目")}</button>
      <button type="button" class="count ${state.filter==="official"?"on":""}" onclick="state.filter='official';render()"><b>${c.official_top5 ?? 0}</b>${esc(labels.official_top5 || "正式入选")}</button>
      <button type="button" class="count ${state.filter==="rising"?"on":""}" onclick="state.filter='rising';render()"><b>${c.provisional ?? 0}</b>${esc(labels.provisional || "参考候选")}</button>
    </div>
  </header>
  ${runBanner(board)}`;
}

function runBanner(board) {
  const r = board.run || {};
  const reasons = (r.reasons_zh || []).map(x => `<li>${esc(x)}</li>`).join("");
  if (r.status === "degraded") {
    return `<div class="banner warn" role="status">
      <h3>今日扫描不完整</h3>
      <p>${esc(r.note || "下面的名单不能当作完整结果。")}</p>
      ${reasons ? `<ul>${reasons}</ul>` : ""}
      <p>建议稍后再次运行 <code>foreshadow run</code>，或等待每日调度。</p>
    </div>`;
  }
  if (r.status === "failed") {
    return `<div class="banner warn" role="status">
      <h3>今日扫描失败</h3>
      <p>${esc(r.note || "请运行 foreshadow run 重试。")}</p>
    </div>`;
  }
  if (r.status === "running") {
    return `<div class="banner" role="status">
      <h3>今日扫描仍在进行</h3>
      <p>${esc(r.note || "请稍后再打开看板。")}</p>
    </div>`;
  }
  if ((board.candidates || []).length && board.official_empty_note) {
    return `<div class="banner ok" role="status"><p>${esc(board.official_empty_note)}</p></div>`;
  }
  return "";
}

function intelBanner(board) {
  const note = board && board.no_high_confidence_note;
  if (!note) return "";
  const text = note === true ? "今天没有高置信机会。以下为参考排名。" : String(note);
  return `<div class="banner" role="status"><p>${esc(text)}</p></div>`;
}

function emptyState(board) {
  const e = board.empty || {};
  const title = e.title || "今日没有可展示的项目";
  const body = e.body || "空的入选名单是正常结果，不是故障。";
  const ok = !!e.is_success;
  const action = e.action ? `<pre><code>${esc(e.action)}</code></pre>` : "";
  return `<div class="empty-state${ok ? " ok" : ""}">
    <h2>${esc(title)}</h2>
    <p>${esc(body)}</p>
    ${action}
  </div>`;
}

function cardIntro(c) {
  return (c && (c.project_summary || c.description)) || "";
}
function cardWhy(c) {
  if (c && c.why_now) return Array.isArray(c.why_now) ? c.why_now.filter(Boolean).join("；") : String(c.why_now);
  if (c && c.strategy_why && c.strategy_why[0]) return String(c.strategy_why[0]);
  return (c && c.headline) || "";
}
function missionIsOpen(c) {
  const id = Number(c.mission_id) || 0;
  if (!id) return false;
  const st = String(c.mission_status || "");
  return st !== "ABANDONED" && st !== "MERGED";
}
function enterOrMissionBtn(c) {
  if (!state.user) {
    return `<button type="button" class="ghost" onclick="event.stopPropagation(); state.showAuth=true;render()">登录后进入</button>`;
  }
  const id = Number(c.mission_id) || 0;
  if (id && (cloneOkFor(c) || missionIsOpen(c))) {
    return `<button type="button" class="primary" onclick="event.stopPropagation(); openExisting(${id})" aria-label="查看任务 ${esc(c.full_name)}">查看任务</button>`;
  }
  return `<button type="button" class="primary" ${state.busy?"disabled":""} onclick="event.stopPropagation(); startEnter('${esc(c.full_name)}')" aria-label="开始进入 ${esc(c.full_name)}，在本机准备项目">开始进入</button>`;
}

function rowKey(ev, name) {
  if (ev.target !== ev.currentTarget) return;
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    openCard(name);
  }
}

function listView(board) {
  const all = board.candidates || [];
  const rows = applySortFilter(all);
  if (!rows.length) {
    if (!all.length) return emptyState(board);
    return `<p class="empty">当前筛选下没有项目。把筛选改回「全部」即可看到今日名单。</p>`;
  }
  return rows.map(c => {
    const desc = cardIntro(c);
    const obs = c.observation_zh
      ? `<span class="obs ${c.observation_kind==="yours"?"yours":"watching"}">${esc(c.observation_zh)}</span>`
      : "";
    return `
    <div class="row ${state.open===c.full_name?"active":""}" tabindex="0" role="button" aria-expanded="${state.open===c.full_name?"true":"false"}" onclick="openCard('${esc(c.full_name)}')" onkeydown="rowKey(event, '${esc(c.full_name)}')">
      <div class="rk">#${esc(c.rank)}</div>
      <div>
        <div class="nm">${esc(c.full_name)}${obs}
          <a class="gh-mini" href="${esc(c.html_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">打开 GitHub ↗</a>
        </div>
        ${desc ? `<div class="sub entry">${esc(desc)}</div>` : ""}
        ${chipsView(c)}
        ${eevLine(c)}
        ${rankFootnote(c)}
      </div>
      <div class="act">
        <button type="button" class="ghost" onclick="event.stopPropagation(); openCard('${esc(c.full_name)}')" aria-label="查看详情 ${esc(c.full_name)}">查看详情</button>
        ${state.open===c.full_name ? "" : enterOrMissionBtn(c)}
      </div>
    </div>`;
  }).join("");
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

function drawerWhyNow(card) {
  if (Array.isArray(card.why_now) && card.why_now.length) return card.why_now.join("；");
  if (card.why_now) return String(card.why_now);
  if (card.strategy_why && card.strategy_why.length) return card.strategy_why.join("；");
  return card.headline || "—";
}

function momentumView(card) {
  return `<section>
    <h3>动能</h3>
    <p class="meta">活跃度：${esc(card.activity_class_zh || "未知")}${card.activity_momentum != null ? "　" + n(card.activity_momentum) + " / 100" : ""}</p>
    <p class="meta">近 7 天提交：${n(card.commits_7d)} · 近 30 天提交：${n(card.commits_30d)} · 近 30 天 Release：${n(card.releases_30d)} · 近 7 天贡献者：${n(card.recent_contributors_7d)}${card.activity_concentration != null ? " · 活动集中度：" + n(card.activity_concentration) : ""}</p>
    <p class="meta">${esc(card.activity_note || "活跃度反映开发与社区活动，不代表 Star 增长。")}</p>
  </section>`;
}

function creatorView(card) {
  const cr = (card && card.creator) || intelOf(card).creator;
  if (!cr || typeof cr !== "object") return "";
  const login = cr.login || cr.name || "";
  const past = fmtList(cr.past_repos != null ? cr.past_repos : cr.repos);
  const ok = fmtList(cr.successful != null ? cr.successful : cr.successes);
  const longest = cr.longest_maintained != null ? cr.longest_maintained
    : (cr.longest_maintained_days != null ? cr.longest_maintained_days : cr.longest);
  const lines = [];
  if (login) lines.push(`<p><strong>登录：</strong>${esc(login)}</p>`);
  if (past) lines.push(`<p><strong>过往仓库：</strong>${esc(past)}</p>`);
  if (ok) lines.push(`<p><strong>成功项目：</strong>${esc(ok)}</p>`);
  if (longest != null && longest !== "") lines.push(`<p><strong>最长维护：</strong>${esc(String(longest))}</p>`);
  if (!lines.length) return "";
  return `<section><h3>创作者</h3>${lines.join("")}</section>`;
}

function communityView(card) {
  const intel = intelOf(card);
  const stats = (card && card.community_stats)
    || (intel.community && typeof intel.community === "object" ? intel.community : null)
    || intel.openness_stats
    || {};
  const extra = [];
  if (stats && typeof stats === "object") {
    if (stats.maintainers != null) extra.push(`维护者 ${esc(n(stats.maintainers))}`);
    if (stats.contributors != null) extra.push(`贡献者 ${esc(n(stats.contributors))}`);
    if (stats.external_pr_n != null) extra.push(`外部 PR ${esc(n(stats.external_pr_n))}`);
    if (stats.merge_rate != null) extra.push(`合并率 ${esc(n(stats.merge_rate))}`);
  }
  const openKnown = intel.openness != null && intel.openness !== "";
  const openScore = openKnown ? `${n(intel.openness)} / 100` : "N/A";
  const sample = opennessSample(card);
  return `<section>
    <h3>贡献者开放度</h3>
    <p><strong>开放度：</strong>${openKnown ? esc(openScore) : '<span class="na">N/A</span>'}${openKnown ? "" : ' <span class="na">数据不足，不是 0</span>'}</p>
    <p class="meta">样本：${sample == null ? `<span class="na">N/A</span>` : esc(sample)} 个外部 PR</p>
    ${extra.length ? `<p class="meta">${extra.join(" · ")}</p>` : ""}
    <h3>进入通道</h3>
    <p><strong>进入通道：</strong>${esc(accessLine(card))}</p>
    <p class="meta">外部 PR 接受率：${n(card.access_merge_rate)} · 外部 PR 评审率：${n(card.access_review_rate)}</p>
  </section>`;
}

function thesisView(card) {
  const t = (card && card.thesis) || intelOf(card).thesis;
  if (!t || typeof t !== "object") return "";
  const fields = [
    ["what", "是什么"],
    ["why", "为什么"],
    ["differentiation", "差异化"],
    ["maturity", "成熟度"],
    ["competitors", "竞品"],
    ["risks", "风险"],
  ];
  const parts = [];
  for (const [k, lab] of fields) {
    let v = t[k];
    if (v == null || v === "") continue;
    if (Array.isArray(v)) v = v.filter(Boolean).join("；");
    if (!String(v).trim()) continue;
    parts.push(`<p><strong>${lab}：</strong>${esc(String(v))}</p>`);
  }
  if (!parts.length) return "";
  return `<section><h3>项目论点</h3>${parts.join("")}</section>`;
}

function drawerView(card) {
  if (!card) return "";
  const d = card.detail || {};
  const officialCard = card.status === "official";
  const preview = !officialCard;
  const whyTitle = d.why_selected ? "为什么推荐" : "为什么没有进入 Top 5";
  const why = (d.why_selected || d.why_excluded || []).map(x => `<li>${esc(x)}</li>`).join("");
  const revs = (d.reviewers || []).map(r => `
    <section class="rev">
      <h3>${esc(r.label)}：${n(r.score)} / 100</h3>
      <p class="focus">关注：${(r.focus||[]).map(esc).join(" · ")}</p>
      ${(r.dimensions||[]).map(x => `<div class="lab"><span>${esc(x.label)}</span><span>${x.na?"N/A":x.value+"/20"}</span></div>${bar(x.na?null:x.value)}`).join("")}
    </section>`).join("");
  const dg = d.disagreement || {};
  const ch = d.chair || {};
  const actions = (d.review_actions || []).map(a => `
    <label><input type="radio" name="decision" value="${esc(a.id)}"
      ${card.my_action===a.id?"checked":""}
      onchange="saveReview('${esc(card.full_name)}','${esc(a.id)}')"> ${esc(a.label)}</label>`).join("");
  const intro = cardIntro(card);
  const kindLine = officialCard
    ? (card.rank_footnote_zh || "序 ≠ 质量 · 正式入选")
    : (card.rank_footnote_zh || "参考排名 · 不是正式入选");
  const intel = intelOf(card);
  const conf = card.confidence_zh || intel.confidence_zh || intel.confidence || card.p0_confidence_zh || "";
  const sample = opennessSample(card);
  const spark = card.sparkline
    ? ` <span class="spark" aria-hidden="true">${esc(card.sparkline)}</span>`
    : "";
  return `
  <div class="drawer-bg ${state.open?"on":""}" onclick="closeCard()"></div>
  <aside class="drawer ${state.open?"on":""}" role="dialog" aria-modal="true" aria-label="项目详情">
    <button class="close" type="button" onclick="closeCard()">关闭</button>
    <p class="meta">${esc(kindLine)}</p>
    <h2>#${esc(card.rank)} ${esc(card.full_name)}</h2>
    ${card.observation_zh ? `<section class="obs-panel">
      <h3>${esc(card.observation_zh)}</h3>
      <p class="meta">${esc(card.observation_hint || (card.observation_kind==="yours" ? "这是你标记关注的仓库。" : "伏笔正在连续看这个仓库近几日的变化。"))}</p>
    </section>` : ""}
    ${state.actionError ? `<p class="warn" role="alert">${esc(state.actionError)}</p>` : ""}
    <section>
      <h3>项目简介</h3>
      <p class="intro">${esc(intro || "信息不足，无法写简介。")}</p>
      <a class="gh-mini" href="${esc(card.html_url)}" target="_blank" rel="noopener noreferrer">打开 GitHub ↗</a>
    </section>
    <section class="score-block">
      <h3>评分</h3>
      ${chipsView(card)}
      ${eevLine(card)}
      ${card.decision ? `<p>判断：${esc(card.decision)}</p>` : ""}
      ${conf ? `<p class="meta">置信度：${esc(conf)}</p>` : `<p class="meta">置信度：<span class="na">N/A</span></p>`}
      <p class="meta">样本：${sample == null ? `<span class="na">N/A</span>` : esc(sample)} 个外部 PR</p>
    </section>
    <section>
      <h3>为什么现在：</h3>
      <p class="now">${esc(drawerWhyNow(card))}</p>
    </section>
    <div class="layers">
      ${factCells(card)}
      <p><strong>事实：</strong>${esc(factLine(card) || "—")}${spark}</p>
      <p><strong>解读：</strong>${esc(card.interpretation || "—")}</p>
      <p><strong>判断：</strong>${esc(card.decision || "—")} · ${esc(card.recommended_action || "")}</p>
    </div>
    ${momentumView(card)}
    ${creatorView(card)}
    ${communityView(card)}
    ${thesisView(card)}
    ${timelineView(card.timeline)}
    <section>
      <h3>推荐入口</h3>
      <p><strong>${esc(card.strategy_summary_zh || "先阅读再决定")}</strong>
        （${esc(card.strategy_path || "")}） · 预计 ${esc(card.strategy_effort || "—")} · 难度 ${esc(card.strategy_difficulty || "—")}</p>
      <ol class="plan">${(card.strategy_steps_zh||[]).map((x,i) => `<li>${labeledStep(x,i)}</li>`).join("")}</ol>
    </section>
    ${entryView(card)}
    ${contributionView(card)}
    <p>
      ${enterOrMissionBtn(card)}
      <a class="gh" href="${esc(card.html_url)}" target="_blank" rel="noopener noreferrer">查看项目 ↗</a>
    </p>
    <p class="meta">「开始进入」只在本机准备项目，不会向 GitHub 发内容。「记入观察清单」不会创建任务，只记个人立场。</p>
    <h3>我的决定</h3>
    <p class="meta">下面只记个人立场。「记入观察清单」不会创建任务。要进入请点「开始进入」。</p>
    <div class="decide">${actions}</div>
    <details class="audit">
      <summary>评分依据</summary>
      <p><strong>最终综合评分：</strong>${n(card.final_score)}
        <span class="pill ${preview?"":"ok"}">${esc(card.rank_kind_zh || kindLine)}</span></p>
      <p class="meta">数据完整度：${esc(card.data_completeness_zh || "低")} · 置信度：${esc(card.confidence_zh || "低")}（完整度低不是低分）</p>
      <p class="meta">阶段：${esc(card.s1_stage_zh || card.s1_stage || "—")} · ${esc(card.s1_pool_zh || "")}</p>
      <p class="meta">早期程度：${n(card.s1_earlyness)} · 证据强度：${n(card.s1_evidence)} · 机会窗口：${n(card.s1_window)}</p>
      <p class="meta">早期加分：${esc((card.s1_earlyness_plus || []).join("；") || "—")}</p>
      <p class="meta">早期扣分：${esc((card.s1_earlyness_minus || []).join("；") || "—")}</p>
      <p class="meta">证据加分：${esc((card.s1_evidence_plus || []).join("；") || "—")}</p>
      <p class="meta">证据不足：${esc((card.s1_evidence_minus || []).join("；") || "—")}</p>
      <p class="meta">Star 只是规模观察，不是区间门槛，也不是否决。</p>
      <p class="meta">进入通道：${esc(accessLine(card))}（不是贡献者缺口）</p>
      <p class="meta">外部 PR 接受率：${n(card.access_merge_rate)} · 外部 PR 评审率：${n(card.access_review_rate)}</p>
      <p class="meta">
        Stars ${n(card.stars)} · Forks ${n(card.forks)} · 贡献者 ${n(card.contributors)}
        · Open Issues ${n(card.open_issues)}<br/>
        最近活动 ${n(card.last_pushed_at)} · 最近 Release ${n(card.last_release)}
        · 首次发现 ${n(card.first_seen_at)}
      </p>
      <p class="meta">长期参与潜力：${card.strategy_long_term && card.strategy_long_term.score != null ? n(card.strategy_long_term.score) + " / 100" : "N/A"}（不是承诺）</p>
      <h3>五维评分</h3>
      ${(d.dimensions || []).map(dimBlock).join("")}
      <h3>三个独立评审视角</h3>
      ${revs}
      <h3>评审分歧：${esc(dg.level_zh || "—")}</h3>
      <p>趋势 ${n(dg.trend)} · 社区 ${n(dg.community)} · 贡献 ${n(dg.contributor)}</p>
      <p>${esc(dg.explain || "")}</p>
      <h3>最终综合评分：${n(card.final_score)}</h3>
      <p>趋势评审 ${n(card.trend)} · 社区评审 ${n(card.community)} · 贡献评审 ${n(card.contributor)} · 主审 ${n(card.chair)}</p>
      <p class="meta">${esc(ch.weight_note || "")}</p>
      <p><strong>综合判断：</strong>${esc(ch.judgment || "")}</p>
      <h3>${esc(whyTitle)}</h3>
      <ul>${why}</ul>
      <p><strong>风险：</strong>${esc(ch.main_risk || "")}</p>
    </details>
  </aside>`;
}

function boardView() {
  const b = state.board;
  return `
  ${header(b)}
  <div class="toolbar">
    <label>排序
      <select onchange="state.sort=this.value;render()">
        ${sortOptions()}
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
    <span class="date">当前按${sortLabel(state.sort)}排序</span>
    <button type="button" disabled title="扫描由每日 foreshadow run 或调度执行，本页不在后台扫 GitHub">暂停扫描</button>
    <button type="button" onclick="loadMissions()">查看任务</button>
  </div>
  ${state.showMissions ? missionListView() : ""}
  ${contributionJobsView()}
  ${intelBanner(b)}
  <h2 id="board-list">今日候选榜</h2>
  <div class="list">${listView(b)}</div>
  ${drawerView((b.candidates||[]).find(c => c.full_name === state.open))}
  ${jobOnlyDrawer()}
  ${missionView(state.mission)}
  `;
}

function contributionJobsView() {
  const rows = state.contributionJobs || [];
  if (!state.user || !rows.length) return "";
  return `<section class="contrib-pack">
    <h3>贡献准备任务</h3>
    ${rows.map(j => `
      <div class="row">
        <div>
          <div class="nm">${esc(j.full_name)}</div>
          <div class="sub">${esc(j.status_zh || j.status || "")} · ${esc(j.backend || "")}</div>
        </div>
        <div>
          <button type="button" class="primary" onclick="openContributionJob(${Number(j.id)||0})">查看结果</button>
        </div>
      </div>`).join("")}
  </section>`;
}
function jobOnlyDrawer() {
  if (!state.openJob) return "";
  const job = state.openJob;
  const card = { full_name: job.full_name, contribution: job.payload || { job }, contribution_job: job };
  return `<div class="drawer-bg on" onclick="state.openJob=null;render()"></div>
  <aside class="drawer on" role="dialog" aria-modal="true" aria-label="贡献结果">
    <button class="close" type="button" onclick="state.openJob=null;render()">关闭</button>
    <h2>${esc(job.full_name || "")}</h2>
    ${contributionView(card)}
  </aside>`;
}
async function openContributionJob(id) {
  try {
    const data = await api("/api/contribution?id=" + id);
    state.openJob = Object.assign({}, data.job || {}, { payload: data });
    applyContribution(data);
    render();
  } catch (e) { state.actionError = e.message || String(e); render(); }
}
function applyContribution(data) {
  if (!data || !data.job) return;
  const jobs = state.contributionJobs || [];
  const idx = jobs.findIndex(j => Number(j.id) === Number(data.job.id));
  if (idx >= 0) jobs[idx] = data.job; else jobs.unshift(data.job);
  state.contributionJobs = jobs;
  const name = data.job.full_name;
  const card = (state.board && state.board.candidates || []).find(c => c.full_name === name);
  if (card) {
    card.contribution = data;
    card.contribution_job = data.job;
  }
  if (state.openJob && Number(state.openJob.id) === Number(data.job.id)) {
    state.openJob = Object.assign({}, data.job, { payload: data });
  }
}
let contribPoll = null;
function stopContribPoll() {
  if (contribPoll) { clearInterval(contribPoll); contribPoll = null; }
}
function startContribPoll(id) {
  stopContribPoll();
  contribPoll = setInterval(async () => {
    try {
      const data = await api("/api/contribution?id=" + id);
      applyContribution(data);
      const st = data.job && data.job.status;
      if (st === "ready" || st === "failed" || st === "refused_remote") stopContribPoll();
      render();
    } catch {}
  }, 1500);
}
function missionListView() {
  const rows = state.missions || [];
  if (!rows.length) return `<p class="empty">还没有进入任务。在榜上点「开始进入」。</p>`;
  return `<div class="mission-list">${rows.map(m => `
    <div class="row">
      <div>
        <div class="nm">${esc(m.full_name)}</div>
        <div class="sub">状态 ${esc(m.status_zh || m.status || "—")} · ${esc((m.steps_zh && m.steps_zh[0]) || m.next_step_zh || "")}</div>
      </div>
      <div>
        <button type="button" class="primary" onclick="openMission(${Number(m.id)||0})">打开</button>
      </div>
    </div>`).join("")}</div>`;
}

function stripStepPrefix(s) {
  return String(s || "").replace(/^第[^步]{1,4}步[：:]\s*/, "").trim();
}

function labeledStep(x, i) {
  const s = String(x || "");
  if (/^第.+步/.test(s)) return esc(s);
  const zh = ["第一步","第二步","第三步","第四步","第五步","第六步","第七步","第八步","第九步","第十步"];
  return `<strong>${zh[i] || ("第"+(i+1)+"步")}</strong> ${esc(s)}`;
}

function missionPaused(m) {
  if (!m || m.status === "ABANDONED") return false;
  if (m.paused || m.status === "PAUSED") return true;
  const id = Number(m.id);
  return !!(state.pausedIds && (state.pausedIds[m.id] || (Number.isFinite(id) && state.pausedIds[id])));
}

const PIPELINE_LABELS_ZH = {
  clone: "克隆仓库",
  branch: "创建本地分支",
  inspect: "检查仓库",
  issue: "读取 Issue",
  tests: "收集测试",
  drafts: "生成草稿",
  waiting_approval: "等待确认"
};
const PIPELINE_ORDER = ["clone","branch","inspect","issue","tests","drafts","waiting_approval"];
const PIPELINE_ID_RE = /^(clone|branch|inspect|issue|tests|drafts|waiting_approval)$/i;
const PIPELINE_GLYPH = {done:"✓", pending:"○", running:"◐", failed:"✕", skipped:"○", dependency_required:"○"};
const PIPELINE_DETAIL = {done:"完成", pending:"未完成", running:"进行中", failed:"失败", skipped:"跳过", dependency_required:"需要用户授权安装依赖"};

function currentNeed(m) {
  if (state.busy) return "无需操作";
  if (m && m.clone && m.clone.ok === false && m.clone.status && m.clone.status !== "skipped") {
    const err = m.clone.error || ({failed:"克隆失败，任务仍保留", timeout:"克隆超时", no_git:"本机没有 git", incomplete:"本地目录不完整，未覆盖", invalid:"仓库名无效"}[m.clone.status] || m.clone.status);
    return "本地 clone 未完成：" + String(err);
  }
  if (m && m.status === "LOCAL_SETUP") return "本地环境还没准备好";
  if (m && m.tests && (m.tests.status === "DEPENDENCY_REQUIRED" || m.tests.gate === "DEPENDENCY_REQUIRED"))
    return "需要用户授权安装依赖";
  if (m && m.status === "WAITING_USER_APPROVAL") return "本地已准备，远程写入需你确认";
  if (m && m.status === "MISSION_READY") return "点击开始进入才会 clone";
  return (m && (m.next_step_zh || m.status_zh)) || "—";
}

function pipelineStepId(step) {
  return String((step && (step.id || step.key || step.name)) || "");
}

function pipelineStepLabel(step) {
  const id = pipelineStepId(step);
  if (PIPELINE_LABELS_ZH[id]) return PIPELINE_LABELS_ZH[id];
  const zh = String((step && (step.label_zh || step.labelZh)) || "");
  if (zh && !PIPELINE_ID_RE.test(zh)) return zh;
  const raw = String((step && (step.label || step.name || step.id)) || "");
  const mapped = PIPELINE_LABELS_ZH[raw] || PIPELINE_LABELS_ZH[raw.toLowerCase()];
  if (mapped) return mapped;
  if (PIPELINE_ID_RE.test(raw)) return PIPELINE_LABELS_ZH[raw.toLowerCase()] || "步骤";
  return zh || "步骤";
}

function pipelineStepStatus(step, isCurrent) {
  const st = String((step && step.status) || "").toLowerCase();
  if (st === "done" || st === "ok" || st === "cloned" || st === "complete") return "done";
  if (st === "failed" || st === "fail" || st === "error") return "failed";
  if (st === "dependency_required") return "dependency_required";
  if (st === "skipped" || st === "skip") return "skipped";
  if (st === "running") return "running";
  if (isCurrent) return "running";
  return "pending";
}

function pipelineLive(m) {
  return !!(state.busy || (m && m.status === "LOCAL_SETUP"));
}

function normalizePipeline(m) {
  if (Array.isArray(m && m.pipeline) && m.pipeline.length) return m.pipeline;
  if (m && m.pipeline && typeof m.pipeline === "object") {
    const items = Object.entries(m.pipeline).map(([key, step]) => {
      const s = (step && typeof step === "object") ? Object.assign({id: key}, step) : {id: key, evidence: step};
      return s;
    });
    if (items.length) return items;
  }
  return PIPELINE_ORDER.map(id => ({id, status: "pending", label_zh: PIPELINE_LABELS_ZH[id]}));
}

function currentPipelineIndex(steps) {
  return steps.findIndex(s => {
    const st = String((s && s.status) || "").toLowerCase();
    return st !== "done" && st !== "ok" && st !== "cloned" && st !== "complete"
      && st !== "failed" && st !== "fail" && st !== "error"
      && st !== "skipped" && st !== "skip" && st !== "running"
      && st !== "dependency_required";
  });
}

const EVIDENCE_ZH = {cloned:"已克隆到本机", exists:"本地已有仓库", failed:"克隆失败，任务仍保留", no_git:"本机没有 git", skipped:"已跳过克隆", timeout:"克隆超时", incomplete:"本地目录不完整，未覆盖", invalid:"仓库名无效", inspected:"已检查仓库", none:"无 Issue 引用", missing:"草稿缺失"};

function stripMd(s) {
  return String(s || "").replace(/[*`#]+/g, "").trim();
}

function renderPipelineStep(step, isCurrent) {
  const status = pipelineStepStatus(step, isCurrent);
  const label = pipelineStepLabel(step);
  const glyph = PIPELINE_GLYPH[status] || "○";
  let detail = PIPELINE_DETAIL[status] || "未完成";
  if (status === "dependency_required") {
    detail = "需要用户授权安装依赖";
  } else if (status !== "skipped") {
    const evidence = step && (step.evidence || step.detail || step.text);
    const ev = evidence == null ? "" : stripMd(String(evidence));
    if (ev && EVIDENCE_ZH[ev]) detail = EVIDENCE_ZH[ev];
    else if (ev && !PIPELINE_ID_RE.test(ev) && ev !== step.status) detail = ev;
  }
  return `<li>${glyph} ${esc(label)}：${esc(detail)}</li>`;
}

function progressChecklist(m) {
  const steps = normalizePipeline(m);
  const live = pipelineLive(m);
  const currentIdx = live ? currentPipelineIndex(steps) : -1;
  return `<ul class="checklist">${steps.map((step, i) => renderPipelineStep(step, live && i === currentIdx)).join("")}</ul>`;
}

function missionView(m) {
  if (!m) return "";
  const cloneOk = m.clone && m.clone.ok;
  const stepsSrc = (m.steps_zh||[]).filter(s => !cloneOk || !(String(s).includes("克隆") || String(s).includes("下到本机")));
  const steps = stepsSrc.map((x,i) => `<li>${labeledStep(x,i)}</li>`).join("");
  const git = (m.git_ops_zh||[]).map(x => `<li>${esc(x)}</li>`).join("");
  const clone = m.clone && m.clone.status ? m.clone.status : "尚未 clone";
  const cloneErr = m.clone && m.clone.error ? m.clone.error : "";
  const cloneZh = ({cloned:"已克隆到本机", exists:"本地已有仓库", failed:"克隆失败，任务仍保留", no_git:"本机没有 git", skipped:"已跳过克隆", timeout:"克隆超时", incomplete:"本地目录不完整，未覆盖", invalid:"仓库名无效"}[clone] || clone);
  const firstRaw = (m.steps_zh && m.steps_zh[0]) || "未知";
  const first = stripStepPrefix(firstRaw) || firstRaw;
  const root = m.local_path || "";
  const id = m.id;
  const paused = missionPaused(m);
  const abandoned = m.status === "ABANDONED";
  const strat = m.strategy || {};
  const why = (m.why_now && m.why_now.length)
    ? m.why_now.join("；")
    : ((strat.why && strat.why.length) ? strat.why.join("；") : "未知");
  const entryBits = [strat.summary_zh, strat.path].filter(Boolean);
  const entry = entryBits.length ? entryBits.join(" / ") : "未知";
  const diff = m.difficulty || strat.difficulty || "未知";
  const effort = m.effort || strat.effort || "未知";
  const statusLine = (m.status_zh || m.status || "未知") + (paused ? " · 已暂停" : "");
  return `
  <div class="drawer-bg on" onclick="state.mission=null;render()"></div>
  <aside class="drawer on" role="dialog" aria-modal="true" aria-label="进入任务">
    <button class="close" type="button" onclick="state.mission=null;render()">关闭</button>
    <p class="brand">今日进入计划</p>
    <h2>${esc(m.full_name)}</h2>
    <section class="enter-brief">
      ${state.actionError ? `<p class="warn" role="alert">${esc(state.actionError)}</p>` : ""}
      <p class="now"><strong>当前需要你做什么：</strong>${esc(currentNeed(m))}</p>
      <p><strong>为什么进入：</strong>${esc(why)}</p>
      <p><strong>推荐入口：</strong>${esc(entry)}</p>
      <p><strong>难度</strong> ${esc(diff)} · <strong>预计</strong> ${esc(effort)}</p>
      <p><strong>第一步：</strong>${esc(first)}</p>
      <p><strong>当前状态：</strong>${esc(statusLine)}</p>
    </section>
    <p class="warn">${esc(m.remote_blocked || "等待你的确认才能执行任何远程 GitHub 操作。")}</p>
    <h3>本地进度</h3>
    ${progressChecklist(m)}
    <p class="meta">暂停只停本地工作，不会向 GitHub 发请求。</p>
    <p>
      ${cloneOk || paused || abandoned ? "" : `<button type="button" class="primary" ${state.busy?"disabled":""} onclick="setupLocal(${id})">把项目下载到本机</button>`}
      ${abandoned ? "" : (paused
        ? `<button type="button" class="primary" onclick="resumeMission(${id})">继续任务</button>`
        : `<button type="button" onclick="pauseMission(${id})">暂停任务</button>`)}
      <button type="button" class="ghost" onclick="markEvent(${id}, 'abandoned')">停止任务</button>
    </p>
    <h3>行动计划</h3>
    <ol class="plan">${steps}</ol>
    <p class="meta">按本地 FORESHADOW.md 和 ISSUE_DRAFT.md 执行。${root ? "打开 " + esc(root) + "/FORESHADOW.md 和 " + esc(root) + "/ISSUE_DRAFT.md。代码在 " + esc(root) + "/repo ，分支 foreshadow/entry。不要 push。" : "把项目下载到本机后会生成这两份文件。"}</p>
    ${m.cited_issue && m.cited_issue.number ? `<p><strong>建议先看 Issue #${esc(m.cited_issue.number)}</strong> ${esc(m.cited_issue.title||"")}</p>` : ""}
    ${m.cited_issue && m.cited_issue.body ? `<pre class="meta">${esc(String(m.cited_issue.body).slice(0,400))}</pre>` : ""}
    ${m.draft_excerpt ? `<h3>本地草稿（未发送）</h3><pre class="meta">${esc(m.draft_excerpt)}</pre>` : ""}
    <p>
      <p class="meta">要改草稿：编辑本地 ISSUE_DRAFT.md。点「草稿可以」只记账，仍不会发送。</p>
      <button type="button" onclick="markEvent(${id}, 'draft_approved')">草稿可以，仍不要发送</button>
      <button type="button" onclick="markEvent(${id}, 'maintainer_replied')">维护者已回复</button>
      <button type="button" onclick="markEvent(${id}, 'pr_merged')">我看到已被合并</button>
      <button type="button" onclick="markEvent(${id}, 'user_submitted')">我已自行提交</button>
    </p>
    <details class="git-ops">
      <summary>展开底层 Git 操作</summary>
      <p>阶段 ${esc(m.stage||"—")} · 机会 ${n(m.opportunity_window)} · 进入通道 ${m.access == null ? "未知" : (n(m.access) + (Number(m.access)===0 ? "（已知为 0，不是未知）" : ""))}</p>
      <p>为什么现在进入：${esc((m.why_now||[]).join("；") || "—")}</p>
      <p>推荐入口：${esc(m.strategy && m.strategy.summary_zh || m.strategy && m.strategy.path || "—")}</p>
      <p>难度 ${esc(m.difficulty||"—")} · 预计 ${esc(m.effort||"—")} · 状态 ${esc(m.status_zh || m.status || "—")}</p>
      <p>下一步：${esc(m.next_step_zh || "先阅读推荐入口")}</p>
      <p>本地目录：${esc(root || "尚未准备")} · clone：${esc(cloneZh)}</p>
      ${cloneErr ? `<p class="warn">clone：${esc(cloneErr)}</p>` : ""}
      ${m.inspect && m.inspect.has_readme ? `<p>README：有${(m.inspect.readme_headings||[]).length ? " · " + esc((m.inspect.readme_headings||[]).slice(0,6).join("；")) : ""}</p>` : ""}
      ${m.tests && (m.tests.status==="DEPENDENCY_REQUIRED" || m.tests.gate==="DEPENDENCY_REQUIRED") ? `<p>需要用户授权安装依赖。Foreshadow 不会执行 npm install / cargo build。</p>` : (m.tests && (m.tests.kind==="node" || m.tests.kind==="cargo") ? `<p>仓库测试是 ${esc(m.tests.kind)}。Foreshadow 不执行 npm/cargo。</p>` : "")}
      <p>本地分支：${esc((m.branch && m.branch.name) || (m.clone && m.clone.ok ? "foreshadow/entry" : "—"))} · 草稿：${esc(m.draft_path || "ISSUE_DRAFT.md")}${m.pr_draft_path ? " · 补丁草案：" + esc(m.pr_draft_path) + "（未发送）" : ""}</p>
      <ul>${git || "<li>仅本地 clone / 分支 / commit</li>"}</ul>
    </details>
    <button type="button" onclick="refuseRemote()">尝试创建 PR（应被拒绝）</button>
  </aside>`;
}

let lastModal = null;
function render() {
  const root = document.getElementById("app");
  if (!state.user && !state.board && !state.public) root.innerHTML = authView();
  else if (!state.board && state.error) root.innerHTML = `<p class="empty">今日机会榜打不开。<br/>${esc(state.error)}<br/><button type="button" class="primary" onclick="retryBoard()">重试</button> ${state.user ? `<button type="button" onclick="logout()">退出</button>` : `<button type="button" onclick="state.showAuth=true;render()">登录</button>`}</p>`;
  else if (!state.board) root.innerHTML = `<p class="empty">正在打开今日机会榜…</p>`;
  else if (!state.user && state.showAuth) root.innerHTML = authView() + `<p class="empty"><button type="button" onclick="state.showAuth=false;render()">返回榜单</button></p>`;
  else root.innerHTML = boardView();
  const modal = document.querySelector("aside.drawer.on");
  const key = modal ? ((state.mission && state.mission.id) || state.open || "drawer") : null;
  if (modal && key !== lastModal) {
    const close = modal.querySelector("button.close");
    if (close) close.focus();
  }
  lastModal = key;
}

function clearWorkState() {
  state.mission = null;
  state.missions = [];
  state.showMissions = false;
  state.actionError = "";
  state.portfolio = null;
  state.pausedIds = {};
  state.open = null;
  state.busy = false;
}

async function boot() {
  try {
    const me = await api("/api/me");
    state.user = me.user;
    state.public = !!me.public;
    state.allowRegister = me.allow_register !== false;
    state.githubOAuth = !!me.github_oauth;
    const authErr = new URLSearchParams(location.search).get("auth_error");
    if (authErr === "not_operator") state.error = "这个 GitHub 账号不是授权操作者。";
    else if (authErr === "state") state.error = "登录已过期，请再点一次 GitHub 登录。";
    else if (authErr === "github") state.error = "GitHub 登录失败。";
    if (authErr) history.replaceState({}, "", location.pathname);
    if (state.user) state.showAuth = false;
  } catch (e) {
    state.user = null;
    state.error = e.message || String(e);
    render();
    return;
  }
  try { await loadBoard(); }
  catch (e) {
    state.error = e.message || String(e);
    if (!state.user && !state.public) state.board = null;
  }
  render();
}

async function loadBoard() {
  try {
    state.board = await api("/api/board");
    if (!state._sortInited) {
      state.sort = (state.board && state.board.sort_default) || "eev";
      state._sortInited = true;
    }
    if (state.board && state.board.public != null) state.public = !!state.board.public;
    if (state.board && state.board.allow_register != null) state.allowRegister = !!state.board.allow_register;
    if (state.user) {
      try { state.portfolio = await api("/api/portfolio"); } catch { state.portfolio = null; }
      try {
        const jobs = await api("/api/contribution");
        state.contributionJobs = jobs.jobs || [];
        const latest = {};
        for (const j of state.contributionJobs) latest[j.full_name] = j;
        for (const c of (state.board.candidates || [])) {
          if (latest[c.full_name]) c.contribution_job = latest[c.full_name];
        }
      } catch { state.contributionJobs = state.contributionJobs || []; }
    } else {
      state.portfolio = null;
    }
    stampMissionOnCards(state.mission);
    for (const m of (state.missions || [])) stampMissionOnCards(m);
  } catch (e) {
    state.error = e.message || String(e);
    throw e;
  }
}

async function submitAuth(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const body = Object.fromEntries(fd.entries());
  state.error = "";
  try {
    const path = state.auth === "register" ? "/api/register" : "/api/login";
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    clearWorkState();
    state.user = data.user;
    await loadBoard();
  } catch (e) {
    state.error = e.message;
  }
  render();
  return false;
}

async function logout() {
  try { await api("/api/logout", { method: "POST", body: "{}" }); } catch {}
  state.user = null;
  state.board = null;
  clearWorkState();
  render();
}

function openCard(name) { state.open = name; render(); }
function closeCard() { state.open = null; render(); }

function cloneOkFor(c) {
  if (!c) return false;
  if (c.clone && c.clone.ok) return true;
  if (state.mission && (state.mission.full_name === c.full_name || Number(state.mission.id) === Number(c.mission_id))
      && state.mission.clone && state.mission.clone.ok) return true;
  const found = (state.missions || []).find(x => Number(x.id) === Number(c.mission_id) || x.full_name === c.full_name);
  return !!(found && found.clone && found.clone.ok);
}

function stampMissionOnCards(m) {
  if (!m || !state.board) return;
  const card = (state.board.candidates || []).find(c => c.full_name === m.full_name);
  if (!card) return;
  if (m.id) card.mission_id = m.id;
  if (m.status) card.mission_status = m.status;
  if (m.clone) card.clone = m.clone;
  if (m.pipeline) card.pipeline = m.pipeline;
  if (m.tests) card.tests = m.tests;
}

function alreadyLocal(m) {
  return !!(m && m.clone && m.clone.ok);
}

async function analyzeEntry(name) {
  state.busy = true; state.actionError = ""; render();
  try {
    const data = await api("/api/entry", { method: "POST", body: JSON.stringify({ full_name: name }) });
    const card = (state.board && state.board.candidates || []).find(c => c.full_name === name);
    if (card) card.entry = data.entry;
  } catch (e) { state.actionError = e.message || String(e); }
  state.busy = false; render();
}
async function startContribution(name) {
  state.busy = true; state.actionError = ""; render();
  try {
    const card0 = (state.board && state.board.candidates || []).find(c => c.full_name === name);
    const entry = card0 && card0.entry;
    const rec = entry && entry.recommended;
    const evidence = (rec && rec.evidence || []).map(e => (e && (e.url || e.id)) || e).filter(Boolean);
    const task = rec ? {
      structured: {
        repository: name,
        task: rec.title || rec.summary_zh || "",
        issue_number: rec.issue_number,
        why: Array.isArray(rec.why) ? rec.why.join("; ") : (rec.why || ""),
        evidence,
        relevant_files: rec.files || [],
        forbidden_actions: ["git push", "gh pr create"],
      },
      why: rec.summary_zh || rec.title || "",
    } : { fixture: "demo_add", why: "no entry analysis; native demo only" };
    const data = await api("/api/contribution", { method: "POST", body: JSON.stringify({
      full_name: name,
      backend: rec ? "mini_swe_agent" : "native",
      task,
    }) });
    applyContribution(data);
    if (data.job && data.job.id) startContribPoll(data.job.id);
  } catch (e) { state.actionError = e.message || String(e); }
  state.busy = false; render();
}
async function startEnter(name) {
  if (state.busy) return;
  state.busy = true;
  state.actionError = "";
  render();
  try {
    const data = await api("/api/mission", { method: "POST", body: JSON.stringify({ full_name: name }) });
    state.mission = data.mission;
    stampMissionOnCards(data.mission);
    render();
    state.open = null;
    const card = (state.board && state.board.candidates || []).find(c => c.full_name === name);
    if (card && data.mission && data.mission.id) card.mission_id = data.mission.id;
    if (data.mission && data.mission.id && !missionPaused(data.mission) && !alreadyLocal(data.mission)) await setupLocal(data.mission.id);
    try { await loadBoard(); } catch {}
  } catch (e) { state.actionError = e.message || String(e); }
  finally { state.busy = false; render(); }
}

async function setupLocal(id) {
  const pausedHere = !!(state.pausedIds[id] || state.pausedIds[Number(id)]
    || (missionPaused(state.mission) && Number(state.mission && state.mission.id) === Number(id)));
  if (pausedHere) return;
  const holdBusy = !state.busy;
  if (holdBusy) { state.busy = true; render(); }
  try {
    const data = await api("/api/mission/setup", { method: "POST", body: JSON.stringify({ id }) });
    state.mission = data.mission;
    stampMissionOnCards(data.mission);
    if (state.mission && (state.pausedIds[id] || state.pausedIds[Number(id)])) state.mission.paused = true;
    if (state.portfolio) try { state.portfolio = await api("/api/portfolio"); } catch {}
    try { await loadBoard(); } catch {}
    render();
  } catch (e) { state.actionError = e.message || String(e); }
  finally { if (holdBusy) { state.busy = false; render(); } }
}

async function loadMissions() {
  state.actionError = "";
  try {
    const data = await api("/api/missions");
    state.missions = data.missions || [];
    for (const m of state.missions) stampMissionOnCards(m);
    state.showMissions = true;
  } catch (e) { state.actionError = e.message || String(e); }
  render();
}

function openMission(id) {
  const nid = Number(id);
  const found = (state.missions || []).find(x => Number(x.id) === nid);
  if (found) {
    state.open = null;
    state.mission = found;
    if (missionPaused(found)) state.mission.paused = true;
    render();
  }
}

async function retryBoard() {
  state.error = "";
  try { await loadBoard(); } catch (e) { state.error = e.message; }
  render();
}

async function openExisting(id) {
  state.actionError = "";
  try {
    const data = await api("/api/missions");
    state.missions = data.missions || [];
    for (const m of state.missions) stampMissionOnCards(m);
    state.showMissions = true;
    openMission(id);
  } catch (e) { state.actionError = e.message || String(e); render(); }
}

async function markEvent(id, event) {
  state.actionError = "";
  try {
    const data = await api("/api/mission/event", { method: "POST", body: JSON.stringify({ id, event }) });
    state.mission = data.mission;
    if (event === "abandoned") {
      delete state.pausedIds[id];
      delete state.pausedIds[Number(id)];
    }
    if (event === "paused" && state.mission) {
      state.pausedIds[id] = true;
      state.mission.paused = true;
    }
    if (event === "resumed" && state.mission) {
      delete state.pausedIds[id];
      delete state.pausedIds[Number(id)];
      state.mission.paused = false;
    }
    try { state.portfolio = await api("/api/portfolio"); } catch {}
    render();
  } catch (e) { state.actionError = e.message || String(e); render(); }
}

async function pauseMission(id) {
  state.pausedIds[id] = true;
  state.pausedIds[Number(id)] = true;
  if (state.mission && Number(state.mission.id) === Number(id)) state.mission.paused = true;
  state.actionError = "";
  render();
  try {
    const data = await api("/api/mission/event", { method: "POST", body: JSON.stringify({ id, event: "paused" }) });
    if (data.mission) {
      state.mission = data.mission;
      state.mission.paused = true;
    }
    try { state.portfolio = await api("/api/portfolio"); } catch {}
  } catch (e) { state.actionError = e.message || String(e); }
  render();
}

async function resumeMission(id) {
  delete state.pausedIds[id];
  delete state.pausedIds[Number(id)];
  if (state.mission && Number(state.mission.id) === Number(id)) state.mission.paused = false;
  state.actionError = "";
  try {
    const data = await api("/api/mission/event", { method: "POST", body: JSON.stringify({ id, event: "resumed" }) });
    if (data.mission) {
      state.mission = data.mission;
      state.mission.paused = false;
    }
    try { state.portfolio = await api("/api/portfolio"); } catch {}
    render();
  } catch (e) {
    state.actionError = e.message || String(e);
    openMission(id);
    render();
  }
}

async function refuseRemote() {
  const body = { action: "create_pr" };
  if (state.mission && state.mission.id) body.id = state.mission.id;
  try {
    const data = await api("/api/mission/remote", { method: "POST", body: JSON.stringify(body) });
    state.actionError = data.error || data.remote_blocked || "已阻止远程操作";
  } catch (e) { state.actionError = e.message || String(e); }
  render();
}

async function saveReview(repo, action) {
  state.actionError = "";
  try {
    await api("/api/review", { method: "POST", body: JSON.stringify({ repo, action }) });
    const card = (state.board.candidates||[]).find(c => c.full_name === repo);
    if (card) { card.my_action = action; }
    render();
  } catch (e) {
    state.actionError = e.message || String(e);
    render();
  }
}

document.addEventListener("keydown", (e) => {
  const modal = document.querySelector("aside.drawer.on");
  if (e.key === "Tab" && modal) {
    const nodes = [...modal.querySelectorAll("button, a, input")].filter(n => !n.disabled);
    if (!nodes.length) return;
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    return;
  }
  if (e.key !== "Escape") return;
  if (state.mission) { state.mission = null; render(); return; }
  closeCard();
});
boot();
</script>
</body>
</html>
"""


def render_app_html() -> str:
    return APP_HTML
