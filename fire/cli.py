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
    python -m fire growth profile --name "Thabo Plumbing" --sector Plumbing --metrics m0.json
    python -m fire growth diagnose --profile thabo-plumbing
    python -m fire growth mission --profile thabo-plumbing
    python -m fire growth consent gm-xxxxxxxxxxxx --owner --customer-contact
    python -m fire growth run gm-xxxxxxxxxxxx --result "..." --evidence "..."
    python -m fire growth measure gm-xxxxxxxxxxxx --metrics m1.json
    python -m fire growth decide gm-xxxxxxxxxxxx
    python -m fire growth report gm-xxxxxxxxxxxx
    python -m fire growth missions
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, fields
from pathlib import Path

from . import __version__
from .commercial import CommercialEngine, CommercialError, PriceTier
from .coach.success_coach import BusinessSuccessCoach
from .config import load_config, paths
from .growth.diagnostic import BusinessMetrics, GrowthDiagnostic
from .growth.learning import GrowthLearningEngine, LearningError, lesson_id_for
from .growth.lifecycle import (
    LOWER_BETTER_LEVERS,
    MissionExecutionError,
    MissionRuntime,
    StepStatus,
    mission_id_for,
)
from .growth.missions import StepKind
from .growth.models import BusinessProfile, GrowthLever
from .growth.orchestrator import GrowthOrchestrator
from .onboarding.consent import ConsentProfile
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
# growth operations (Phase 7): a thin operator layer over the EXISTING
# diagnostic / coach / orchestrator / consent / lifecycle engines.
# No business logic is duplicated here; every mutation goes through those
# engines, which own persistence, consent gates and the EventLog audit trail.
# ---------------------------------------------------------------------------

class _GrowthCLIError(Exception):
    """Operator-facing usage error for the growth subcommands."""


METRIC_FIELDS = tuple(f.name for f in fields(BusinessMetrics))

# consent dimension -> the CLI flags that satisfy it (Contact/purchase gates
# also require owner authorization, per the existing ConsentManager AND rules)
_GROWTH_CONSENT_FLAGS = {
    "owner_authorized": "--owner",
    "customer_contact_authorized": "--owner --customer-contact",
    "supplier_contact_authorized": "--owner --supplier-contact",
    "purchasing_authorized": "--owner --purchasing",
}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _growth_runtime() -> MissionRuntime:
    return MissionRuntime(P["memory_dir"])


def _profiles_dir() -> Path:
    d = P["memory_dir"] / "business_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_metrics(path: str) -> BusinessMetrics:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _GrowthCLIError(f"cannot read metrics file {path}: {exc}")
    if not isinstance(data, dict):
        raise _GrowthCLIError("metrics JSON must be an object of BusinessMetrics fields")
    unknown = set(data) - set(METRIC_FIELDS)
    if unknown:
        raise _GrowthCLIError(
            f"unknown metric fields: {', '.join(sorted(unknown))} "
            f"(allowed: {', '.join(METRIC_FIELDS)})")
    try:
        return BusinessMetrics(**{k: float(v) for k, v in data.items()})
    except (TypeError, ValueError) as exc:
        raise _GrowthCLIError(f"metric values must be numeric: {exc}")


def _require_profile(slug: str | None) -> tuple[BusinessProfile, BusinessMetrics]:
    if not slug:
        raise _GrowthCLIError(
            "no profile given — persist one first: "
            "fire growth profile --name \"...\" --sector \"...\"")
    path = _profiles_dir() / f"{_re_slug(slug)}.json"
    if not path.exists():
        found = None
        for p in sorted(_profiles_dir().glob("*.json")):
            try:
                if json.loads(p.read_text(encoding="utf-8")).get("business_name", "").lower() == slug.lower():
                    found = p
                    break
            except (OSError, json.JSONDecodeError):
                continue
        if found is None:
            raise _GrowthCLIError(
                f"unknown profile '{slug}' — save it first with `fire growth profile`")
        path = found
    data = json.loads(path.read_text(encoding="utf-8"))
    prof = BusinessProfile(
        business_name=data["business_name"],
        sector=data.get("sector", ""),
        location=data.get("location", ""),
        products_services=list(data.get("products_services", [])),
        uses_whatsapp=bool(data.get("uses_whatsapp", False)),
        uses_crm=bool(data.get("uses_crm", False)),
        uses_online_sales=bool(data.get("uses_online_sales", False)),
        owner_consent=bool(data.get("owner_consent", False)),
    )
    metrics = BusinessMetrics(
        **{k: float(v) for k, v in data.get("metrics", {}).items() if k in METRIC_FIELDS})
    return prof, metrics


