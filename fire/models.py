"""Core data models for PROJECT FIRE."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    "academic", "design", "engineering", "finance", "game-development",
    "gis", "healthcare", "marketing", "paid-media", "product",
    "project-management", "sales", "security", "spatial-computing",
    "specialized", "support", "testing",
]

LIFECYCLE_STAGES = [
    "discover", "validate", "design", "build", "launch", "sell", "operate", "optimize",
]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class AgentRecord:
    """Machine-readable record derived from a Markdown agent definition."""

    agent_id: str            # e.g. "engineering.rapid-prototyper"
    name: str                # from frontmatter
    department: str          # top-level directory
    slug: str                # file stem (core name, prefix stripped)
    description: str = ""
    emoji: str = ""
    vibe: str = ""
    capabilities: list = field(default_factory=list)
    success_metrics: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    lifecycle_stages: list = field(default_factory=list)
    risk_level: str = "medium"
    version: str = "1.0.0"
    source_path: str = ""
    sections: dict = field(default_factory=dict)  # canonical section -> raw text

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegistryStats:
    total_agents: int = 0
    departments: dict = field(default_factory=dict)      # dept -> count
    stages: dict = field(default_factory=dict)           # stage -> count
    tools: dict = field(default_factory=dict)            # tool -> count
    agents_without_frontmatter: int = 0
    index_file: str = ""


# ---------------------------------------------------------------------------
# Kernel
# ---------------------------------------------------------------------------


@dataclass
class Objective:
    """Parsed mission objective from natural language input."""

    raw: str
    intent: str = "execute"                 # find / build / audit / launch / optimize / validate / sell
    departments: list = field(default_factory=list)
    stages: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    constraints: dict = field(default_factory=dict)     # price, location, audience, ...
    deliverable: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TeamMember:
    agent_id: str
    name: str
    department: str
    role: str                       # e.g. "orchestrator", "build", "verify"
    matched_terms: list = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkflowStep:
    phase: str                      # lifecycle stage
    step: int
    agent_id: str
    role: str
    task: str
    deliverable: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Workflow:
    mission: str
    steps: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Opportunity Engine
# ---------------------------------------------------------------------------


@dataclass
class Opportunity:
    """A scored business opportunity."""

    id: str
    name: str
    problem: str
    customer: str
    solution: str
    pricing: str
    distribution: str
    mvp: str
    scores: dict = field(default_factory=dict)          # criterion -> 0..10
    weighted_score: float = 0.0
    reasons: list = field(default_factory=list)         # top drivers for the score
    validation_experiment: str = ""
    required_agents: list = field(default_factory=list)  # agent_ids
    kill_criteria: list = field(default_factory=list)
    scale_criteria: list = field(default_factory=list)
    evidence: list = field(default_factory=list)         # [(source, claim)]
    economics: dict = field(default_factory=dict)        # pricing hypothesis, margin, mrr target
    origin: str = "seed-hypothesis"                      # or "discovered"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Quality / Reality Engine
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evaluation:
    verdict: str                    # GO / REVISE / NO-GO
    checks: list = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Memory / Revenue
# ---------------------------------------------------------------------------


@dataclass
class MissionRecord:
    mission_id: str
    objective: str
    intent: str
    status: str = "planned"         # planned / running / done / killed
    team: list = field(default_factory=list)
    workflow: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    evaluation: Optional[dict] = None
    economic_result: Optional[dict] = None
    lessons: list = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RevenueEngine:
    """One operating revenue stream."""

    name: str
    price: float                   # per unit
    period: str = "month"          # month / one-off / percent
    customers: int = 0
    cost_month: float = 0.0        # direct cost
    take_rate: float = 0.0         # for percent-based models (0..1)

    def to_dict(self) -> dict:
        return asdict(self)
