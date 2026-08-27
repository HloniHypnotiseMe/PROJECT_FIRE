"""FIRE growth mission models.

A GrowthMission is a measurable, permission-controlled execution plan for
one economic lever of one business.

FIRE autonomously RECOMMENDS and PREPAREs. Any workflow step that touches
an external party (customer, supplier) or spends money is an
EXECUTE_EXTERNAL step behind a CONSENT_GATE. Consent is evaluated only
through fire.onboarding.consent.ConsentManager, which encodes the
owner-authorization AND rules. Gates are never bypassed: without a granted
gate, external execution stays blocked.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum

from fire.models import TeamMember
from fire.onboarding.consent import ConsentManager, ConsentProfile


# ---------------------------------------------------------------------------
# status + step kinds
# ---------------------------------------------------------------------------

class MissionStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    BLOCKED = "BLOCKED"
    IN_PROGRESS = "IN_PROGRESS"
    SCALED = "SCALED"
    KILLED = "KILLED"


class StepKind(str, Enum):
    PREPARE = "prepare"                # autonomous: no external contact
    RECOMMEND = "recommend"            # FIRE drafts; owner decides
    EXECUTE_EXTERNAL = "execute_external"  # live action; requires consent
    CONSENT_GATE = "consent_gate"      # explicit authorization checkpoint
    MEASURE = "measure"
    DECIDE = "decide"


# Permission names mirror ConsentProfile fields.
PERM_OWNER = "owner_authorized"
PERM_CUSTOMER_CONTACT = "customer_contact_authorized"
PERM_SUPPLIER_CONTACT = "supplier_contact_authorized"
PERM_PURCHASING = "purchasing_authorized"

# Each gate permission maps to the ConsentManager rule that grants it.
# can_contact_customers / can_contact_suppliers / can_purchase already
# require owner_authorized in addition to their specific flag.
_CONSENT_CHECKS = {
    PERM_CUSTOMER_CONTACT: ConsentManager.can_contact_customers,
    PERM_SUPPLIER_CONTACT: ConsentManager.can_contact_suppliers,
    PERM_PURCHASING: ConsentManager.can_purchase,
}


# ---------------------------------------------------------------------------
# workflow + gates
# ---------------------------------------------------------------------------

@dataclass
class MissionStep:
    """One ordered step of a growth mission workflow."""

    step: int
    name: str
    kind: StepKind = StepKind.PREPARE
    agent_id: str | None = None          # registry agent assigned, if any
    requires_permission: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApprovalGate:
    """A consent checkpoint gating external-execution steps."""

    permission: str
    step_numbers: list[int] = field(default_factory=list)
    description: str = ""
    granted: bool | None = None          # None = not yet evaluated

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# the mission
# ---------------------------------------------------------------------------

@dataclass
class GrowthMission:
    """A consent-gated, measurable plan for one economic lever."""

    business_name: str
    lever: object                          # fire.growth.models.GrowthLever
    objective: str
    problem: str
    evidence: list[str] = field(default_factory=list)
    baseline: dict = field(default_factory=dict)      # metric snapshot
    target: dict = field(default_factory=dict)        # measurable targets
    agent_team: list[TeamMember] = field(default_factory=list)
    workflow: list[MissionStep] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    approval_gates: list[ApprovalGate] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    kill_criteria: list[str] = field(default_factory=list)
    scale_criteria: list[str] = field(default_factory=list)
    status: MissionStatus = MissionStatus.DRAFT

    # -- consent ------------------------------------------------------------
    def gate_for(self, permission: str) -> ApprovalGate | None:
        return next((g for g in self.approval_gates if g.permission == permission), None)

    def apply_consent(self, consent: ConsentProfile) -> list[ApprovalGate]:
        """Evaluate every gate through ConsentManager. Never bypasses."""
        for gate in self.approval_gates:
            check = _CONSENT_CHECKS.get(gate.permission)
            gate.granted = check(consent) if check is not None else False
        if self.approval_gates:
            blocked = any(g.granted is False for g in self.approval_gates)
            self.status = MissionStatus.BLOCKED if blocked else MissionStatus.READY
        return self.approval_gates

    @property
    def external_execution_allowed(self) -> bool:
        """True only when every gate exists and is granted.

        A mission with unevaluated (None) gates is NOT allowed to execute
        externally: FIRE may prepare and recommend, nothing more.
        """
        return bool(self.approval_gates) and all(
            g.granted is True for g in self.approval_gates
        )

    # -- serialization -------------------------------------------------------
    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["lever"] = getattr(self.lever, "value", self.lever)
        return data
