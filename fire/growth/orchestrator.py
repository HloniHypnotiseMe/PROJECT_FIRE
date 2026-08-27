"""FIRE Growth Mission Orchestrator.

Pipeline (Phase 5):

    BusinessProfile + BusinessMetrics [+ ConsentProfile]
      -> GrowthDiagnostic            (existing, fire.growth.diagnostic)
      -> highest-value economic lever
      -> GrowthMission               (new, fire.growth.missions)
      -> agent team via existing registry search
      -> ordered workflow with consent gates
      -> measurable success / kill / scale criteria

ACQUISITION is the default first mission: when the diagnostic cannot
distinguish constraints (all-zero scores), GrowthDiagnostic resolves the
tie to ACQUISITION, matching the principle that a business without
customers cannot meaningfully optimize the rest.

FIRE autonomously RECOMMENDS and PREPAREs. External execution (customer
contact, supplier contact, purchasing) is gated by ConsentProfile checks
evaluated through ConsentManager. Agent resolution uses the existing
registry search only; no agent name is invented here.
"""

from dataclasses import asdict, dataclass

from fire.coach.success_coach import BusinessSuccessCoach
from fire.growth.diagnostic import BusinessMetrics, GrowthDiagnostic
from fire.growth.missions import (
    PERM_CUSTOMER_CONTACT,
    PERM_OWNER,
    PERM_PURCHASING,
    PERM_SUPPLIER_CONTACT,
    ApprovalGate,
    GrowthMission,
    MissionStep,
    StepKind,
)
from fire.growth.models import BusinessProfile, GrowthLever
from fire.models import TeamMember
from fire.onboarding.consent import ConsentProfile
from fire.registry import CapabilitySearch, load_registry

# ---------------------------------------------------------------------------
# lever templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _StepSpec:
    name: str
    kind: StepKind
    role: str | None = None
    permission: str | None = None


@dataclass(frozen=True)
class _LeverTemplate:
    objective: str
    slots: list[tuple[str, str, str | None]]   # (role, search query, department|None)
    steps: list[_StepSpec]
    permissions: list[str]
    gates: list[ApprovalGate]

    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]


GTM_TEMPLATE = _LeverTemplate(
    objective="Build a repeatable customer acquisition engine.",
    slots=[
        ("gtm_strategy", "go-to-market strategy customer acquisition positioning", "marketing"),
        ("acquisition", "customer acquisition lead generation prospects", "marketing"),
        ("sales", "sales outbound proposal close discovery", "sales"),
        ("marketing", "content campaign social media growth", "marketing"),
        ("conversion", "conversion landing page offer copy", None),
        ("follow_up_crm", "follow-up customer relationship pipeline retention", None),
        ("research", "market research customer discovery insight", None),
    ],
    steps=[
        _StepSpec("Audit current acquisition channels", StepKind.PREPARE, "research"),
        _StepSpec("Identify target customer", StepKind.RECOMMEND, "research"),
        _StepSpec("Analyse offer and positioning", StepKind.RECOMMEND, "gtm_strategy"),
        _StepSpec("Identify acquisition opportunities", StepKind.RECOMMEND, "acquisition"),
        _StepSpec("Build GTM experiment", StepKind.PREPARE, "gtm_strategy", PERM_CUSTOMER_CONTACT),
        _StepSpec("Build response/conversion mechanism", StepKind.PREPARE, "conversion"),
        _StepSpec("Build follow-up", StepKind.PREPARE, "follow_up_crm"),
        _StepSpec("Measure", StepKind.MEASURE),
        _StepSpec("Optimise", StepKind.RECOMMEND, "marketing"),
        _StepSpec("Scale or kill based on evidence", StepKind.DECIDE),
    ],
    permissions=[PERM_OWNER, PERM_CUSTOMER_CONTACT],
    gates=[
        ApprovalGate(
            PERM_CUSTOMER_CONTACT, [5],
            "Live execution of the GTM experiment involves contacting "
            "customers; requires owner authorization AND customer contact "
            "authorization.",
        ),
    ],
)

