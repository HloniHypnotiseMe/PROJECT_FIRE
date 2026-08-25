"""Command Kernel: natural-language missions -> objective -> agent team -> workflow.

The kernel is the entry point of FIRE. It translates a mission statement into
an Objective, uses the registry to select ONLY the agents needed, assembles a
team, and produces an ordered workflow with deliverables and success metrics.
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Objective, TeamMember, Workflow, WorkflowStep
from .registry import CapabilitySearch, tokenize

# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "find": ["find", "discover", "identify", "hunt", "research", "what is the highest"],
    "build": ["build", "create", "develop", "ship", "implement", "make", "prototype",
              "mvp", "stand up", "construct"],
    "launch": ["launch", "release", "go to market", "gtm", "deploy", "roll out"],
    "audit": ["audit", "review", "evaluate", "assess", "check", "inspect", "due diligence"],
    "validate": ["validate", "test", "experiment", "prove", "verify"],
    "optimize": ["optimize", "improve", "scale", "grow", "increase", "reduce"],
    "sell": ["sell", "outbound", "pitch", "close", "acquire customers", "gtm for"],
}

# domain keywords -> departments (may hit multiple).
# All regexes use word boundaries: loose substrings (ar/app/ui) over-match.
DOMAIN_MAP: list[tuple[str, list[str]]] = [
    (r"\bwhatsapp\b|\bvoice\s*notes?\b|\btwilio\b|\bmessaging\b|\bsms\b|\bchatbot\b",
     ["engineering", "sales"]),
    (r"\bquote[sd]?\b|\bquotation\b|\binvoic\w*\b|\bbookkeep\w*\b|\baccount\w*\b|\btax\b|"
     r"\bfinanc\w*\b|\brevenue\b|\bpayment\b|\bbilling\b|\bcash\s*flow\b",
     ["finance", "engineering"]),
    (r"\btiktok\b|\binstagram\b|\blinkedin\b|\btwitter\b|\bfacebook\b|\bsocial\b|"
     r"\bcontent\b|\bseo\b|\bblog\b|\bpodcast\b|\byoutube\b|\bcarousel\b|\bcopy\b|\bcampaign\b",
     ["marketing"]),
    (r"\bads\b|\bppc\b|\bpaid\s*media\b|\bgoogle\s*ads\b|\bmeta\s*ads\b", ["paid-media", "marketing"]),
    (r"\bsales\b|\boutbound\b|\bpipeline\b|\bprospect\b|\bdeals?\b|\bclos\w*\b", ["sales"]),
    (r"\blegal\b|\bcontract\b|\bcompliance\b|\btenant\b|\beviction\b|\bconsumer\s*protection\b|"
     r"\bpopia\b|\bgdpr\b|\bregulatory\b", ["specialized"]),
    (r"\brecruit\w*\b|\bcv\b|\bresume\b|\bats\b|\bhiring\b|\bhr\b|\bonboard\w*\b",
     ["specialized", "engineering"]),
    (r"\bfrontend\b|\bweb\s*app\b|\bwebsite\b|\blanding\s*page\b|\bui\b|\breact\b",
     ["engineering", "design"]),
    (r"\bbackend\b|\bapi\b|\bserver\b|\bdatabase\b|\barchitecture\b|\bcloud\b|\binfra\w*\b",
     ["engineering"]),
    (r"\bmobile\b|\bapp\b|\bapps\b|\bios\b|\bandroid\b|\bflutter\b", ["engineering"]),
    (r"\bmvp\b|\bprototype\b|\bproduct\b", ["engineering", "product"]),
    (r"\bdesign\b|\bbrand\b|\bvisual\b|\bsleeve\b|\balbum\s*art\b|\blogo\b", ["design"]),
    (r"\bgames?\b|\bunity\b|\bunreal\b|\bgodot\b|\broblox\b|\bblender\b", ["game-development"]),
    (r"\btest\w*\b|\bqa\b|\bquality\b|\bbenchmark\b|\breliability\b", ["testing"]),
    (r"\bsupport\b|\bcustomer\s*service\b|\bhelpdesk\b|\btriage\b", ["support"]),
    (r"\bresearch\b|\bmarket\b|\btrend\b|\bopportunit\w*\b", ["product", "strategy", "academic"]),
    (r"\bsecurity\b|\bthreat\b|\bpentest\b|\bvulnerab\w*\b|\baudit\b", ["security"]),
    (r"\bspatial\b|\bvision\s*os\b|\bxr\b|\bimmersive\b|\bar\b|\bvr\b", ["spatial-computing"]),
    (r"\bhealth\w*\b|\bmedical\b|\bclinic\b|\bpatient\b", ["healthcare", "specialized"]),
    (r"\bgis\b|\bgeospatial\b|\blocation\b", ["gis"]),
    (r"\bstrateg\w*\b|\bplaybook\b|\brunbook\b|\bpilot\b|\bgovernance\b",
     ["strategy", "project-management"]),
]

STAGE_KEYWORDS = {
    "discover": ["research", "discover", "trend", "opportunity", "hunt", "explore"],
    "validate": ["validate", "experiment", "prove", "feedback", "hypothesis", "evidence"],
    "design": ["design", "ux", "ui", "brand", "visual"],
    "build": ["build", "develop", "mvp", "prototype", "implement", "code", "create"],
    "launch": ["launch", "release", "go to market", "gtm", "deploy"],
    "sell": ["sell", "outbound", "pitch", "customers", "acquire"],
    "operate": ["operate", "support", "run", "maintain"],
    "optimize": ["optimize", "grow", "scale", "improve", "retention"],
}

DELIVERABLE_BY_INTENT = {
    "find": "Opportunity ranking with evidence, economics, validation experiment, kill/scale criteria",
    "build": "MVP build plan + day-1 code + launch checklist",
    "launch": "Launch plan with channel playbook, copy, and success metrics",
    "audit": "Audit report with findings, risks, and prioritized fixes",
    "validate": "Validation experiment design with success/failure thresholds",
    "optimize": "Optimization roadmap with metrics baseline and experiments",
    "sell": "Outbound/GtM script with persona, message, and close play",
    "execute": "Execution plan with team, workflow, and deliverables",
}

# ---------------------------------------------------------------------------
# Objective parsing
# ---------------------------------------------------------------------------


def parse_objective(raw: str) -> Objective:
    low = raw.lower()
    intent = "execute"
    best = 0
    for name, kws in INTENT_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in low)
        if hits > best:
            best, intent = hits, name

    departments = []
    for pattern, depts in DOMAIN_MAP:
        if re.search(pattern, low):
            for d in depts:
                if d not in departments:
                    departments.append(d)

    stages = []
    for stage, kws in STAGE_KEYWORDS.items():
        if any(kw in low for kw in kws):
            stages.append(stage)

    keywords = tokenize(raw)

    constraints: dict = {}
    m = re.search(r"R\s?([\d,]+)", raw)
    if m:
        constraints["price_zar"] = float(m.group(1).replace(",", ""))
    m = re.search(r"\$\s?([\d,]+)", raw)
    if m:
        constraints["price_usd"] = float(m.group(1).replace(",", ""))
    for loc in ("south africa", "sa", "johannesburg", "cape town", "joburg", "jhb"):
        if loc in low:
            constraints["location"] = "South Africa"
            break
    if "recurring" in low or "mrr" in low:
        constraints["recurring"] = True
    if re.search(r"\bper\s*(day|month)\b|\bdaily\b", low):
        constraints["cadence"] = "daily" if "day" in low else "monthly"

    return Objective(
        raw=raw, intent=intent, departments=departments, stages=stages,
        keywords=keywords, constraints=constraints,
        deliverable=DELIVERABLE_BY_INTENT.get(intent, DELIVERABLE_BY_INTENT["execute"]),
    )


# ---------------------------------------------------------------------------
# Team assembly
# ---------------------------------------------------------------------------

ORCHESTRATOR_PREFERENCE = [
    "specialized.agents-orchestrator",
    "specialized.workflow-architect",
    "project-management.project-shepherd",
]

# department-specific seed terms appended to the objective query so the
# within-department pick is relevant to that department's function
DEPT_SEED = {
    "engineering": "build mvp prototype implementation architecture",
    "marketing": "campaign content growth strategy",
    "sales": "sales outbound pitch proposal close",
    "finance": "finance accounting analysis forecasting",
    "product": "product management prioritization roadmap",
    "design": "design brand visual creative",
    "testing": "testing quality assurance verification",
    "specialized": "operations compliance workflow coordination",
    "support": "support customer service resolution",
    "security": "security threat risk vulnerability",
    "paid-media": "paid media ads campaign budget",
    "project-management": "project planning tracking delivery",
    "strategy": "strategy playbook planning",
    "academic": "research analysis writing",
    "healthcare": "healthcare clinical patient care",
    "gis": "geospatial mapping data",
    "spatial-computing": "spatial ar vr immersive",
    "game-development": "game development design mechanics",
}


def assemble_team(obj: Objective, search: CapabilitySearch,
                  max_size: int = 6) -> list[TeamMember]:
    team: list[TeamMember] = []

    # 1) orchestrator
    for oid in ORCHESTRATOR_PREFERENCE:
        rec = search.get(oid)
        if rec:
            team.append(TeamMember(
                agent_id=rec.agent_id, name=rec.name, department=rec.department,
                role="orchestrator", matched_terms=["orchestration"],
                score=10.0,
            ))
            break

    # 2) one agent per relevant department (best capability match)
    depts = obj.departments or ["engineering"]
    base_query = " ".join(obj.keywords[:10])
    used = {m.agent_id for m in team}
    for dept in depts:
        query = f"{base_query} {DEPT_SEED.get(dept, '')}"
        hits = search.search(query, top=3, department=dept, min_score=0.5)
        if not hits:
            hits = search.search(" ".join(obj.keywords[:6]), top=3, department=dept)
        for hit in hits:
            if hit["agent_id"] in used:
                continue
            used.add(hit["agent_id"])
            team.append(TeamMember(
                agent_id=hit["agent_id"], name=hit["name"], department=hit["department"],
                role="executor", matched_terms=hit["matched_terms"], score=hit["score"],
            ))
            break
        if len(team) >= max_size:
            break

    # 3) quality gate: reality/quality agent if not already present
    gate_ids = ["testing.reality-checker", "testing.test-results-analyzer",
                "testing.workflow-optimizer"]
    for gid in gate_ids:
        rec = search.get(gid)
        if rec and rec.agent_id not in used:
            used.add(rec.agent_id)
            team.append(TeamMember(
                agent_id=rec.agent_id, name=rec.name, department=rec.department,
                role="quality-gate", matched_terms=["quality"], score=9.0,
            ))
            break

    return team[:max_size]


def build_workflow(obj: Objective, team: list[TeamMember]) -> Workflow:
    """Produce an ordered workflow from objective stages + team roles."""
    steps: list[WorkflowStep] = []
    phase_order = obj.stages or ["build"]

    role_task = {
        "orchestrator": ("Define mission, sequence agents, set success criteria",
                         "Mission brief + orchestration plan"),
        "executor": ("Execute the work for this phase with the agent's process",
                     "Phase deliverable per agent's workflow"),
        "quality-gate": ("Independently review outputs against evidence and economics",
                         "GO / REVISE / NO-GO evaluation"),
    }

    step = 0
    for phase in phase_order:
        for member in team:
            task, deliverable = role_task.get(member.role, role_task["executor"])
            if member.role == "executor" and phase not in (
                    member.__dict__.get("phases") or ["build"]):
                pass
            step += 1
            steps.append(WorkflowStep(
                phase=phase, step=step, agent_id=member.agent_id,
                role=member.role, task=task, deliverable=deliverable,
            ))
    if not steps:
        steps.append(WorkflowStep(
            phase="build", step=1, agent_id="", role="orchestrator",
            task="Execute mission", deliverable="Mission output",
        ))
    return Workflow(mission=obj.raw, steps=steps)


def mission_to_plan(raw: str, search: CapabilitySearch,
                    max_size: int = 6) -> dict:
    """Full pipeline: objective -> team -> workflow."""
    obj = parse_objective(raw)
    team = assemble_team(obj, search, max_size=max_size)
    wf = build_workflow(obj, team)
    return {
        "objective": obj.to_dict(),
        "team": [m.to_dict() for m in team],
        "workflow": wf.to_dict(),
    }
