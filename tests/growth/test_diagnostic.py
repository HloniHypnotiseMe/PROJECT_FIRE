import unittest

from fire.growth.diagnostic import BusinessMetrics, GrowthDiagnostic
from fire.growth.models import BusinessProfile, GrowthLever


class TestGrowthDiagnostic(unittest.TestCase):

    def setUp(self):
        self.business = BusinessProfile(
            business_name="Demo Business",
            sector="Retail",
            location="Gauteng",
        )

    def test_weak_acquisition_is_prioritised(self):
        result = GrowthDiagnostic().diagnose(
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
            result.primary_lever,
            GrowthLever.ACQUISITION,
        )

    def test_weak_ltv_is_prioritised(self):
        result = GrowthDiagnostic().diagnose(
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
            result.primary_lever,
            GrowthLever.LIFETIME_VALUE,
        )

    def test_supply_constraint_is_detected(self):
        result = GrowthDiagnostic().diagnose(
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
            result.primary_lever,
            GrowthLever.SUPPLY,
        )


if __name__ == "__main__":
    unittest.main()
