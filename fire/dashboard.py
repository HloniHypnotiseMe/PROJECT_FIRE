"""Control Room: static operational dashboard (no external assets).

Generated HTML with inline CSS so it renders anywhere, including sandboxed
previews. Shows system health, registry stats, active missions, ranked
opportunities, revenue model and R1M/day capacity framing.
"""
from __future__ import annotations

import html
from pathlib import Path

from .models import RegistryStats
from .opportunity import Opportunity

CSS = """
:root{--bg:#0b0f1a;--panel:#111827;--line:#1f2937;--txt:#e5e7eb;--mut:#9ca3af;
--acc:#f59e0b;--ok:#34d399;--warn:#fbbf24;--bad:#f87171;--blue:#60a5fa;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;padding:24px}
header{display:flex;align-items:baseline;gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:20px}
h1{font-size:22px;letter-spacing:2px}
h1 .dot{color:var(--acc)}
.tag{color:var(--mut);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:24px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.card .num{font-size:26px;font-weight:700;color:var(--acc)}
.card .lbl{color:var(--mut);font-size:12px;margin-top:4px}
.card .sub{color:var(--mut);font-size:11px;margin-top:2px}
h2{font-size:15px;margin:20px 0 10px;color:var(--acc);text-transform:uppercase;letter-spacing:1px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--mut);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);font-weight:600}
td{padding:8px 10px;border-bottom:1px solid #161f2f;vertical-align:top}
.ok{color:var(--ok)} .warn{color:var(--warn)} .bad{color:var(--bad)}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;border:1px solid var(--line);margin:1px 2px}
.warnbox{border-left:3px solid var(--warn);background:#1c1917;padding:10px 14px;border-radius:6px;font-size:12px;margin:8px 0;color:#fde68a}
footer{margin-top:28px;color:var(--mut);font-size:11px;border-top:1px solid var(--line);padding-top:12px}
"""


def _score_color(s: float) -> str:
    if s >= 8.0:
        return "ok"
    if s >= 6.5:
        return "warn"
    return "bad"


def render_dashboard(stats: RegistryStats,
                     opps: list[Opportunity],
                     mission_meta: list[dict],
                     revenue: dict,
                     capacity: dict,
                     version: str) -> str:
    rows: list[str] = []
    top_opps = opps[:10]

    cards = [
        ("AGENTS INDEXED", str(stats.total_agents), f"{len(stats.departments)} divisions"),
        ("STAGE TAGS", str(sum(stats.stages.values())), "lifecycle mappings"),
        ("OPPORTUNITIES", str(len(opps)), "scored & ranked"),
        ("TOP SCORE", f"{top_opps[0].weighted_score:.1f}" if top_opps else "-",
         top_opps[0].name if top_opps else ""),
        ("PORTFOLIO MRR (model)", f"R{revenue['total_mrr']:,.0f}", "hypothesis, not realised"),
        ("NORTH STAR", "R1,000,000/day", "capacity target"),
    ]
    for num, lbl, sub in cards:
        rows.append(f'<div class="card"><div class="num">{html.escape(num)}</div>'
                    f'<div class="lbl">{html.escape(lbl)}</div>'
                    f'<div class="sub">{html.escape(sub)}</div></div>')

    # divisions
    dept_rows = "".join(
        f"<tr><td>{html.escape(d)}</td><td>{n}</td></tr>"
        for d, n in sorted(stats.departments.items(), key=lambda kv: -kv[1])
    )

    # opportunities
    opp_rows = "".join(
        f'<tr><td class="mono">{i+1}</td>'
        f'<td>{html.escape(o.name)}</td>'
        f'<td class="{_score_color(o.weighted_score)}">{o.weighted_score:.2f}</td>'
        f'<td>{", ".join(html.escape(r) for r in o.reasons)}</td>'
        f'<td class="mono">{html.escape(o.pricing)}</td></tr>'
        for i, o in enumerate(top_opps)
    )

    # missions
    mission_rows = "".join(
        f'<tr><td class="mono">{html.escape(m.get("mission_id",""))}</td>'
        f'<td>{html.escape(m.get("objective",""))[:90]}</td>'
        f'<td>{html.escape(m.get("status",""))}</td></tr>'
        for m in mission_meta[-8:]
    ) or '<tr><td colspan="3" class="mut">No missions recorded yet</td></tr>'

    # revenue
    rev_rows = "".join(
        f"<tr><td>{html.escape(r['engine'])}</td><td>R{r['monthly_revenue']:,.0f}</td>"
        f"<td>R{r['monthly_profit']:,.0f}</td><td>{r['gross_margin_pct']}%</td></tr>"
        for r in revenue["engines"]
    ) or '<tr><td colspan="4" class="mut">No revenue engines configured</td></tr>'

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PROJECT FIRE — Control Room</title><style>{CSS}</style></head>
<body>
<header><h1><span class="dot">FIRE</span> CONTROL ROOM</h1>
<span class="tag">AI Business Operating System · v{html.escape(version)}</span>
<span class="tag">GITHUB = canonical fabric · LOCAL = control node · RUNTIME = on-demand</span></header>

<div class="grid">{''.join(rows)}</div>

<div class="warnbox">⚠️ All revenue figures are HYPOTHESIS / CAPACITY MODEL values, not realised
revenue. FIRE's reality engine gates every claim before it is marked as achieved.</div>

<h2>System Health — Registry</h2>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
<div class="card"><h2 style="margin:0 0 8px">Divisions</h2>
<table><tr><th>Department</th><th>Agents</th></tr>{dept_rows}</table></div>
<div class="card"><h2 style="margin:0 0 8px">Active Missions</h2>
<table><tr><th>ID</th><th>Objective</th><th>Status</th></tr>{mission_rows}</table></div>
</div>

<h2>Opportunity Ranking (hypothesis scores)</h2>
<table><tr><th>#</th><th>Opportunity</th><th>Score</th><th>Why</th><th>Pricing</th></tr>{opp_rows}</table>

<h2>Revenue Model (per engine, hypothesis)</h2>
<table><tr><th>Engine</th><th>MRR (model)</th><th>Profit (model)</th><th>Margin</th></tr>{rev_rows}</table>

<h2>North Star — Capacity Model</h2>
<div class="card"><div class="num">R{capacity['target_daily_zar']:,.0f}/day</div>
<div class="lbl">{capacity['label']}</div>
<div class="sub">≈ {capacity['engines_needed']} revenue engines at R{capacity['avg_daily_rev_per_engine']:,.0f}/day each · {html.escape(capacity['formula'])}</div></div>

<footer>PROJECT FIRE · registry index: {html.escape(stats.index_file)} · generated {html.escape(__import__('datetime').datetime.now().isoformat(timespec='minutes'))}</footer>
</body></html>"""
    return doc


def write_dashboard(dest: Path, **kwargs) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_dashboard(**kwargs), encoding="utf-8")
    return dest