SUPPLY_TEMPLATE = _LeverTemplate(
    objective="Reduce procurement cost and improve supplier economics.",
    slots=[
        ("supplier_research", "supplier discovery market research sourcing", None),
        ("procurement", "procurement supply chain purchasing inventory", None),
        ("pricing_economics", "pricing economics cost finance analysis", "finance"),
        ("negotiation", "negotiation deal terms contract sales", "sales"),
    ],
    steps=[
        _StepSpec("Identify purchasing requirements", StepKind.PREPARE, "procurement"),
        _StepSpec("Discover suppliers", StepKind.PREPARE, "supplier_research"),
        _StepSpec("Compare price/MOQ/delivery/payment terms", StepKind.PREPARE, "pricing_economics"),
        _StepSpec("Identify negotiation opportunities", StepKind.RECOMMEND, "negotiation"),
        _StepSpec("Prepare negotiation", StepKind.PREPARE, "negotiation"),
        _StepSpec("Require supplier-contact authorization", StepKind.CONSENT_GATE, None, PERM_SUPPLIER_CONTACT),
        _StepSpec("Negotiate/contact supplier", StepKind.EXECUTE_EXTERNAL, "negotiation", PERM_SUPPLIER_CONTACT),
        _StepSpec("Compare resulting terms", StepKind.PREPARE, "pricing_economics"),
        _StepSpec("Prepare purchase recommendation", StepKind.RECOMMEND, "pricing_economics"),
        _StepSpec("Require purchasing authorization", StepKind.CONSENT_GATE, None, PERM_PURCHASING),
        _StepSpec("Execute purchase", StepKind.EXECUTE_EXTERNAL, "procurement", PERM_PURCHASING),
        _StepSpec("Measure savings/margin improvement", StepKind.MEASURE),
    ],
    permissions=[PERM_OWNER, PERM_SUPPLIER_CONTACT, PERM_PURCHASING],
    gates=[
        ApprovalGate(
            PERM_SUPPLIER_CONTACT, [6, 7],
            "Contacting or negotiating with suppliers requires owner "
            "authorization AND supplier contact authorization.",
        ),
        ApprovalGate(
            PERM_PURCHASING, [10, 11],
            "Executing a purchase requires owner authorization AND "
            "purchasing authorization.",
        ),
    ],
)

CUSTOMER_SPEND_TEMPLATE = _LeverTemplate(
    objective="Increase customer spend through expanded offers.",
    slots=[
        ("spend_offers", "upsell cross-sell offer pricing bundle", None),
        ("conversion", "conversion landing page offer copy", None),
        ("marketing", "content campaign social media growth", "marketing"),
        ("sales", "sales outbound proposal close discovery", "sales"),
        ("follow_up_crm", "follow-up customer relationship pipeline retention", None),
        ("research", "market research customer discovery insight", None),
    ],
    steps=[
        _StepSpec("Audit current customer spend and offer mix", StepKind.PREPARE, "research"),
        _StepSpec("Segment customers by spend", StepKind.PREPARE, "research"),
        _StepSpec("Identify upsell, cross-sell and bundle opportunities", StepKind.RECOMMEND, "spend_offers"),
        _StepSpec("Design expanded offers", StepKind.PREPARE, "spend_offers"),
        _StepSpec("Build offer rollout campaign", StepKind.PREPARE, "marketing", PERM_CUSTOMER_CONTACT),
        _StepSpec("Build offer communication and response mechanism", StepKind.PREPARE, "conversion"),
        _StepSpec("Build follow-up for accepted offers", StepKind.PREPARE, "follow_up_crm"),
        _StepSpec("Measure offer uptake and spend change", StepKind.MEASURE),
        _StepSpec("Optimise offer mix", StepKind.RECOMMEND, "marketing"),
        _StepSpec("Scale or kill based on evidence", StepKind.DECIDE),
    ],
    permissions=[PERM_OWNER, PERM_CUSTOMER_CONTACT],
    gates=[
        ApprovalGate(
            PERM_CUSTOMER_CONTACT, [5],
            "Rolling out offers contacts existing customers; requires owner "
            "authorization AND customer contact authorization.",
        ),
    ],
)

