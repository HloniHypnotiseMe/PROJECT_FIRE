import unittest

from fire.activation.activation import ActivationSession, ActivationState
from fire.activation.onboarding import OnboardingData
from fire.onboarding.consent import ConsentProfile


class TestActivation(unittest.TestCase):

    def setUp(self):
        self.session = ActivationSession(session_id="DEMO-001")

        self.onboarding = OnboardingData(
            business_name="Demo Business",
            sector="Retail",
            location="Gauteng",
            uses_whatsapp=True,
            consent=ConsentProfile(owner_authorized=True),
        )

    def test_activation_lifecycle(self):
        self.assertEqual(
            self.session.state,
            ActivationState.VISITOR,
        )

        self.session.identify_business(self.onboarding)

        self.assertEqual(
            self.session.state,
            ActivationState.BUSINESS_IDENTIFIED,
        )

        result = self.session.start_demo()

        self.assertIsNotNone(result.primary_opportunity)
        self.assertEqual(
            self.session.state,
            ActivationState.OPPORTUNITY_REVEALED,
        )

        self.session.start_trial()
        self.assertEqual(
            self.session.state,
            ActivationState.TRIAL,
        )

        self.session.subscribe()
        self.assertEqual(
            self.session.state,
            ActivationState.SUBSCRIBED,
        )

        self.session.activate()
        self.assertEqual(
            self.session.state,
            ActivationState.ACTIVATED,
        )

    def test_cannot_skip_subscription(self):
        self.session.identify_business(self.onboarding)
        self.session.start_demo()
        self.session.start_trial()

        with self.assertRaises(ValueError):
            self.session.activate()

    def test_consent_is_preserved(self):
        self.session.identify_business(self.onboarding)

        self.assertTrue(
            self.session.consent().owner_authorized
        )


if __name__ == "__main__":
    unittest.main()
