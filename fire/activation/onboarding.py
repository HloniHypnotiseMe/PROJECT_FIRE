"""FIRE business onboarding.

Collects the minimum information required to demonstrate FIRE's value.
Execution permissions remain explicitly controlled by the owner.
"""

from dataclasses import dataclass, field

from fire.growth.models import BusinessProfile
from fire.onboarding.consent import ConsentProfile


@dataclass
class OnboardingData:
    business_name: str
    sector: str
    location: str = ""
    products_services: list[str] = field(default_factory=list)

    uses_whatsapp: bool = False
    uses_crm: bool = False
    uses_online_sales: bool = False

    consent: ConsentProfile = field(default_factory=ConsentProfile)

    def to_business_profile(self) -> BusinessProfile:
        return BusinessProfile(
            business_name=self.business_name,
            sector=self.sector,
            location=self.location,
            products_services=self.products_services,
            uses_whatsapp=self.uses_whatsapp,
            uses_crm=self.uses_crm,
            uses_online_sales=self.uses_online_sales,
            owner_consent=self.consent.owner_authorized,
        )
