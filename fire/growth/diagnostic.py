"""FIRE business constraint diagnostic.

Identifies the economic bottleneck most likely to constrain growth.
This is advisory; execution remains governed by owner authorization.
"""

from dataclasses import dataclass

from fire.growth.models import BusinessProfile, GrowthLever


@dataclass
class BusinessMetrics:
    monthly_leads: float = 0
    conversion_rate: float = 0
    average_customer_spend: float = 0
    repeat_purchase_rate: float = 0
    customer_retention_rate: float = 0
    input_cost_ratio: float = 0


@dataclass
class DiagnosticResult:
    primary_lever: GrowthLever
    scores: dict[GrowthLever, float]
    rationale: str


class GrowthDiagnostic:
    """Score the four economic growth levers."""

    def diagnose(
        self,
        business: BusinessProfile,
        metrics: BusinessMetrics,
    ) -> DiagnosticResult:

        scores = {
            GrowthLever.ACQUISITION: 0.0,
            GrowthLever.CUSTOMER_SPEND: 0.0,
            GrowthLever.LIFETIME_VALUE: 0.0,
            GrowthLever.SUPPLY: 0.0,
        }

        # Weak acquisition/conversion signal.
        if metrics.monthly_leads <= 0:
            scores[GrowthLever.ACQUISITION] += 1.0

        if metrics.conversion_rate < 0.10:
            scores[GrowthLever.ACQUISITION] += 1.0

        # Weak customer monetisation signal.
        if metrics.average_customer_spend <= 0:
            scores[GrowthLever.CUSTOMER_SPEND] += 0.5

        # Weak repeat/retention signal.
        if metrics.repeat_purchase_rate < 0.20:
            scores[GrowthLever.LIFETIME_VALUE] += 1.0

        if metrics.customer_retention_rate < 0.50:
            scores[GrowthLever.LIFETIME_VALUE] += 1.0

        # High input-cost signal.
        if metrics.input_cost_ratio > 0.50:
            scores[GrowthLever.SUPPLY] += 1.0

        primary = max(scores, key=scores.get)

        rationales = {
            GrowthLever.ACQUISITION:
                "Customer acquisition or conversion appears to be the primary constraint.",
            GrowthLever.CUSTOMER_SPEND:
                "Existing customers may represent unrealised revenue through higher-value offers.",
            GrowthLever.LIFETIME_VALUE:
                "Retention and repeat purchasing appear to be the primary growth opportunity.",
            GrowthLever.SUPPLY:
                "Input costs and procurement economics appear to be constraining margin.",
        }

        return DiagnosticResult(
            primary_lever=primary,
            scores=scores,
            rationale=rationales[primary],
        )
