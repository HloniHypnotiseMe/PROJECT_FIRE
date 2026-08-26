"""FIRE live business demonstration engine."""

from dataclasses import dataclass

from fire.coach.success_coach import BusinessSuccessCoach
from fire.growth.diagnostic import BusinessMetrics
from fire.growth.models import BusinessProfile, GrowthOpportunity, SuccessPlan


@dataclass
class DemoResult:
    business_name: str
    plan: SuccessPlan
    primary_opportunity: GrowthOpportunity | None
    demonstration: str


class FireDemo:
    """Turn a business profile into a concrete FIRE demonstration."""

    def run(
        self,
        business: BusinessProfile,
        metrics: BusinessMetrics | None = None,
    ) -> DemoResult:
        coach = BusinessSuccessCoach()

        if metrics is not None:
            plan = coach.audit(business, metrics)
        else:
            plan = coach.audit(business)

        primary = plan.opportunities[0] if plan.opportunities else None

        demonstration = self._build_demonstration(business, primary)

        return DemoResult(
            business_name=business.business_name,
            plan=plan,
            primary_opportunity=primary,
            demonstration=demonstration,
        )

    @staticmethod
    def _build_demonstration(
        business: BusinessProfile,
        opportunity: GrowthOpportunity | None,
    ) -> str:
        if opportunity is None:
            return (
                f"FIRE completed an initial audit of {business.business_name}, "
                "but did not identify a demonstration opportunity."
            )

        return (
            f"FIRE identified {opportunity.title} as the current priority for "
            f"{business.business_name}. "
            f"Problem: {opportunity.problem} "
            f"FIRE can demonstrate: {opportunity.proposed_action} "
            f"Expected business impact: {opportunity.expected_impact}"
        )
