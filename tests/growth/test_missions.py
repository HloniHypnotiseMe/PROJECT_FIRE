"""Tests for the growth mission model (fire/growth/missions.py)."""

import unittest

from fire.growth.missions import (
    PERM_CUSTOMER_CONTACT,
    PERM_PURCHASING,
    PERM_SUPPLIER_CONTACT,
    ApprovalGate,
    GrowthMission,
    MissionStatus,
    MissionStep,
    StepKind,
)
from fire.growth.models import GrowthLever
from fire.onboarding.consent import ConsentProfile


def make_mission(**overrides) -> GrowthMission:
    """A minimal GTM-shaped mission for model-level tests."""
    base = dict(
        business_name="Demo Business",
        lever=GrowthLever.ACQUISITION,
        objective="Build a repeatable customer acquisition engine.",
        problem="Acquisition is the primary constraint.",
        baseline={"monthly_leads": 0, "conversion_rate": 0.05},
        target={"monthly_leads": 10.0, "conversion_rate": 0.10},
        workflow=[
            MissionStep(1, "Audit current acquisition channels", StepKind.PREPARE),
            MissionStep(2, "Build GTM experiment", StepKind.PREPARE,
                        requires_permission=PERM_CUSTOMER_CONTACT),
            MissionStep(3, "Measure", StepKind.MEASURE),
        ],
        approval_gates=[
            ApprovalGate(PERM_CUSTOMER_CONTACT, [2],
                         "GTM experiment execution contacts customers."),
        ],
    )
    base.update(overrides)
    return GrowthMission(**base)


class TestGrowthMissionModel(unittest.TestCase):

    def test_mission_creation_works(self):
        mission = make_mission()
        self.assertEqual(mission.business_name, "Demo Business")
        self.assertEqual(mission.lever, GrowthLever.ACQUISITION)
        self.assertTrue(mission.objective)
        self.assertTrue(mission.problem)
        self.assertEqual(mission.status, MissionStatus.DRAFT)
        self.assertEqual(len(mission.workflow), 3)

    def test_workflow_is_numbered_in_order(self):
        mission = make_mission()
        numbers = [s.step for s in mission.workflow]
        self.assertEqual(numbers, list(range(1, len(mission.workflow) + 1)))

    def test_gate_for_returns_matching_gate(self):
        mission = make_mission()
        gate = mission.gate_for(PERM_CUSTOMER_CONTACT)
        self.assertIsNotNone(gate)
        self.assertEqual(gate.step_numbers, [2])
        self.assertIsNone(mission.gate_for(PERM_PURCHASING))

    def test_external_execution_blocked_before_any_consent(self):
        # No consent applied -> gates unevaluated -> no external execution.
        mission = make_mission()
        self.assertFalse(mission.external_execution_allowed)
        self.assertIsNone(mission.gate_for(PERM_CUSTOMER_CONTACT).granted)

    def test_apply_consent_grants_when_owner_and_customer_authorized(self):
        mission = make_mission()
        mission.apply_consent(ConsentProfile(
            owner_authorized=True,
            customer_contact_authorized=True,
        ))
        self.assertTrue(mission.gate_for(PERM_CUSTOMER_CONTACT).granted)
        self.assertEqual(mission.status, MissionStatus.READY)
        self.assertTrue(mission.external_execution_allowed)

    def test_customer_contact_blocked_without_customer_consent(self):
        # Owner authorized alone is NOT sufficient (AND semantics).
        mission = make_mission()
        mission.apply_consent(ConsentProfile(owner_authorized=True))
        self.assertFalse(mission.gate_for(PERM_CUSTOMER_CONTACT).granted)
        self.assertEqual(mission.status, MissionStatus.BLOCKED)
        self.assertFalse(mission.external_execution_allowed)

    def test_customer_contact_blocked_without_owner_authorization(self):
        mission = make_mission()
        mission.apply_consent(ConsentProfile(customer_contact_authorized=True))
        self.assertFalse(mission.gate_for(PERM_CUSTOMER_CONTACT).granted)
        self.assertEqual(mission.status, MissionStatus.BLOCKED)

    def test_all_gates_required_for_external_execution(self):
        mission = make_mission(
            approval_gates=[
                ApprovalGate(PERM_SUPPLIER_CONTACT, [2], "supplier contact"),
                ApprovalGate(PERM_PURCHASING, [3], "purchasing"),
            ],
        )
        # Two of three granted is still not enough.
        mission.apply_consent(ConsentProfile(
            owner_authorized=True,
            supplier_contact_authorized=True,
        ))
        self.assertTrue(mission.gate_for(PERM_SUPPLIER_CONTACT).granted)
        self.assertFalse(mission.gate_for(PERM_PURCHASING).granted)
        self.assertEqual(mission.status, MissionStatus.BLOCKED)
        self.assertFalse(mission.external_execution_allowed)

    def test_to_dict_roundtrip(self):
        mission = make_mission()
        mission.apply_consent(ConsentProfile(
            owner_authorized=True, customer_contact_authorized=True,
        ))
        data = mission.to_dict()
        self.assertEqual(data["business_name"], "Demo Business")
        self.assertEqual(data["lever"], "acquisition")
        self.assertEqual(data["status"], "READY")
        self.assertEqual(data["workflow"][1]["requires_permission"],
                         PERM_CUSTOMER_CONTACT)
        self.assertEqual(data["approval_gates"][0]["granted"], True)


if __name__ == "__main__":
    unittest.main()
