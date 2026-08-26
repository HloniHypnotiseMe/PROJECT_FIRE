"""FIRE Business Growth domain models.

FIRE's purpose is to improve measurable business outcomes:
1. Acquire more customers.
2. Increase customer spend.
3. Increase customer lifetime value.
4. Improve supplier/procurement economics.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class GrowthLever(str, Enum):
    ACQUISITION = "acquisition"
    CUSTOMER_SPEND = "customer_spend"
    LIFETIME_VALUE = "lifetime_value"
    SUPPLY = "supply"


@dataclass
class BusinessProfile:
    """Business context collected during owner-authorized onboarding."""

    business_name: str
    sector: str
    location: str = ""
    products_services: List[str] = field(default_factory=list)

    uses_whatsapp: bool = False
    uses_crm: bool = False
    uses_online_sales: bool = False

    owner_consent: bool = False


@dataclass
class GrowthOpportunity:
    """A measurable opportunity FIRE can identify for a business."""

    lever: GrowthLever
    title: str
    problem: str
    proposed_action: str

    expected_impact: str = ""
    evidence_required: List[str] = field(default_factory=list)

    owner_approval_required: bool = True
    status: str = "IDENTIFIED"


@dataclass
class SuccessPlan:
    """FIRE's prioritized business improvement plan."""

    business_name: str
    opportunities: List[GrowthOpportunity] = field(default_factory=list)

    priority_lever: GrowthLever | None = None
    status: str = "DRAFT"