def _consent_from_args(args) -> ConsentProfile:
    return ConsentProfile(
        owner_authorized=bool(args.owner),
        customer_contact_authorized=bool(args.customer_contact),
        supplier_contact_authorized=bool(args.supplier_contact),
        purchasing_authorized=bool(args.purchasing),
    )


def _has_consent_flags(args) -> bool:
    return bool(args.owner or args.customer_contact
                or args.supplier_contact or args.purchasing)


def cmd_growth_profile(args):
    if args.show:
        prof, metrics = _require_profile(args.show)
        _print_json({"business": asdict(prof), "metrics": asdict(metrics)})
        return 0
    if not args.name:
        raise _GrowthCLIError(
            "provide --name to save a profile, or --show SLUG to print one")
    if args.sector is None:
        raise _GrowthCLIError("--sector is required to save a profile")
    slug = _re_slug(args.name)
    path = _profiles_dir() / f"{slug}.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = {
        "business_name": args.name,
        "sector": args.sector,
        "location": args.location if args.location is not None else prev.get("location", ""),
        "products_services": (
            [s.strip() for s in args.services.split(",") if s.strip()]
            if args.services is not None else prev.get("products_services", [])),
        "uses_whatsapp": args.whatsapp or prev.get("uses_whatsapp", False),
        "uses_crm": args.crm or prev.get("uses_crm", False),
        "uses_online_sales": args.online_sales or prev.get("uses_online_sales", False),
        "owner_consent": args.owner_consent or prev.get("owner_consent", False),
        "metrics": (asdict(_load_metrics(args.metrics))
                    if args.metrics else
                    prev.get("metrics", {k: 0 for k in METRIC_FIELDS})),
        "updated_at": _now_iso(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _growth_runtime().events.append(
        "business_profile_saved", {"profile": slug, "business": args.name})
    print(f"PROFILE {slug} saved -> {path}")
    print(f"  business: {data['business_name']} | sector: {data['sector']} | "
          f"location: {data['location'] or '-'}")
    if data["products_services"]:
        print(f"  services: {', '.join(data['products_services'])}")
    print("  metrics: " + ", ".join(f"{k}={v}" for k, v in data["metrics"].items()))
    print("  note: only operator-supplied evidence is stored; nothing is fabricated.")
    return 0


def cmd_growth_diagnose(args):
    prof, metrics = _require_profile(args.profile)
    result = GrowthDiagnostic().diagnose(prof, metrics)
    plan = BusinessSuccessCoach().audit(prof, metrics)
    print(f"BUSINESS: {prof.business_name} ({prof.sector})")
    print("\nLEVER SCORES (existing GrowthDiagnostic):")
    for lever, score in result.scores.items():
        mark = "  <-- PRIMARY" if lever is result.primary_lever else ""
        print(f"  {lever.value:16s} {score:4.1f}{mark}")
    print(f"\nPRIMARY LEVER: {result.primary_lever.value}")
    print(f"REASONING: {result.rationale}")
    print(f"\nOPPORTUNITIES (existing BusinessSuccessCoach, "
          f"priority: {plan.priority_lever.value}):")
    for o in plan.opportunities:
        marker = "*" if o.lever is plan.priority_lever else " "
        print(f" {marker} [{o.lever.value:16s}] {o.title}")
        print(f"     impact: {o.expected_impact}")
    # closed loop (Phase 8): recorded prior lessons for this business+lever
    prior = _growth_engine().retrieve(
        business=prof.business_name, lever=result.primary_lever.value)
    print("\nPRIOR LESSONS (recorded from earlier missions on this "
          "business/lever):")
    if prior:
        for l in prior:
            print(f"  - {l.lesson_id} [{l.decision}] (mission {l.mission_id}): "
                  f"{l.lesson}")
    else:
        print("  (none recorded yet)")
    return 0


def cmd_growth_mission(args):
    prof, metrics = _require_profile(args.profile)
    rt = _growth_runtime()
    mission = GrowthOrchestrator().create_mission(prof, metrics)
    # closed loop (Phase 8): carry relevant recorded prior lessons into the
    # new mission as traceable evidence (existing evidence field, additive)
    prior = _growth_engine().retrieve(
        business=mission.business_name, lever=mission.lever.value)
    for l in prior:
        mission.evidence.append(
            f"prior lesson {l.lesson_id} (mission {l.mission_id}, "
            f"decision {l.decision}): {l.lesson}")
    mid = mission_id_for(mission)
    existed = rt.path_for(mid).exists()
    mid = rt.persist(mission)
    print(f"MISSION {mid}"
          + (" (existing mission resumed — idempotent)" if existed else " (created and persisted)"))
    print(f"  business : {mission.business_name}")
    print(f"  lever    : {mission.lever.value}")
    print(f"  objective: {mission.objective}")
    print(f"  problem  : {mission.problem}")
    print(f"  status   : {mission.status.value}")
    print("  baseline : " + ", ".join(f"{k}={v}" for k, v in mission.baseline.items()))
    print("  target   : " + ", ".join(f"{k}={v:g}" for k, v in mission.target.items()))
    print("\nWORKFLOW (ordered, non-skippable):")
    for s in mission.workflow:
        perm = f"  [requires {s.requires_permission}]" if s.requires_permission else ""
        print(f"  {s.step:02d} [{s.kind.value:16s}] {s.name}{perm}")
    print("\nTEAM (registry-resolved):")
    for m in mission.agent_team:
        print(f"  {m.role:16s} {m.agent_id}")
    print("\nCONSENT GATES:")
    for g in mission.approval_gates:
        state = {True: "granted", False: "DENIED", None: "not yet evaluated"}[g.granted]
        print(f"  {g.permission} (steps {g.step_numbers}) — {state}")
        print(f"     {g.description}")
    if not mission.approval_gates:
        print("  (none)")
    print("\nSUCCESS CRITERIA:")
    for c in mission.success_criteria:
        print(f"  - {c}")
    print("KILL CRITERIA:")
    for c in mission.kill_criteria:
        print(f"  - {c}")
    print("SCALE CRITERIA:")
    for c in mission.scale_criteria:
        print(f"  - {c}")
    if prior:
        print("\nPRIOR LESSONS (recorded evidence carried into this mission):")
        for l in prior:
            print(f"  - {l.lesson_id} [{l.decision}] (mission {l.mission_id}): "
                  f"{l.lesson}")
    return 0


def cmd_growth_consent(args):
    rt = _growth_runtime()
    if _has_consent_flags(args):
        rt.apply_consent(args.mission, _consent_from_args(args))
    mission = rt.load(args.mission)
    print(f"MISSION {args.mission} — status: {mission.status.value}")
    for g in mission.approval_gates:
        state = {True: "GRANTED", False: "denied", None: "not yet evaluated"}[g.granted]
        print(f"  gate {g.permission:28s} steps {g.step_numbers} — {state}")
    if not mission.approval_gates:
        print("  (no consent gates on this mission)")
    if mission.status.value == "BLOCKED":
        print("  mission is BLOCKED: apply the missing consent dimension(s) "
              "with `fire growth consent`")
    return 0


def cmd_growth_run(args):
    rt = _growth_runtime()
    mission = rt.load(args.mission)
    step = args.step if args.step is not None else rt.next_actionable(args.mission)
    if step is None:
        st = rt.state(args.mission)
        print(f"MISSION {args.mission} — all steps complete (completed_at={st['completed_at']})")
        return 0
    step_obj = next(s for s in mission.workflow if s.step == step)
    consent = _consent_from_args(args) if _has_consent_flags(args) else None
    ex = rt.execute_step(args.mission, step, result=args.result,
                         evidence=args.evidence, consent=consent)
    if ex.blocked:
        print(f"STEP {step} BLOCKED — {ex.reason}")
        perm = ex.reason.split(": ", 1)[1] if ": " in ex.reason else ""
        if perm in _GROWTH_CONSENT_FLAGS:
            print(f"  authorize: fire growth consent {args.mission} "
                  f"{_GROWTH_CONSENT_FLAGS[perm]}")
            print(f"  then:      fire growth run {args.mission} --step {step}")
        return 2
    print(f"STEP {step} [{step_obj.kind.value}] {step_obj.name}")
    print(f"  status: {ex.status.value} | attempts: {ex.attempts}")
    if args.result:
        print(f"  result: {args.result}")
    if args.evidence:
        print(f"  evidence: {args.evidence}")
    if ex.status is StepStatus.COMPLETED and step_obj.kind is StepKind.EXECUTE_EXTERNAL:
        print("  note: external action recorded per operator input; the real-world")
        print("        action is owner-authorized and operator-attested — the CLI did not act.")
    st = rt.state(args.mission)
    if st["completed_at"]:
        print(f"MISSION {args.mission} — all steps complete (completed_at={st['completed_at']})")
        print("next: fire growth measure / decide / report")
    return 0


def cmd_growth_measure(args):
    rt = _growth_runtime()
    mission = rt.load(args.mission)
    current = _load_metrics(args.metrics)
    meas = rt.measure(args.mission, current)
    lower = mission.lever in LOWER_BETTER_LEVERS
    direction = "lower is better (cost)" if lower else "higher is better"
    print(f"MISSION {args.mission} | lever: {mission.lever.value} ({direction})")
    print(f"{'metric':24s} {'baseline':>10s} {'current':>10s} {'target':>10s} "
          f"{'progress':>10s}")
    for key, target in mission.target.items():
        base = float(mission.baseline.get(key, 0.0))
        cur = float(meas.metrics.get(key, base))
        print(f"{key:24s} {base:>10.3f} {cur:>10.3f} {float(target):>10.3f} "
              f"{meas.progress[key]:>10.3f}")
    print(f"OVERALL PROGRESS: {meas.overall:.4f}")
    print("next: fire growth decide / report")
    return 0


def cmd_growth_decide(args):
    rt = _growth_runtime()
    decision = rt.decide(args.mission)
    mission = rt.load(args.mission)
    print(decision)
    print(f"MISSION {args.mission} — status: {mission.status.value} "
          "(decision from the latest recorded measurement)")
    return 0


def cmd_growth_report(args):
    rt = _growth_runtime()
    path = rt.write_execution_report(args.mission, out_path=args.out)
    st = rt.state(args.mission)
    mission = rt.load(args.mission)
    rep = st["report"] or {}
    print(f"REPORT: {path}")
    print(f"QUALITY GATE: {rep.get('verdict')} ({rep.get('summary')})")
    print(f"MISSION {args.mission} — status: {mission.status.value} | "
          f"decision: {st['decision'] or 'pending'}")
    print(f"EVIDENCE: {len(mission.evidence)} item(s) recorded in mission state")
    return 0


def cmd_growth_missions(args):
    rt = _growth_runtime()
    ids = rt.list_missions()
    if not ids:
        print("no growth missions persisted yet")
        return 0
    print(f"{'id':20s} {'business':26s} {'lever':16s} {'status':12s} "
          f"{'decision':10s} next")
    for mid in ids:
        st = rt.state(mid)
        m = st["mission"]
        nxt = rt.next_actionable(mid)
        nxt_s = f"step {nxt}" if nxt is not None else (
            "done" if st["completed_at"] else "-")
        print(f"{mid:20s} {m['business_name'][:26]:26s} {m['lever']:16s} "
              f"{m['status']:12s} {str(st['decision'] or '-'):10s} {nxt_s}")
    return 0


def _growth_engine() -> GrowthLearningEngine:
    return GrowthLearningEngine(P["memory_dir"])


def cmd_growth_learn(args):
    engine = _growth_engine()
    pre_existing = engine.path_for(lesson_id_for(args.mission)).exists()
    lesson = engine.learn(args.mission)
    print(f"LESSON {lesson.lesson_id} ({'updated' if pre_existing else 'created'})")
    print(f"  mission    : {lesson.mission_id}")
    print(f"  business   : {lesson.business}")
    print(f"  lever      : {lesson.lever}")
    print(f"  objective  : {lesson.objective}")
    print(f"  decision   : {lesson.decision}")
    print(f"  outcome    : {lesson.outcome}")
    print(f"  observation: {lesson.observation}")
    print(f"  lesson     : {lesson.lesson}")
    print(f"  recommend  : {lesson.recommendation}")
    print(f"  confidence : {lesson.confidence} (deterministic heuristic over "
          f"evidence quantity — not statistical certainty)")
    print(f"  evidence   : {len(lesson.evidence)} item(s), "
          f"traceable to mission state")
    return 0


def cmd_growth_lessons(args):
    engine = _growth_engine()
    lessons = engine.retrieve(
        business=args.business, lever=args.lever, decision=args.decision)
    if not lessons:
        print("no lessons recorded yet (or none match the filters)")
        return 0
    print(f"LESSONS ({len(lessons)}):")
    for l in lessons:
        print(f"  {l.lesson_id}  mission={l.mission_id}  business={l.business}  "
              f"lever={l.lever}  decision={l.decision}  confidence={l.confidence}")
        print(f"      {l.lesson}")
    return 0


# ---------------------------------------------------------------------------
# commercial operations (Phase 9): evidence-bounded revenue validation.
# No receipt = no revenue. Simulated != real. Verified revenue =
# collected AND receipt exists AND simulated == false.
# ---------------------------------------------------------------------------

_PERIOD_SUFFIXES = {"mo": "month", "month": "month", "quote": "one-off",
                    "one-off": "one-off", "once": "one-off", "year": "year"}


def _commercial_engine() -> CommercialEngine:
    return CommercialEngine(P["memory_dir"])


def _parse_tiers(spec: str) -> list[PriceTier]:
    """Parse 'P1=199/mo,P2=99/mo,P3=49/quote' into PriceTier records."""
    tiers: list[PriceTier] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise CommercialError(f"invalid tier spec {part!r} (expected TIER=PRICE[/period])")
        name, rest = part.split("=", 1)
        rest = rest.strip()
        if "/" in rest:
            price_s, per = rest.rsplit("/", 1)
            period = _PERIOD_SUFFIXES.get(per.strip().lower())
            if period is None:
                raise CommercialError(
                    f"unknown period {per!r} (allowed: {', '.join(sorted(set(_PERIOD_SUFFIXES)))})")
        else:
            price_s, period = rest, "month"
        try:
            price = float(price_s.replace("R", "").strip())
        except ValueError as exc:
            raise CommercialError(f"invalid price in tier {part!r}") from exc
        tiers.append(PriceTier(tier=name.strip(), price=price, period=period))
    if not tiers:
        raise CommercialError("no price tiers given")
    return tiers


def _print_prospects() -> int:
    prospects = _commercial_engine().list_prospects()
    if not prospects:
        print("no prospects recorded")
        return 0
    print(f"PROSPECTS ({len(prospects)}):")
    for p in prospects:
        sim = " [SIMULATED]" if p.simulated else ""
        print(f"  {p.prospect_id}  {p.business:28s} {p.trade:14s} "
              f"{p.status:12s}{sim}")
    return 0


def cmd_commercial_prospect(args):
    if args.prospect_cmd == "add":
        eng = _commercial_engine()
        p = eng.add_prospect(args.business, args.trade, args.location or "",
                             notes=args.notes or "", simulated=args.simulated)
        print(f"PROSPECT {p.prospect_id} ({'SIMULATED' if p.simulated else 'real'}) — "
              f"{p.business} ({p.trade})")
        print(f"  location: {p.location or '-'} | status: {p.status}")
        if p.notes:
            print(f"  notes: {p.notes}")
        print("  deterministic id: re-adding the same business/trade/location "
              "updates this record")
        return 0
    if args.prospect_cmd == "list":
        return _print_prospects()
    p = _commercial_engine().get_prospect(args.id)
    _print_json(p.to_dict())
    return 0


def cmd_commercial_offer(args):
    if args.offer_cmd == "create":
        eng = _commercial_engine()
        offer = eng.create_offer(
            args.opportunity, _parse_tiers(args.tiers),
            unit_of_delivery=args.unit or "", promised_outcome=args.outcome or "",
            terms=args.terms or "", simulated=args.simulated)
        print(f"OFFER {offer.offer_id} (opportunity: {offer.opportunity_id} — "
              f"{offer.opportunity_name})")
        if offer.unit_of_delivery:
            print(f"  unit of delivery: {offer.unit_of_delivery}")
        if offer.promised_outcome:
            print(f"  promised outcome: {offer.promised_outcome}")
        print("  price tiers (HYPOTHESES until actually paid):")
        for t in offer.price_tiers:
            print(f"    {t.tier}: {t.price:g} /{t.period}"
                  + (f" — {t.terms}" if t.terms else ""))
        print("  references the existing Opportunity; hypothetical economics "
              "remain hypotheses")
        return 0
    offers = _commercial_engine().list_offers()
    if not offers:
        print("no offers recorded")
        return 0
    print(f"OFFERS ({len(offers)}):")
    for o in offers:
        sim = " [SIMULATED]" if o.simulated else ""
        tiers = ", ".join(f"{t.tier}={t.price:g}/{t.period}" for t in o.price_tiers)
        print(f"  {o.offer_id}  {o.opportunity_id:24s} {tiers}{sim}")
    return 0


def cmd_commercial_trial(args):
    eng = _commercial_engine()
    e = eng.start_trial(args.prospect, offer_id=args.offer, mission_id=args.mission)
    print(f"ENGAGEMENT {e.engagement_id} started — prospect {e.prospect_id} under "
          f"offer {e.offer_id}")
    if e.simulated:
        print("  [SIMULATED — never counted as verified revenue]")
    if e.mission_id:
        print(f"  attributed to growth mission: {e.mission_id}")
    print("next: fire commercial delivery record / price offer")
    return 0


def cmd_commercial_delivery(args):
    eng = _commercial_engine()
    d = eng.record_delivery(args.engagement, args.quote_n, args.requested_at,
                            args.delivered_at, args.evidence,
                            used_by_client=args.used)
    print(f"DELIVERY quote #{d.quote_n} recorded")
    print(f"  turnaround: {d.turnaround_min:.1f} min (computed from recorded timestamps)")
    print(f"  evidence: {d.evidence_path}")
    print(f"  used by client: {'yes' if d.used_by_client else 'not recorded'}")
    return 0


def cmd_commercial_price(args):
    eng = _commercial_engine()
    _, tier = eng.offer_price(args.engagement, args.tier)
    print(f"PRICE OFFERED: tier {tier.tier} — {tier.price:g} /{tier.period}")
    print("  a hypothesis until payment is recorded with a receipt")
    return 0


def cmd_commercial_payment(args):
    eng = _commercial_engine()
    tx = eng.record_payment(args.prospect, args.amount, args.receipt,
                            period=args.period, kind=args.kind,
                            delivery_cost=args.delivery_cost,
                            engagement_id=args.engagement)
    print(f"TRANSACTION {tx.transaction_id} — {tx.amount:g} {tx.currency} "
          f"/{tx.period} ({tx.kind})")
    print(f"  stage: {tx.stage} | collected_at: {tx.collected_at}")
    print(f"  receipt: {tx.receipt_path}")
    print(f"  simulated: {tx.simulated} | verified: {tx.verified}")
    if not tx.verified:
        print("  note: a simulated transaction is NEVER verified revenue")
    return 0


def cmd_commercial_revenue(args):
    s = _commercial_engine().revenue_summary()
    print("REVENUE VALIDATION SUMMARY")
    print("\nMODEL (hypotheses from existing Opportunity economics — NOT revenue):")
    for row in s["model"]:
        print(f"  - {row['opportunity']} [{row['opportunity_id']}]: "
              f"{row['economics']}  ({row['label']})")
    if not s["model"]:
        print("  (no offers recorded)")
    print(f"\nQUOTED (offered, not collected):           R{s['quoted']:,.2f}")
    print(f"INVOICED (awaiting payment):                R{s['invoiced']:,.2f}")
    print(f"COLLECTED (all, incl. simulated):           R{s['collected_all']:,.2f}")
    print(f"  of which SIMULATED (not verified):        R{s['collected_simulated']:,.2f}")
    print(f"VERIFIED REVENUE (collected+receipt+real):  R{s['verified_revenue']:,.2f}")
    print(f"  of which recurring monthly:               R{s['verified_recurring_monthly']:,.2f}")
    print(f"DELIVERY COST (verified):                   R{s['verified_delivery_cost']:,.2f}")
    print(f"GROSS MARGIN (verified):                    R{s['verified_gross_margin']:,.2f}")
    print(f"\ninvariant: {s['invariant']}")
    print(s["simulated_note"].capitalize() + ".")
    return 0


def cmd_commercial_decide(args):
    eng = _commercial_engine()
    dec = eng.decide_experiment(args.experiment)
    print(f"EXPERIMENT DECISION — {args.experiment}")
    print(f"  decision: {dec.decision}   (decision_id {dec.decision_id})")
    print("  measured numbers: " + ", ".join(f"{k}={v}" for k, v in dec.numbers.items()))
    print("  conditions (computed from recorded numbers only):")
    for k, c in dec.conditions.items():
        mark = {True: "MET", False: "not met", None: "not tracked"}[c["met"]]
        print(f"    {k:3s} [{mark:11s}] {c['detail']}")
    lid = lesson_id_for(dec.decision_id)
    print(f"\n  lesson recorded in the existing learning loop: {lid} (lever=revenue)")
    print("  retrieve: fire growth lessons --lever revenue")
    return 0


def cmd_commercial_decisions(args):
    decs = _commercial_engine().list_decisions()
    if not decs:
        print("no experiment decisions recorded")
        return 0
    print(f"DECISIONS ({len(decs)}):")
    for d in decs:
        print(f"  {d.decision_id}  {d.experiment:24s} {d.decision:14s} {d.decided_at}")
    return 0


def cmd_commercial_prospects(args):
    return _print_prospects()


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

    p_growth = sub.add_parser(
        "growth", help="growth operations: profile->diagnose->mission->consent"
                       "->run->measure->decide->report")
    gr = p_growth.add_subparsers(dest="growth_cmd", required=True)

    p_gp = gr.add_parser("profile", help="save/reload persisted business evidence")
    p_gp.add_argument("--name", help="business name (creates/updates)")
    p_gp.add_argument("--sector")
    p_gp.add_argument("--location")
    p_gp.add_argument("--services", help="comma-separated products/services")
    p_gp.add_argument("--whatsapp", action="store_true")
    p_gp.add_argument("--crm", action="store_true")
    p_gp.add_argument("--online-sales", action="store_true")
    p_gp.add_argument("--owner-consent", action="store_true",
                      help="record owner onboarding consent in the profile")
    p_gp.add_argument("--metrics", metavar="JSON",
                      help="metrics file (BusinessMetrics fields, subset ok)")
    p_gp.add_argument("--show", metavar="SLUG", help="print a persisted profile")

    p_gd = gr.add_parser("diagnose", help="score levers + prioritize opportunities")
    p_gd.add_argument("--profile", metavar="SLUG", help="persisted profile slug/name")

    p_gm = gr.add_parser("mission", help="create/persist the growth mission")
    p_gm.add_argument("--profile", metavar="SLUG", help="persisted profile slug/name")

    p_gc = gr.add_parser("consent",
                         help="apply owner consent to mission gates (or show state)")
    p_gc.add_argument("mission", help="mission id (gm-...)")
    p_gc.add_argument("--owner", action="store_true")
    p_gc.add_argument("--customer-contact", action="store_true")
    p_gc.add_argument("--supplier-contact", action="store_true")
    p_gc.add_argument("--purchasing", action="store_true")

    p_gr = gr.add_parser("run", help="execute the next actionable step (or --step N)")
    p_gr.add_argument("mission", help="mission id (gm-...)")
    p_gr.add_argument("--step", type=int, default=None)
    p_gr.add_argument("--result", default="",
                      help="operator-attested result of the performed action")
    p_gr.add_argument("--evidence", default="",
                      help="operator-attested evidence for the performed action")
    p_gr.add_argument("--owner", action="store_true")
    p_gr.add_argument("--customer-contact", action="store_true")
    p_gr.add_argument("--supplier-contact", action="store_true")
    p_gr.add_argument("--purchasing", action="store_true")

    p_gme = gr.add_parser("measure", help="record current metrics vs baseline/target")
    p_gme.add_argument("mission", help="mission id (gm-...)")
    p_gme.add_argument("--metrics", required=True, metavar="JSON",
                       help="metrics file (BusinessMetrics fields, subset ok)")

    p_gde = gr.add_parser("decide", help="SCALE / OPTIMIZE / KILL from latest measurement")
    p_gde.add_argument("mission", help="mission id (gm-...)")

    p_gre = gr.add_parser("report", help="write the execution report via the quality gate")
    p_gre.add_argument("mission", help="mission id (gm-...)")
    p_gre.add_argument("--out", default=None, metavar="PATH")

    gr.add_parser("missions", help="list persisted growth missions")

    p_gl = gr.add_parser("learn",
                         help="extract + persist a lesson from a decided mission")
    p_gl.add_argument("--mission", required=True, help="mission id (gm-...)")

    p_gls = gr.add_parser("lessons", help="list recorded lessons (filterable)")
    p_gls.add_argument("--business", default=None)
    p_gls.add_argument("--lever", default=None,
                       choices=[l.value for l in GrowthLever] + ["revenue"])
    p_gls.add_argument("--decision", default=None,
                       choices=["SCALE", "OPTIMIZE", "KILL"])

    p_com = sub.add_parser(
        "commercial", help="revenue validation: prospects, offers, trials, "
                           "deliveries, payments, verified revenue")
    com = p_com.add_subparsers(dest="com_cmd", required=True)

    p_cp = com.add_parser("prospect", help="record/inspect prospects")
    cps = p_cp.add_subparsers(dest="prospect_cmd", required=True)
    p_cpa = cps.add_parser("add", help="add a prospect (deterministic id)")
    p_cpa.add_argument("--business", required=True)
    p_cpa.add_argument("--trade", required=True)
    p_cpa.add_argument("--location", default="")
    p_cpa.add_argument("--notes", default="")
    p_cpa.add_argument("--simulated", action="store_true",
                       help="mark as simulated (never verified revenue)")
    cps.add_parser("list", help="list prospects")
    p_cpsh = cps.add_parser("show", help="print a prospect record")
    p_cpsh.add_argument("id", help="prospect id (pr-...)")

    p_co = com.add_parser("offer", help="offers referencing existing opportunities")
    cos = p_co.add_subparsers(dest="offer_cmd", required=True)
    p_coc = cos.add_parser("create", help="create an offer from an existing Opportunity")
    p_coc.add_argument("--opportunity", required=True,
                       help="existing Opportunity id (e.g. opp-wa-voice-quote)")
    p_coc.add_argument("--tiers", required=True,
                       help='e.g. "P1=199/mo,P2=99/mo,P3=49/quote"')
    p_coc.add_argument("--unit", default="", help="unit of delivery")
    p_coc.add_argument("--outcome", default="", help="promised measurable outcome")
    p_coc.add_argument("--terms", default="")
    p_coc.add_argument("--simulated", action="store_true")
    cos.add_parser("list", help="list offers")

    p_ct = com.add_parser("trial", help="start a trial engagement")
    p_cts = p_ct.add_subparsers(dest="trial_cmd", required=True)
    p_ctst = p_cts.add_parser("start")
    p_ctst.add_argument("--prospect", required=True)
    p_ctst.add_argument("--offer", default=None)
    p_ctst.add_argument("--mission", default=None,
                        help="optional growth mission id (attribution)")

    p_cd = com.add_parser("delivery", help="record a delivered unit (evidence required)")
    p_cds = p_cd.add_subparsers(dest="delivery_cmd", required=True)
    p_cdr = p_cds.add_parser("record")
    p_cdr.add_argument("--engagement", required=True)
    p_cdr.add_argument("--quote-n", type=int, required=True)
    p_cdr.add_argument("--requested-at", required=True, help="ISO timestamp")
    p_cdr.add_argument("--delivered-at", required=True, help="ISO timestamp")
    p_cdr.add_argument("--evidence", required=True,
                       help="path to the evidence file (must exist)")
    p_cdr.add_argument("--used", action="store_true",
                       help="end client used the delivered unit")

    p_cc = com.add_parser("price", help="offer a price tier")
    p_ccs = p_cc.add_subparsers(dest="price_cmd", required=True)
    p_cco = p_ccs.add_parser("offer")
    p_cco.add_argument("--engagement", required=True)
    p_cco.add_argument("--tier", required=True)

    p_cpay = com.add_parser("payment", help="record a payment (receipt REQUIRED)")
    p_cpay_s = p_cpay.add_subparsers(dest="payment_cmd", required=True)
    p_cpay_r = p_cpay_s.add_parser("record")
    p_cpay_r.add_argument("--prospect", required=True)
    p_cpay_r.add_argument("--amount", type=float, required=True)
    p_cpay_r.add_argument("--period", default="month",
                          choices=["month", "one-off", "year"])
    p_cpay_r.add_argument("--kind", default="SUBSCRIPTION",
                          choices=["SUBSCRIPTION", "ONE_OFF", "REFUND"])
    p_cpay_r.add_argument("--receipt", required=True,
                          help="path to the payment receipt file (must exist)")
    p_cpay_r.add_argument("--delivery-cost", type=float, default=0.0)
    p_cpay_r.add_argument("--engagement", default=None)

    com.add_parser("revenue",
                   help="staged revenue summary (modelled vs verified)")
    p_cdec = com.add_parser("decide",
                            help="compute K/O/S from recorded numbers + record a lesson")
    p_cdec.add_argument("--experiment", required=True)
    com.add_parser("decisions", help="list experiment decisions")
    com.add_parser("prospects", help="list prospects")

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
        if args.cmd == "growth":
            try:
                if args.growth_cmd == "profile":
                    return cmd_growth_profile(args)
                if args.growth_cmd == "diagnose":
                    return cmd_growth_diagnose(args)
                if args.growth_cmd == "mission":
                    return cmd_growth_mission(args)
                if args.growth_cmd == "consent":
                    return cmd_growth_consent(args)
                if args.growth_cmd == "run":
                    return cmd_growth_run(args)
                if args.growth_cmd == "measure":
                    return cmd_growth_measure(args)
                if args.growth_cmd == "decide":
                    return cmd_growth_decide(args)
                if args.growth_cmd == "report":
                    return cmd_growth_report(args)
                if args.growth_cmd == "missions":
                    return cmd_growth_missions(args)
                if args.growth_cmd == "learn":
                    return cmd_growth_learn(args)
                if args.growth_cmd == "lessons":
                    return cmd_growth_lessons(args)
            except (MissionExecutionError, _GrowthCLIError, LearningError) as exc:
                print(f"[fire] error: {exc}", file=sys.stderr)
                return 1
        if args.cmd == "commercial":
            try:
                if args.com_cmd == "prospect":
                    return cmd_commercial_prospect(args)
                if args.com_cmd == "offer":
                    return cmd_commercial_offer(args)
                if args.com_cmd == "trial":
                    return cmd_commercial_trial(args)
                if args.com_cmd == "delivery":
                    return cmd_commercial_delivery(args)
                if args.com_cmd == "price":
                    return cmd_commercial_price(args)
                if args.com_cmd == "payment":
                    return cmd_commercial_payment(args)
                if args.com_cmd == "revenue":
                    return cmd_commercial_revenue(args)
                if args.com_cmd == "decide":
                    return cmd_commercial_decide(args)
                if args.com_cmd == "decisions":
                    return cmd_commercial_decisions(args)
                if args.com_cmd == "prospects":
                    return cmd_commercial_prospects(args)
            except CommercialError as exc:
                print(f"[fire] error: {exc}", file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
