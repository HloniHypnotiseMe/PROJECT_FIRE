import unittest

from fire.activation.demo import FireDemo
from fire.growth.models import BusinessProfile


class TestFireDemo(unittest.TestCase):

    def test_demo_produces_business_opportunity(self):
        business = BusinessProfile(
            business_name="Demo Business",
            sector="Retail",
            location="Gauteng",
            uses_whatsapp=True,
        )

        result = FireDemo().run(business)

        self.assertEqual(result.business_name, "Demo Business")
        self.assertIsNotNone(result.primary_opportunity)
        self.assertIn("FIRE identified", result.demonstration)


if __name__ == "__main__":
    unittest.main()
