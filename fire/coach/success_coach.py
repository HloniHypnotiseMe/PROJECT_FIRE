"""FIRE Business Success Coach.

Transforms business context and operating metrics into a prioritized,
measurable growth plan.

The coach recommends and orchestrates.
Owner authorization governs execution.
"""

from fire.growth.diagnostic import BusinessMetrics, GrowthDiagnostic
from fire.growth.models import (
    BusinessProfile,
    GrowthLever,
    GrowthOpportunity,
    SuccessPlan,
)


class BusinessSuccessCoach:
    """Identify and prioritize where FIRE can create economic value."""

    def audit(
        self,
        business: BusinessProfile,
        metrics: BusinessMetrics | None = None,
    ) -> SuccessPlan:

        opportunities = [
            GrowthOpportunity(
                lever=GrowthLever.ACQUISITION,
                title="Customer acquisition audit",
                problem=(
                    "Determine whether the business has a reliable "
                    "customer acquisition and conversion engine."
                ),
                proposed_action=(
                    "Audit current channels, conversion paths, follow-up, "
                    "GTM opportunities and customer acquisition economics."
                ),
                expected_impact="More qualified customers and higher conversion.",
            ),
            GrowthOpportunity(
                lever=GrowthLever.CUSTOMER_SPEND,
                title="Customer spend expansion",
                problem=(
                    "Existing customers may have unmet purchasing potential."
                ),
                proposed_action=(
                    "Identify upsell, cross-sell, bundling, premium offer "
                    "and reactivation opportunities."
                ),
                expected_impact="Higher average revenue per customer.",
            ),
            GrowthOpportunity(
                lever=GrowthLever.LIFETIME_VALUE,
                title="Customer lifetime value audit",
                problem=(
                    "Revenue may be lost through weak retention and follow-up."
                ),
                proposed_action=(
                    "Identify retention, reactivation, loyalty and "
                    "repeat-purchase opportunities."
                ),
                expected_impact="Longer customer relationships and higher LTV.",
            ),
            GrowthOpportunity(
                lever=GrowthLever.SUPPLY,
                title="Supplier and procurement audit",
                problem=(
                    "Input costs and supplier terms may be reducing margins."
                ),
                proposed_action=(
                    "Discover suppliers, compare pricing and terms, "
                    "identify negotiation opportunities and optimize ordering."
                ),
                expected_impact="Lower input costs and improved margins.",
            ),
        ]

        if metrics is None:
            priority = GrowthLever.ACQUISITION
        else:
            diagnostic = GrowthDiagnostic().diagnose(business, metrics)
            priority = diagnostic.primary_lever

        return SuccessPlan(
            business_name=business.business_name,
            opportunities=opportunities,
            priority_lever=priority,
            status="AUDITED",
        )
