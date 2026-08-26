"""FIRE activation lifecycle.

The activation layer converts a visitor into an activated business account.
It does not execute customer, supplier, or purchasing actions without consent.
"""

from dataclasses import dataclass
from enum import Enum

from fire.activation.demo import DemoResult, FireDemo
from fire.activation.onboarding import OnboardingData
from fire.onboarding.consent import ConsentProfile


class ActivationState(str, Enum):
    VISITOR = "VISITOR"
    BUSINESS_IDENTIFIED = "BUSINESS_IDENTIFIED"
    DEMO_STARTED = "DEMO_STARTED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    OPPORTUNITY_REVEALED = "OPPORTUNITY_REVEALED"
    TRIAL = "TRIAL"
    SUBSCRIBED = "SUBSCRIBED"
    ACTIVATED = "ACTIVATED"


@dataclass
class ActivationSession:
    session_id: str
    state: ActivationState = ActivationState.VISITOR
    onboarding: OnboardingData | None = None
    demo_result: DemoResult | None = None

    def identify_business(self, onboarding: OnboardingData) -> None:
        self.onboarding = onboarding
        self.state = ActivationState.BUSINESS_IDENTIFIED

    def start_demo(self) -> DemoResult:
        if self.onboarding is None:
            raise ValueError("Business onboarding is required before starting demo.")

        self.state = ActivationState.DEMO_STARTED

        business = self.onboarding.to_business_profile()
        self.demo_result = FireDemo().run(business)

        self.state = ActivationState.AUDIT_COMPLETED

        if self.demo_result.primary_opportunity is not None:
            self.state = ActivationState.OPPORTUNITY_REVEALED

        return self.demo_result

    def start_trial(self) -> None:
        if self.demo_result is None:
            raise ValueError("Demo must be completed before trial activation.")

        self.state = ActivationState.TRIAL

    def subscribe(self) -> None:
        if self.state != ActivationState.TRIAL:
            raise ValueError("Trial must be started before subscription.")

        self.state = ActivationState.SUBSCRIBED

    def activate(self) -> None:
        if self.state != ActivationState.SUBSCRIBED:
            raise ValueError("Subscription is required before activation.")

        self.state = ActivationState.ACTIVATED

    def consent(self) -> ConsentProfile:
        if self.onboarding is None:
            return ConsentProfile()

        return self.onboarding.consent
