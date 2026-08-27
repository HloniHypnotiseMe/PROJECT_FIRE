"""Tests for the GrowthOrchestrator (fire/growth/orchestrator.py).

Agent resolution runs against the real registry, built once per test class.
"""

import unittest

from fire.growth.diagnostic import BusinessMetrics, GrowthDiagnostic
from fire.growth.models import BusinessProfile, GrowthLever
from fire.growth.orchestrator import GrowthOrchestrator
from fire.onboarding.consent import ConsentProfile
from fire.registry import CapabilitySearch, load_registry


def healthy_metrics() -> BusinessMetrics:
    return BusinessMetrics(
        monthly_leads=100,
        conversion_rate=0.30,
        average_customer_spend=500,
        repeat_purchase_rate=0.50,
        customer_retention_rate=0.80,
        input_cost_ratio=0.30,
    )


class TestGrowthOrchestrator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.search = CapabilitySearch(load_registry())
        cls.orchestrator = GrowthOrchestrator(search=cls.search)
        cls.business = BusinessProfile(
            business_name="Demo Business",
            sector="Retail",
            location="Gauteng",
        )

    def weak_acquisition_metrics(self) -> BusinessMetrics:
        return BusinessMetrics(
            monthly_leads=0,
            conversion_rate=0.05,
            average_customer_spend=1000,
            repeat_purchase_rate=0.50,
            customer_retention_rate=0.70,
            input_cost_ratio=0.30,
        )

    def weak_supply_metrics(self) -> BusinessMetrics:
        m = healthy_metrics()
        m.input_cost_ratio = 0.80
        return m

    def weak_ltv_metrics(self) -> BusinessMetrics:
        m = healthy_metrics()
        m.repeat_purchase_rate = 0.05
        m.customer_retention_rate = 0.30
        return m

    # -- 1. creation ----------------------------------------------------------
    def test_mission_creation_works(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_acquisition_metrics(),
        )
        self.assertEqual(mission.business_name, "Demo Business")
        self.assertTrue(mission.objective)
        self.assertTrue(mission.problem)
        self.assertTrue(mission.evidence)
        self.assertTrue(mission.workflow)
        self.assertTrue(mission.agent_team)
        self.assertEqual(mission.status.value, "DRAFT")  # no consent supplied

    # -- 2/3. lever selection ---------------------------------------------------
    def test_weak_acquisition_creates_gtm_mission(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_acquisition_metrics(),
        )
        self.assertEqual(mission.lever, GrowthLever.ACQUISITION)
        self.assertEqual(
            mission.objective,
            "Build a repeatable customer acquisition engine.",
        )
        self.assertEqual(len(mission.workflow), 10)
        self.assertEqual(mission.workflow[0].name,
                         "Audit current acquisition channels")
        self.assertEqual(mission.workflow[-1].name,
                         "Scale or kill based on evidence")

    def test_weak_supply_creates_procurement_mission(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_supply_metrics(),
        )
        self.assertEqual(mission.lever, GrowthLever.SUPPLY)
        self.assertEqual(
            mission.objective,
            "Reduce procurement cost and improve supplier economics.",
        )
        self.assertEqual(len(mission.workflow), 12)
        self.assertEqual(mission.workflow[5].name,
                         "Require supplier-contact authorization")
        self.assertEqual(mission.workflow[9].name,
                         "Require purchasing authorization")

    # -- 4. diagnostic evidence changes priority --------------------------------
    def test_diagnostic_evidence_changes_mission_priority(self):
        cases = [
            (self.weak_acquisition_metrics(), GrowthLever.ACQUISITION),
            (self.weak_ltv_metrics(), GrowthLever.LIFETIME_VALUE),
            (self.weak_supply_metrics(), GrowthLever.SUPPLY),
        ]
        levers_seen = set()
        for metrics, lever in cases:
            # sanity: the diagnostic itself agrees with the expectation
            result = GrowthDiagnostic().diagnose(self.business, metrics)
            self.assertEqual(result.primary_lever, lever)
            mission = self.orchestrator.create_mission(self.business, metrics)
            self.assertEqual(mission.lever, lever)
            levers_seen.add(lever)
        # different evidence produced different mission priorities
        self.assertEqual(len(levers_seen), 3)
        # no metrics at all -> default first mission is acquisition (GTM)
        default = self.orchestrator.create_mission(self.business, None)
        self.assertEqual(default.lever, GrowthLever.ACQUISITION)

    # -- 5. agent resolution ------------------------------------------------------
    def test_agent_team_resolves_against_registry(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_acquisition_metrics(),
        )
        self.assertGreater(len(mission.agent_team), 0)
        for member in mission.agent_team:
            record = self.search.get(member.agent_id)
            self.assertIsNotNone(
                record, f"team member not in registry: {member.agent_id}"
            )
            self.assertEqual(record.agent_id, member.agent_id)
        roles = {m.role for m in mission.agent_team}
        self.assertIn("orchestrator", roles)
        self.assertIn("quality_gate", roles)

    def test_supply_team_resolves_against_registry(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_supply_metrics(),
        )
        self.assertGreater(len(mission.agent_team), 0)
        for member in mission.agent_team:
            self.assertIsNotNone(
                self.search.get(member.agent_id),
                f"supply team member not in registry: {member.agent_id}",
            )

    # -- 6. workflow ordering -----------------------------------------------------
    def test_workflow_is_ordered(self):
        for metrics in (self.weak_acquisition_metrics(),
                        self.weak_supply_metrics()):
            mission = self.orchestrator.create_mission(self.business, metrics)
            numbers = [s.step for s in mission.workflow]
            self.assertEqual(numbers, list(range(1, len(mission.workflow) + 1)))
            self.assertTrue(all(s.name for s in mission.workflow))

    # -- 7. permissions -------------------------------------------------------------
    def test_required_permissions_declared(self):
        gtm = self.orchestrator.create_mission(
            self.business, self.weak_acquisition_metrics(),
        )
        self.assertIn("owner_authorized", gtm.required_permissions)
        self.assertIn("customer_contact_authorized", gtm.required_permissions)

        supply = self.orchestrator.create_mission(
            self.business, self.weak_supply_metrics(),
        )
        for perm in ("owner_authorized", "supplier_contact_authorized",
                     "purchasing_authorized"):
            self.assertIn(perm, supply.required_permissions)

    # -- 8/9/10. consent gates -----------------------------------------------------
    def test_customer_contact_blocked_without_consent(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_acquisition_metrics(),
        )
        # not evaluated at all
        self.assertFalse(mission.external_execution_allowed)
        # owner alone: still blocked
        mission.apply_consent(ConsentProfile(owner_authorized=True))
        self.assertFalse(mission.external_execution_allowed)
        # both flags: unblocked
        mission.apply_consent(ConsentProfile(
            owner_authorized=True, customer_contact_authorized=True,
        ))
        self.assertTrue(mission.external_execution_allowed)
        self.assertEqual(mission.status.value, "READY")

    def test_supplier_contact_blocked_without_consent(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_supply_metrics(),
        )
        mission.apply_consent(ConsentProfile(
            owner_authorized=True,
            customer_contact_authorized=True,  # irrelevant for suppliers
        ))
        gate = mission.gate_for("supplier_contact_authorized")
        self.assertIsNotNone(gate)
        self.assertFalse(gate.granted)
        self.assertFalse(mission.external_execution_allowed)
        mission.apply_consent(ConsentProfile(
            owner_authorized=True, supplier_contact_authorized=True,
        ))
        self.assertTrue(gate.granted)
        # purchasing gate still pending -> overall still blocked
        self.assertFalse(mission.external_execution_allowed)

    def test_purchasing_blocked_without_purchasing_authorization(self):
        mission = self.orchestrator.create_mission(
            self.business, self.weak_supply_metrics(),
        )
        mission.apply_consent(ConsentProfile(
            owner_authorized=True,
            supplier_contact_authorized=True,
        ))
        gate = mission.gate_for("purchasing_authorized")
        self.assertIsNotNone(gate)
        self.assertFalse(gate.granted)
        self.assertFalse(mission.external_execution_allowed)
        mission.apply_consent(ConsentProfile(
            owner_authorized=True,
            supplier_contact_authorized=True,
            purchasing_authorized=True,
        ))
        self.assertTrue(gate.granted)
        self.assertTrue(mission.external_execution_allowed)
        self.assertEqual(mission.status.value, "READY")

    # -- 11/12/13. measurable criteria ---------------------------------------------
    def test_success_criteria_exist(self):
        for metrics in (self.weak_acquisition_metrics(),
                        self.weak_supply_metrics()):
            mission = self.orchestrator.create_mission(self.business, metrics)
            self.assertGreater(len(mission.success_criteria), 0)
            self.assertTrue(all(c.strip() for c in mission.success_criteria))

    def test_kill_criteria_exist(self):
        for metrics in (self.weak_acquisition_metrics(),
                        self.weak_supply_metrics()):
            mission = self.orchestrator.create_mission(self.business, metrics)
            self.assertGreater(len(mission.kill_criteria), 0)
            self.assertTrue(all(c.strip() for c in mission.kill_criteria))

    def test_scale_criteria_exist(self):
        for metrics in (self.weak_acquisition_metrics(),
                        self.weak_supply_metrics()):
            mission = self.orchestrator.create_mission(self.business, metrics)
            self.assertGreater(len(mission.scale_criteria), 0)
            self.assertTrue(all(c.strip() for c in mission.scale_criteria))

    # -- baseline/target evidence -----------------------------------------------------
    def test_baseline_and_target_are_measured(self):
        metrics = self.weak_acquisition_metrics()
        mission = self.orchestrator.create_mission(self.business, metrics)
        self.assertEqual(mission.baseline["monthly_leads"], 0)
        self.assertEqual(mission.baseline["conversion_rate"], 0.05)
        self.assertGreaterEqual(mission.target["monthly_leads"], 10.0)
        self.assertGreaterEqual(mission.target["conversion_rate"], 0.10)
        # evidence must reference the diagnostic verdict
        self.assertTrue(any("primary lever" in e for e in mission.evidence))


if __name__ == "__main__":
    unittest.main()
