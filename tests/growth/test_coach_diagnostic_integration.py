import unittest

from fire.coach.success_coach import BusinessSuccessCoach
from fire.growth.diagnostic import BusinessMetrics
from fire.growth.models import BusinessProfile, GrowthLever


class TestCoachDiagnosticIntegration(unittest.TestCase):

    def setUp(self):
        self.business = BusinessProfile(
            business_name="Integration Business",
            sector="Retail",
            location="Gauteng",
        )

    def test_coach_uses_acquisition_diagnostic(self):
        plan = BusinessSuccessCoach().audit(
            self.business,
            BusinessMetrics(
                monthly_leads=20,
                conversion_rate=0.05,
                average_customer_spend=1000,
                repeat_purchase_rate=0.50,
                customer_retention_rate=0.70,
                input_cost_ratio=0.30,
            ),
        )

        self.assertEqual(
            plan.priority_lever,
            GrowthLever.ACQUISITION,
        )

    def test_coach_uses_ltv_diagnostic(self):
        plan = BusinessSuccessCoach().audit(
            self.business,
            BusinessMetrics(
                monthly_leads=500,
                conversion_rate=0.25,
                average_customer_spend=1000,
                repeat_purchase_rate=0.05,
                customer_retention_rate=0.20,
                input_cost_ratio=0.30,
            ),
        )

        self.assertEqual(
            plan.priority_lever,
            GrowthLever.LIFETIME_VALUE,
        )

    def test_coach_uses_supply_diagnostic(self):
        plan = BusinessSuccessCoach().audit(
            self.business,
            BusinessMetrics(
                monthly_leads=500,
                conversion_rate=0.25,
                average_customer_spend=1000,
                repeat_purchase_rate=0.50,
                customer_retention_rate=0.80,
                input_cost_ratio=0.70,
            ),
        )

        self.assertEqual(
            plan.priority_lever,
            GrowthLever.SUPPLY,
        )


if __name__ == "__main__":
    unittest.main()