LIFETIME_VALUE_TEMPLATE = _LeverTemplate(
    objective="Increase customer lifetime value through retention and repeat purchase.",
    slots=[
        ("retention", "retention reactivation loyalty customer success", None),
        ("follow_up_crm", "follow-up customer relationship pipeline retention", None),
        ("marketing", "content campaign social media growth", "marketing"),
        ("research", "market research customer discovery insight", None),
    ],
    steps=[
        _StepSpec("Audit retention and repeat-purchase baseline", StepKind.PREPARE, "research"),
        _StepSpec("Identify at-risk and lapsed customers", StepKind.PREPARE, "retention"),
        _StepSpec("Analyse reasons for churn and non-repeat", StepKind.RECOMMEND, "research"),
        _StepSpec("Design retention and reactivation program", StepKind.PREPARE, "retention"),
        _StepSpec("Build retention campaign", StepKind.PREPARE, "marketing", PERM_CUSTOMER_CONTACT),
        _StepSpec("Build follow-up and reactivation flow", StepKind.PREPARE, "follow_up_crm"),
        _StepSpec("Build loyalty and repeat incentive", StepKind.PREPARE, "marketing"),
        _StepSpec("Measure repeat purchase and retention change", StepKind.MEASURE),
        _StepSpec("Optimise program", StepKind.RECOMMEND, "marketing"),
        _StepSpec("Scale or kill based on evidence", StepKind.DECIDE),
    ],
    permissions=[PERM_OWNER, PERM_CUSTOMER_CONTACT],
    gates=[
        ApprovalGate(
            PERM_CUSTOMER_CONTACT, [5],
            "Retention campaigns contact customers; requires owner "
            "authorization AND customer contact authorization.",
        ),
    ],
)

_LEVER_TEMPLATES: dict[GrowthLever, _LeverTemplate] = {
    GrowthLever.ACQUISITION: GTM_TEMPLATE,
    GrowthLever.CUSTOMER_SPEND: CUSTOMER_SPEND_TEMPLATE,
    GrowthLever.LIFETIME_VALUE: LIFETIME_VALUE_TEMPLATE,
    GrowthLever.SUPPLY: SUPPLY_TEMPLATE,
}

# Fixed preferences follow the existing kernel convention
# (fire/kernel.py ORCHESTRATOR_PREFERENCE / gate ids). Both are real
# registry ids; resolution still goes through the registry.
ORCHESTRATOR_AGENT_ID = "specialized.agents-orchestrator"
QUALITY_GATE_AGENT_ID = "testing.reality-checker"


# ---------------------------------------------------------------------------
# measurable targets + criteria (deterministic, no invented numbers)
# ---------------------------------------------------------------------------

def _targets_for(lever: GrowthLever, m: BusinessMetrics) -> dict:
    """Deterministic 30-60 day targets: ~25% improvement on the lever's key
    metrics, with documented floors where a zero baseline needs one."""
    if lever is GrowthLever.ACQUISITION:
        return {
            "monthly_leads": max(10.0, m.monthly_leads * 1.25),
            "conversion_rate": max(0.10, m.conversion_rate * 1.25),
        }
    if lever is GrowthLever.CUSTOMER_SPEND:
        base = m.average_customer_spend
        return {"average_customer_spend": base * 1.15 if base > 0 else 100.0}
    if lever is GrowthLever.LIFETIME_VALUE:
        return {
            "repeat_purchase_rate": max(0.20, m.repeat_purchase_rate * 1.25),
            "customer_retention_rate": max(0.50, m.customer_retention_rate * 1.10),
        }
    # SUPPLY: 10% reduction in input cost ratio (lower is better)
    base = m.input_cost_ratio
    return {"input_cost_ratio": base * 0.90 if base > 0 else 0.35}


