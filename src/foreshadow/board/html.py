from __future__ import annotations

import html
from datetime import UTC, datetime

from foreshadow.board.schema import BoardCard, BoardDocument


def _e(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _dim_cell(value: int | None, insufficient: bool = False) -> str:
    if value is None or insufficient:
        return '<td class="na">N/A</td>'
    return f"<td>{value}/20</td>"


def _score(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.1f}"


def _reviewer_block(title: str, card: BoardCard, which: str) -> str:
    r = getattr(card, which)
    ev = "".join(
        f"<li>{_e(item.polarity)} {_e(item.metric)}: {_e(item.detail)}"
        f"{' <span class="muted">[' + _e(item.window) + ']</span>' if item.window else ''}"
        f"</li>"
        for item in r.evidence[:8]
    )
    st = "".join(f"<li>{_e(x)}</li>" for x in r.strengths)
    wk = "".join(f"<li>{_e(x)}</li>" for x in r.weaknesses)
    rk = "".join(f"<li>{_e(x)}</li>" for x in r.risks)
    dims = "".join(
        f"<tr><th>{_e(k)}</th>{_dim_cell(v, k == 'momentum' and card.momentum_na)}</tr>"
        for k, v in r.dimensions.items()
    )
    return f"""
<section class="reviewer">
  <h4>{_e(title)} · {_score(r.score)} · {_e(r.confidence)} · {_e(r.recommendation)}</h4>
  <table class="dims">{dims}</table>
  <p class="muted">Weights: {_e(r.weights)}</p>
  <div class="cols">
    <div><h5>Strengths</h5><ul>{st}</ul></div>
    <div><h5>Weaknesses</h5><ul>{wk}</ul></div>
    <div><h5>Risks</h5><ul>{rk}</ul></div>
  </div>
  <h5>Evidence</h5>
  <ul class="ev">{ev}</ul>
</section>
"""


def _actions(card: BoardCard) -> str:
    bits = []
    for action, cmd in card.review_commands.items():
        bits.append(f"<code title='{_e(cmd)}'>{_e(action)}</code>")
    return " ".join(bits)


def _card_html(card: BoardCard, *, dense: bool) -> str:
    stamp = ""
    if card.momentum_na:
        stamp = '<span class="stamp">PROVISIONAL</span>'
    if card.vetoed:
        stamp += ' <span class="stamp stamp-bad">VETO</span>'
    why_not = ""
    if card.chair.exclusion_reason:
        why_not = f"<p class='exclude'><strong>Why not Top 5?</strong> {_e(card.chair.exclusion_reason)}</p>"
    why_yes = ""
    if card.chair.why_selected:
        why_yes = f"<p><strong>Why selected:</strong> {_e(card.chair.why_selected)}</p>"
    dims = "".join(
        f"<tr><th>{_e(k)}</th>{_dim_cell(v, k == 'momentum' and card.momentum_na)}</tr>"
        for k, v in card.dimensions.items()
    )
    body = f"""
<p class="lede">
  Final {_score(card.final_score)}
  · Chair {_score(card.chair.score)}
  · Trend {_score(card.trend.score)}
  · Community {_score(card.community.score)}
  · Contributor {_score(card.contributor.score)}
  · {_e(card.chair.consensus)} ({_e(card.chair.disagreement)} disagreement, spread {card.chair.spread:.1f})
</p>
<p class="muted">{_e(card.chair.justification)}</p>
{why_yes}{why_not}
<table class="dims">{dims}</table>
<p><strong>Main risk:</strong> {_e(card.chair.main_risk)}</p>
<p><strong>P0 scores</strong> Opportunity {_score(card.p0_opportunity)}
 / Explosion {_score(card.p0_explosion)}
 / Contribution {_score(card.p0_contribution)}
 {"· Explosion N/A until v7" if card.momentum_na else ""}</p>
<p><strong>Suggested contribution:</strong> {_e(card.suggested_contribution or "See open issues after Enter.")}</p>
<p class="actions">Human: {_actions(card)}</p>
"""
    if dense:
        body += _reviewer_block("Trend", card, "trend")
        body += _reviewer_block("Community", card, "community")
        body += _reviewer_block("Contributor", card, "contributor")
    return f"""
<article class="card" id="{_e(card.full_name)}">
  <h3><a href="{_e(card.html_url or "#")}">{_e(card.full_name)}</a>
  {stamp}
  <span class="stars">{_e(card.stars)}★</span></h3>
  {body}
</article>
"""


def render_board_html(board: BoardDocument) -> str:
    mode_class = "prov" if board.mode == "provisional" else "off"
    pool_rows = []
    for row in board.pool:
        pool_rows.append(
            f"""<tr>
              <td>{row.rank:02d}</td>
              <td><a href="#{_e(row.full_name)}">{_e(row.full_name)}</a></td>
              <td>{_e(row.stars)}</td>
              <td>{_e(row.growth_signal)}</td>
              <td class="st-{_e(row.status)}">{_e(row.status)}</td>
            </tr>
            <tr class="detail"><td colspan="5">{_e(row.reason or row.lightweight_score)}</td></tr>"""
        )
    short = "".join(
        f"<li><a href='#{_e(c.full_name)}'>{_e(c.full_name)}</a> "
        f"lw {_score(c.lightweight_score)} · {_e('rejected' if c.vetoed else 'reviewed')}</li>"
        for c in board.shortlist
    )
    deep = "".join(_card_html(c, dense=True) for c in board.deep)
    top = "".join(
        _card_html(c, dense=True) for c in (board.official or board.provisional)
    )
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Foreshadow Daily Board · {_e(board.date)}</title>
<style>
:root {{
  --paper: #f3efe4;
  --ink: #1c1712;
  --rule: #c9b89a;
  --stamp: #9b1d1d;
  --ok: #1f4d3a;
  --muted: #6b6258;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.45 "Iowan Old Style", Palatino, "Palatino Linotype", Georgia, serif;
}}
header.mast {{
  border-bottom: 3px double var(--ink);
  padding: 1.5rem 8vw 1rem;
}}
header.mast h1 {{
  font-size: 1.6rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  margin: 0 0 .4rem;
}}
.counts {{ display: flex; gap: 1.5rem; flex-wrap: wrap; font-variant-numeric: tabular-nums; }}
.counts b {{ display: block; font-size: 1.6rem; }}
.stamp {{
  display: inline-block;
  margin-left: .5rem;
  padding: .05rem .4rem;
  border: 2px solid var(--stamp);
  color: var(--stamp);
  font-size: .7rem;
  letter-spacing: .14em;
  transform: rotate(-6deg);
}}
.stamp-bad {{ border-color: var(--ink); color: var(--ink); }}
.{mode_class} .mode {{ color: var(--stamp); font-weight: 700; }}
main {{ padding: 1rem 8vw 4rem; }}
section.block {{
  border-top: 1px solid var(--rule);
  padding: 1.2rem 0;
}}
table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
th, td {{ text-align: left; padding: .25rem .4rem; border-bottom: 1px solid var(--rule); vertical-align: top; }}
.na {{ color: var(--stamp); font-style: italic; }}
.st-shortlisted {{ color: var(--ok); }}
.st-rejected {{ color: var(--stamp); }}
.muted {{ color: var(--muted); font-size: .88rem; }}
.card {{
  border: 1px solid var(--ink);
  padding: 1rem 1.1rem;
  margin: 1rem 0;
  background: #faf7ef;
}}
.card h3 {{ margin: 0 0 .4rem; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: .8rem; }}
.reviewer {{ margin-top: 1rem; padding-top: .6rem; border-top: 1px dashed var(--rule); }}
.exclude {{ border-left: 3px solid var(--stamp); padding-left: .6rem; }}
code {{
  font: 12px/1.3 ui-monospace, "SF Mono", Menlo, monospace;
  background: #ece6d8;
  padding: .1rem .3rem;
}}
a {{ color: inherit; }}
details.pool table tr.detail {{ display: none; color: var(--muted); font-size: .85rem; }}
details.pool[open] tr.detail {{ display: table-row; }}
footer {{ padding: 1rem 8vw 3rem; color: var(--muted); font-size: .85rem; }}
@media (max-width: 800px) {{
  .cols {{ grid-template-columns: 1fr; }}
  header.mast, main, footer {{ padding-left: 1rem; padding-right: 1rem; }}
}}
</style>
</head>
<body class="{mode_class}">
<header class="mast">
  <h1>Foreshadow · Daily Board</h1>
  <p>{_e(board.date)} · <span class="mode">{_e(board.mode.upper())}</span>
     · {_e(board.mode_reason)}</p>
  <div class="counts">
    <div><b>{board.discovered}</b> Discovered</div>
    <div><b>{board.shortlisted}</b> Shortlisted</div>
    <div><b>{board.deep_reviewed}</b> Deep reviewed</div>
    <div><b>{board.official_top5}</b> Official Top 5</div>
    <div><b>{board.provisional_count}</b> Provisional seats</div>
  </div>
  <p class="muted">Generated from {_e(board.generated_from)} · snapshot-days {board.snapshot_days}
     · {generated} UTC. Auditability is evidence, not hidden chain-of-thought.</p>
</header>
<main>
<section class="block">
  <h2>Official vs provisional</h2>
  <p>Official Top 5 still requires P0 <code>v7</code> plus Opportunity ≥ 55 and Explosion ≥ 35.
     Today official = <strong>{board.official_top5}</strong>.
     Provisional ranking exists so you can audit the funnel without inventing history.</p>
</section>
<section class="block">
  <h2>Final {("Official Top 5" if board.official else "Provisional ranking")}</h2>
  {top or "<p>None. Empty Top 5 is valid.</p>"}
</section>
<section class="block">
  <h2>Deep reviewed (Chair + three reviewers)</h2>
  {deep or "<p>None.</p>"}
</section>
<section class="block">
  <h2>Shortlist</h2>
  <ol>{short}</ol>
</section>
<section class="block">
  <h2>Candidate pool</h2>
  <details class="pool" open>
    <summary>All {board.discovered} discovered rows (click a name to jump)</summary>
    <table>
      <thead><tr><th>#</th><th>Repository</th><th>Stars</th><th>Growth</th><th>Status</th></tr></thead>
      <tbody>{"".join(pool_rows)}</tbody>
    </table>
  </details>
</section>
</main>
<footer>
  Human review stays on the CLI. Copy an action command from a card.
  Dogfood snapshots are not modified by Preview.
</footer>
</body>
</html>
"""
