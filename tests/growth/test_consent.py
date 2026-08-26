import unittest

from fire.onboarding.consent import ConsentManager, ConsentProfile


class TestConsentManager(unittest.TestCase):

    def test_no_owner_consent_means_no_customer_contact(self):
        consent = ConsentProfile()

        self.assertFalse(
            ConsentManager.can_contact_customers(consent)
        )

    def test_owner_can_authorize_customer_contact(self):
        consent = ConsentProfile(
            owner_authorized=True,
            customer_contact_authorized=True,
        )

        self.assertTrue(
            ConsentManager.can_contact_customers(consent)
        )

    def test_supplier_contact_requires_supplier_authorization(self):
        consent = ConsentProfile(
            owner_authorized=True,
            customer_contact_authorized=True,
        )

        self.assertFalse(
            ConsentManager.can_contact_suppliers(consent)
        )

    def test_purchase_requires_explicit_purchase_authority(self):
        consent = ConsentProfile(
            owner_authorized=True,
            supplier_contact_authorized=True,
        )

        self.assertFalse(
            ConsentManager.can_purchase(consent)
        )


if __name__ == "__main__":
    unittest.main()
