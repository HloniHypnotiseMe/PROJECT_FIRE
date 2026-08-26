"""FIRE Business Success Coach.

Transforms business context into prioritized, measurable growth opportunities.
The coach recommends and orchestrates; owner authorization governs execution.
"""

from fire.growth.models import (
    BusinessProfile,
    GrowthLever,
    GrowthOpportunity,
    SuccessPlan,
)


class BusinessSuccessCoach:
    """Identify where FIRE can create economic value."""

    def audit(self, business: BusinessProfile) -> SuccessPlan:
        opportunities = []

        opportunities.append(
            GrowthOpportunity(
                lever=GrowthLever.ACQUISITION,
                title="Customer acquisition audit",
                problem="Determine whether the business has a reliable customer acquisition engine.",
                proposed_action=(
                    "Audit current channels, conversion paths, follow-up, "
                    "and opportunities for automated GTM."
                ),
                expected_impact="More qualified customers and higher conversion.",
            )
        )

        opportunities.append(
            GrowthOpportunity(
                lever=GrowthLever.CUSTOMER_SPEND,
                title="Customer spend expansion",
                problem="Existing customers may have unmet purchasing potential.",
                proposed_action=(
                    "Identify upsell, cross-sell, bundling, offer and "
                    "reactivation opportunities."
                ),
                expected_impact="Higher average revenue per customer.",
            )
        )

        opportunities.append(
            GrowthOpportunity(
                lever=GrowthLever.LIFETIME_VALUE,
                title="Customer lifetime value audit",
                problem="Revenue may be lost through weak retention and follow-up.",
                proposed_action=(
                    "Identify retention, reactivation, loyalty and "
                    "repeat-purchase opportunities."
                ),
                expected_impact="Longer customer relationships and higher LTV.",
            )
        )

        opportunities.append(
            GrowthOpportunity(
                lever=GrowthLever.SUPPLY,
                title="Supplier and procurement audit",
                problem="Input costs and supplier terms may be reducing margins.",
                proposed_action=(
                    "Discover suppliers, compare pricing and terms, "
                    "identify negotiation opportunities and optimize ordering."
                ),
                expected_impact="Lower input costs and improved margins.",
            )
        )

        return SuccessPlan(
            business_name=business.business_name,
            opportunities=opportunities,
            priority_lever=GrowthLever.ACQUISITION,
            status="AUDITED",
        )
