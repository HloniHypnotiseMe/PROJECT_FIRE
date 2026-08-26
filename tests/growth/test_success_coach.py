import unittest

from fire.coach.success_coach import BusinessSuccessCoach
from fire.growth.models import BusinessProfile, GrowthLever


class TestBusinessSuccessCoach(unittest.TestCase):

    def setUp(self):
        self.business = BusinessProfile(
            business_name="Test Business",
            sector="Professional Services",
            location="Gauteng",
            uses_whatsapp=True,
            owner_consent=True,
        )

    def test_audit_has_four_economic_levers(self):
        plan = BusinessSuccessCoach().audit(self.business)

        levers = {op.lever for op in plan.opportunities}

        self.assertEqual(
            levers,
            {
                GrowthLever.ACQUISITION,
                GrowthLever.CUSTOMER_SPEND,
                GrowthLever.LIFETIME_VALUE,
                GrowthLever.SUPPLY,
            },
        )

    def test_acquisition_is_initial_priority(self):
        plan = BusinessSuccessCoach().audit(self.business)

        self.assertEqual(
            plan.priority_lever,
            GrowthLever.ACQUISITION,
        )

    def test_business_is_audited(self):
        plan = BusinessSuccessCoach().audit(self.business)

        self.assertEqual(plan.status, "AUDITED")


if __name__ == "__main__":
    unittest.main()
