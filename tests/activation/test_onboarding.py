import unittest

from fire.activation.onboarding import OnboardingData
from fire.onboarding.consent import ConsentProfile


class TestOnboarding(unittest.TestCase):

    def test_onboarding_creates_business_profile(self):
        data = OnboardingData(
            business_name="Demo Business",
            sector="Retail",
            location="Gauteng",
            products_services=["Product A"],
            uses_whatsapp=True,
            consent=ConsentProfile(owner_authorized=True),
        )

        profile = data.to_business_profile()

        self.assertEqual(profile.business_name, "Demo Business")
        self.assertTrue(profile.uses_whatsapp)
        self.assertTrue(profile.owner_consent)


if __name__ == "__main__":
    unittest.main()