def _criteria_for(lever: GrowthLever, t: dict) -> tuple[list[str], list[str], list[str]]:
    if lever is GrowthLever.ACQUISITION:
        return (
            [
                f"Monthly tracked leads >= {t['monthly_leads']:.0f} within 30 days of live experiments",
                f"Conversion rate >= {t['conversion_rate']:.2f} on at least 20 tracked opportunities",
            ],
            [
                "No qualified leads generated after 2 completed experiment cycles (30 days)",
                "Cost per acquired customer > 2x average customer spend for 2 consecutive cycles",
            ],
            [
                "2+ distinct channels each generating >= 25% of tracked leads",
                "Conversion at or above target for 2 consecutive cycles",
            ],
        )
    if lever is GrowthLever.SUPPLY:
        return (
            [
                f"Input cost ratio <= {t['input_cost_ratio']:.2f} within 60 days",
                "At least one renegotiated supplier agreement with documented savings",
            ],
            [
                "No supplier improves terms after 3 documented comparisons",
                "Savings below 2% of monthly input cost after 60 days",
            ],
            [
                "Input cost ratio at or below target for 2 consecutive months",
                "Savings >= 5% of monthly input cost sustained for 2 months",
            ],
        )
    if lever is GrowthLever.CUSTOMER_SPEND:
        return (
            [
                f"Average customer spend >= {t['average_customer_spend']:.0f} within 30 days",
                ">= 10% of active customers take an expanded offer",
            ],
            [
                "Offer uptake < 5% after 2 campaigns (30 days)",
                "Spend uplift below 5% of baseline after 30 days",
            ],
            [
                "Spend uplift >= 15% sustained for 2 consecutive months",
                "2+ expanded offers in regular rotation",
            ],
        )
    # LIFETIME_VALUE
    return (
        [
            f"Repeat purchase rate >= {t['repeat_purchase_rate']:.2f} within 60 days",
            f"Retention rate >= {t['customer_retention_rate']:.2f} on a 60-day cohort",
        ],
        [
            "Repeat purchase rate improvement < 5 points after 2 retention cycles (60 days)",
        ],
        [
            "Retention at or above target for 2 consecutive cohorts",
            "Reactivation converts >= 10% of lapsed contacts",
        ],
    )


def _evidence_for(result, m: BusinessMetrics) -> list[str]:
    """Measured facts only: the diagnostic verdict plus the metric values."""
    scores = result.scores
    ev = [
        f"diagnostic scores: "
        + ", ".join(f"{l.value}={s:.1f}" for l, s in scores.items()),
        f"primary lever: {result.primary_lever.value} — {result.rationale}",
        "metrics: "
        + ", ".join(f"{k}={v}" for k, v in asdict(m).items()),
    ]
    if m.monthly_leads <= 0:
        ev.append("monthly_leads <= 0: no measurable lead flow")
    if m.conversion_rate < 0.10:
        ev.append("conversion_rate below 0.10 threshold")
    if m.repeat_purchase_rate < 0.20:
        ev.append("repeat_purchase_rate below 0.20 threshold")
    if m.customer_retention_rate < 0.50:
        ev.append("customer_retention_rate below 0.50 threshold")
    if m.input_cost_ratio > 0.50:
        ev.append("input_cost_ratio above 0.50 threshold")
    return ev


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

