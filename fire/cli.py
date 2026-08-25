"""PROJECT FIRE CLI.

Usage examples:
    python -m fire registry build
    python -m fire registry stats
    python -m fire search "voice quoting tradespeople south africa"
    python -m fire mission "Find the highest-potential business opportunity ..."
    python -m fire team "Build an MVP for a WhatsApp voice-note quote bot"
    python -m fire materialize --mission "voice-quote-bot"
    python -m fire hunt
    python -m fire evaluate reports/hunt_report.md
    python -m fire revenue
    python -m fire dashboard
    python -m fire status
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import load_config, paths
from .dashboard import write_dashboard
from .memory import EventLog
from .models import AgentRecord, RevenueEngine
from .opportunity import run_hunt, save_hunt_report
from .quality import evaluate_artifact
from .registry import CapabilitySearch, build_registry, load_registry, parse_agent_file
from .kernel import mission_to_plan
from .revenue import capacity_scenario, portfolio

CFG = load_config()
P = paths(CFG)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _search() -> CapabilitySearch:
    return CapabilitySearch(load_registry(CFG))


def _log() -> EventLog:
    return EventLog(P["memory_dir"])


def _print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_registry_build(args):
    records, stats = build_registry(CFG)
    print(f"[fire] indexed {stats.total_agents} agents -> {stats.index_file}")
    print(f"[fire] divisions: {len(stats.departments)}")
    print(f"[fire] no-frontmatter files skipped: {stats.agents_without_frontmatter}")
    return 0


def cmd_registry_stats(args):
    records = load_registry(CFG)
    stats = {
        "agents": len(records),
        "by_department": _counts(r.department for r in records),
        "by_stage": _counts(s for r in records for s in r.lifecycle_stages),
        "by_risk": _counts(r.risk_level for r in records),
        "top_tools": dict(sorted(_counts(t for r in records for t in r.tools).items(),
                                 key=lambda kv: -kv[1])[:15]),
        "index_file": str(P["registry_file"]),
    }
    _print_json(stats)
    return 0


def _counts(items) -> dict:
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def cmd_search(args):
    s = _search()
    hits = s.search(args.query, top=args.top, department=args.department)
    if not hits:
        print("[fire] no matches")
        return 1
    for h in hits:
        print(f"{h['emoji']} {h['agent_id']:45s} {h['score']:6.2f}  "
              f"({h['department']}) terms={','.join(h['matched_terms'][:6])}")
        if args.verbose:
            print(f"     caps: {', '.join(h['capabilities'][:4])}")
    print(f"\n[fire] {len(hits)} of {s.snapshot_meta()['indexed']} agents returned "
          f"(lazy: only these are activated)")
    return 0


def cmd_mission(args):
    s = _search()
    log = _log()
    plan = mission_to_plan(args.mission, s, max_size=args.max_team)
    rec = log.start_mission(args.mission, plan["objective"]["intent"], plan["team"])
    plan["mission_id"] = rec.mission_id
    _print_json(plan)
    print(f"\n[fire] mission {rec.mission_id} registered in memory "
          f"({len(plan['team'])} agents activated of {s.snapshot_meta()['indexed']})",
          file=sys.stderr)
    return 0


def cmd_team(args):
    s = _search()
    plan = mission_to_plan(args.mission, s, max_size=args.max_team)
    print(f"INTENT: {plan['objective']['intent']}")
    print(f"STAGES: {', '.join(plan['objective']['stages'])}")
    print(f"DEPTS : {', '.join(plan['objective']['departments'])}")
    print(f"CONSTRAINTS: {plan['objective']['constraints']}")
    print("\nTEAM (on-demand activation):")
    for m in plan["team"]:
        print(f"  - {m['agent_id']:42s} role={m['role']:12s} score={m['score']:.2f}")
    print("\nWORKFLOW:")
    for step in plan["workflow"]["steps"]:
        print(f"  [{step['phase']:9s}] step {step['step']:02d}  "
              f"{step['agent_id'] or '(kernel)':42s} {step['role']}")
    return 0


def cmd_materialize(args):
    """Lazy/on-demand retrieval: copy ONLY the selected agents into a team pack."""
    s = _search()
    plan = mission_to_plan(args.mission, s, max_size=args.max_team)
    team = plan["team"]
    slug = _re_slug(args.mission)
    dest = P["artifacts_dir"] / "teams" / slug
    dest.mkdir(parents=True, exist_ok=True)

    manifest = {"mission": args.mission, "mission_id": None, "agents": []}
    for m in team:
        rec = s.get(m["agent_id"])
        if not rec:
            continue
        src = Path(rec.source_path)
        if not src.exists():
            print(f"[fire] WARN: source missing for {rec.agent_id} ({src})")
            continue
        target = dest / f"{m['role']}--{rec.agent_id}.md"
        shutil.copyfile(src, target)
        manifest["agents"].append({
            "agent_id": rec.agent_id, "role": m["role"], "score": m["score"],
            "source": rec.source_path,
        })
    # orchestrator brief
    brief = {
        "mission": args.mission,
        "objective": plan["objective"],
        "workflow": plan["workflow"],
        "team": manifest["agents"],
        "instructions": (
            "Use ONLY the agents in this pack. Sequence them per the workflow. "
            "Every deliverable goes through the quality gate (GO/REVISE/NO-GO). "
            "Record results in memory before starting the next phase."
        ),
    }
    (dest / "00_mission_brief.json").write_text(
        json.dumps(brief, indent=2), encoding="utf-8")
    print(f"[fire] team pack materialized -> {dest}")
    print(f"[fire] {len(manifest['agents'])} agents activated "
          f"of {s.snapshot_meta()['indexed']} indexed (lazy activation)")
    return 0


def _re_slug(text: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "mission"


def cmd_hunt(args):
    s = _search()
    opps = run_hunt(search=s)
    report_path = P["reports_dir"] / "opportunity_hunt.json"
    save_hunt_report(opps, report_path)
    log = _log()
    log.append("opportunity_hunt", {"count": len(opps), "report": str(report_path)})
    for i, o in enumerate(opps[:args.top], 1):
        print(f"{i:2d}. [{o.weighted_score:4.2f}] {o.name}")
        print(f"     pricing: {o.pricing} | why: {', '.join(o.reasons)}")
    print(f"\n[fire] full hunt -> {report_path}")
    return 0


def cmd_evaluate(args):
    ev = evaluate_artifact(args.path)
    print(f"VERDICT: {ev.verdict}  ({ev.summary})")
    for c in ev.checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}" if c.detail else f"  [{mark}] {c.name}")
    return 0 if ev.verdict == "GO" else 2


def cmd_revenue(args):
    engines = [
        RevenueEngine("WA Voice-Quote (10 subs)", 199, "month", 10, cost_month=500),
        RevenueEngine("CV->ATS (one-offs)", 99, "one-off", 20, cost_month=100),
        RevenueEngine("Tenant Demand Letters", 150, "one-off", 15, cost_month=50),
        RevenueEngine("Invoice Chaser (recovered)", 0.03, "percent", 20_000, cost_month=0),
        RevenueEngine("Loom->SOP (10 subs)", 15, "month", 10, cost_month=40),
    ]
    port = portfolio(engines)
    cap = capacity_scenario(target_daily_zar=CFG["north_star_daily_zar"])
    out = {"portfolio": port, "capacity": cap,
           "note": "All figures are MODEL hypotheses for illustration, not realised revenue."}
    _print_json(out)
    return 0


def cmd_dashboard(args):
    records = load_registry(CFG)
    stats = _registry_stats(records)
    s = _search()
    opps = run_hunt(search=s)
    log = _log()
    missions = [m.to_dict() for m in log.all_missions()]

    engines = [
        RevenueEngine("WA Voice-Quote", 199, "month", 10, cost_month=500),
        RevenueEngine("CV->ATS", 99, "one-off", 20, cost_month=100),
        RevenueEngine("Tenant Demand Letters", 150, "one-off", 15, cost_month=50),
        RevenueEngine("Invoice Chaser", 0.03, "percent", 20_000),
        RevenueEngine("Loom->SOP", 15, "month", 10, cost_month=40),
    ]
    port = portfolio(engines)
    cap = capacity_scenario(target_daily_zar=CFG["north_star_daily_zar"])
    dest = write_dashboard(
        P["dashboard_dir"] / "index.html",
        stats=stats, opps=opps, mission_meta=missions,
        revenue=port, capacity=cap, version=__version__,
    )
    print(f"[fire] control room -> {dest}")
    return 0


def _registry_stats(records: list[AgentRecord]):
    from .models import RegistryStats
    stats = RegistryStats(total_agents=len(records))
    for r in records:
        stats.departments[r.department] = stats.departments.get(r.department, 0) + 1
        for st in r.lifecycle_stages:
            stats.stages[st] = stats.stages.get(st, 0) + 1
        for t in r.tools:
            stats.tools[t] = stats.tools.get(t, 0) + 1
    stats.index_file = str(P["registry_file"])
    return stats


def cmd_status(args):
    records = load_registry(CFG)
    log = _log()
    missions = log.all_missions()
    print(f"[fire] v{__version__}")
    print(f"[fire] agents indexed       : {len(records)}")
    print(f"[fire] divisions            : {len({r.department for r in records})}")
    print(f"[fire] missions recorded    : {len(missions)}")
    print(f"[fire] running missions     : {sum(1 for m in missions if m.status == 'running')}")
    print(f"[fire] registry file        : {P['registry_file']}")
    print(f"[fire] agent library source : {P['agent_library']}")
    print(f"[fire] north star           : R{CFG['north_star_daily_zar']:,.0f}/day (capacity target)")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(prog="fire", description="PROJECT FIRE — AI business operating system")
    parser.add_argument("--version", action="version", version=f"fire {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("registry", help="build/stats the agent registry")
    reg_sub = p_reg.add_subparsers(dest="reg_cmd", required=True)
    reg_sub.add_parser("build", help="build agent_registry.json from the library")
    reg_sub.add_parser("stats", help="registry statistics")

    p_search = sub.add_parser("search", help="capability search")
    p_search.add_argument("query")
    p_search.add_argument("--top", type=int, default=10)
    p_search.add_argument("--department", default=None)
    p_search.add_argument("--verbose", action="store_true")

    p_mission = sub.add_parser("mission", help="parse a mission into objective+team+workflow")
    p_mission.add_argument("mission")
    p_mission.add_argument("--max-team", type=int, default=6)

    p_team = sub.add_parser("team", help="show the assembled team for a mission")
    p_team.add_argument("mission")
    p_team.add_argument("--max-team", type=int, default=6)

    p_mat = sub.add_parser("materialize", help="lazily copy only required agents into a team pack")
    p_mat.add_argument("mission")
    p_mat.add_argument("--max-team", type=int, default=6)

    p_hunt = sub.add_parser("hunt", help="run the opportunity engine")
    p_hunt.add_argument("--top", type=int, default=10)

    p_ev = sub.add_parser("evaluate", help="quality/reality gate on an artifact")
    p_ev.add_argument("path")

    p_rev = sub.add_parser("revenue", help="revenue model + capacity scenario")

    p_dash = sub.add_parser("dashboard", help="generate control room HTML")

    p_stat = sub.add_parser("status", help="system status")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "registry":
            if args.reg_cmd == "build":
                return cmd_registry_build(args)
            return cmd_registry_stats(args)
        if args.cmd == "search":
            return cmd_search(args)
        if args.cmd == "mission":
            return cmd_mission(args)
        if args.cmd == "team":
            return cmd_team(args)
        if args.cmd == "materialize":
            return cmd_materialize(args)
        if args.cmd == "hunt":
            return cmd_hunt(args)
        if args.cmd == "evaluate":
            return cmd_evaluate(args)
        if args.cmd == "revenue":
            return cmd_revenue(args)
        if args.cmd == "dashboard":
            return cmd_dashboard(args)
        if args.cmd == "status":
            return cmd_status(args)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
