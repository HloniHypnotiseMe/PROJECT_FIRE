"""Owner authorization controls for FIRE."""

from dataclasses import dataclass


@dataclass
class ConsentProfile:
    owner_authorized: bool = False
    customer_contact_authorized: bool = False
    supplier_contact_authorized: bool = False
    purchasing_authorized: bool = False


class ConsentManager:
    """Enforce owner-controlled execution boundaries."""

    @staticmethod
    def can_contact_customers(consent: ConsentProfile) -> bool:
        return consent.owner_authorized and consent.customer_contact_authorized

    @staticmethod
    def can_contact_suppliers(consent: ConsentProfile) -> bool:
        return consent.owner_authorized and consent.supplier_contact_authorized

    @staticmethod
    def can_purchase(consent: ConsentProfile) -> bool:
        return consent.owner_authorized and consent.purchasing_authorized