class GrowthOrchestrator:
    """Turn profile + metrics into a consent-gated growth mission."""

    def __init__(self, search: CapabilitySearch | None = None):
        self.search = search or CapabilitySearch(load_registry())

    # -- public --------------------------------------------------------------
    def create_mission(
        self,
        business: BusinessProfile,
        metrics: BusinessMetrics | None = None,
        consent: ConsentProfile | None = None,
        max_team_size: int = 9,
    ) -> GrowthMission:
        m = metrics or BusinessMetrics()

        # 1-2. diagnose (existing engine) and select the highest-value lever.
        result = GrowthDiagnostic().diagnose(business, m)
        lever = result.primary_lever
        template = _LEVER_TEMPLATES[lever]

        # 3. coach (existing engine) supplies the problem framing for the lever.
        plan = BusinessSuccessCoach().audit(business, m)
        opp = next((o for o in plan.opportunities if o.lever == lever), None)
        problem = opp.problem if opp else result.rationale

        # 4-5. agent team from the registry, then ordered workflow.
        team = self._resolve_team(lever, max_team_size)
        workflow = self._build_workflow(template, team)

        # 6-8. measurable targets + criteria from the diagnostic evidence.
        target = _targets_for(lever, m)
        success, kill, scale = _criteria_for(lever, target)

        mission = GrowthMission(
            business_name=business.business_name,
            lever=lever,
            objective=template.objective,
            problem=problem,
            evidence=_evidence_for(result, m),
            baseline=asdict(m),
            target=target,
            agent_team=team,
            workflow=workflow,
            required_permissions=list(template.permissions),
            approval_gates=[
                ApprovalGate(g.permission, list(g.step_numbers), g.description)
                for g in template.gates
            ],
            success_criteria=success,
            kill_criteria=kill,
            scale_criteria=scale,
        )

        # 9. consent gates apply only when a ConsentProfile is supplied;
        #    preparation/recommendation never requires them.
        if consent is not None:
            mission.apply_consent(consent)
        return mission

    # -- agent resolution (registry only) ------------------------------------
    def _resolve_team(self, lever: GrowthLever, max_team_size: int) -> list[TeamMember]:
        team: list[TeamMember] = []
        used: set[str] = set()

        orch = self.search.get(ORCHESTRATOR_AGENT_ID)
        if orch:
            team.append(TeamMember(
                agent_id=orch.agent_id, name=orch.name, department=orch.department,
                role="orchestrator", matched_terms=["orchestration"], score=10.0,
            ))
            used.add(orch.agent_id)

        for role, query, department in _LEVER_TEMPLATES[lever].slots:
            if len(team) >= max_team_size:
                break
            for hit in self.search.search(query, top=3, department=department, min_score=0.5):
                if hit["agent_id"] in used:
                    continue
                used.add(hit["agent_id"])
                team.append(TeamMember(
                    agent_id=hit["agent_id"], name=hit["name"],
                    department=hit["department"], role=role,
                    matched_terms=hit["matched_terms"], score=hit["score"],
                ))
                break

        gate_rec = self.search.get(QUALITY_GATE_AGENT_ID)
        if gate_rec and gate_rec.agent_id not in used:
            team.append(TeamMember(
                agent_id=gate_rec.agent_id, name=gate_rec.name,
                department=gate_rec.department, role="quality_gate",
                matched_terms=["quality"], score=9.0,
            ))
        return team

    # -- workflow assembly -----------------------------------------------------
    def _build_workflow(self, template: _LeverTemplate, team: list[TeamMember]) -> list[MissionStep]:
        by_role = {
            m.role: m for m in team if m.role not in ("orchestrator", "quality_gate")
        }
        quality = next((m for m in team if m.role == "quality_gate"), None)

        steps: list[MissionStep] = []
        for i, spec in enumerate(template.steps, start=1):
            agent_id = None
            if spec.kind in (StepKind.MEASURE, StepKind.DECIDE) and quality:
                agent_id = quality.agent_id
            elif spec.role is not None:
                member = by_role.get(spec.role)
                agent_id = member.agent_id if member else None
            steps.append(MissionStep(
                step=i, name=spec.name, kind=spec.kind,
                agent_id=agent_id, requires_permission=spec.permission,
            ))
        return steps
