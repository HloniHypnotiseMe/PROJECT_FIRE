"""Tests for the mission lifecycle (fire/growth/lifecycle.py).

Covers: deterministic ids, persistence, ordered execution, per-step consent
enforcement, failure/retry, resume, direction-aware measurement,
SCALE/OPTIMIZE/KILL decisions, status transitions, event recording and the
execution-report quality gate.
"""

import tempfile
import unittest
from pathlib import Path

from fire.growth.diagnostic import BusinessMetrics
from fire.growth.lifecycle import (
    DECISION_KILL,
    DECISION_OPTIMIZE,
    DECISION_SCALE,
    MissionExecutionError,
    MissionRuntime,
    StepStatus,
)
from fire.growth.models import BusinessProfile, GrowthLever
from fire.growth.orchestrator import GrowthOrchestrator
from fire.onboarding.consent import ConsentProfile
from fire.registry import CapabilitySearch, load_registry

FULL_CUSTOMER = ConsentProfile(owner_authorized=True,
                               customer_contact_authorized=True)
FULL_SUPPLY = ConsentProfile(owner_authorized=True,
                             supplier_contact_authorized=True,
                             purchasing_authorized=True)
OWNER_ONLY = ConsentProfile(owner_authorized=True)


def weak_acquisition() -> BusinessMetrics:
    return BusinessMetrics(monthly_leads=0, conversion_rate=0.05,
                           average_customer_spend=1000,
                           repeat_purchase_rate=0.50,
                           customer_retention_rate=0.70,
                           input_cost_ratio=0.30)


def weak_supply() -> BusinessMetrics:
    m = BusinessMetrics(monthly_leads=100, conversion_rate=0.30,
                        average_customer_spend=500,
                        repeat_purchase_rate=0.50,
                        customer_retention_rate=0.80,
                        input_cost_ratio=0.80)
    return m


class TestMissionLifecycle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.search = CapabilitySearch(load_registry())
        cls.orchestrator = GrowthOrchestrator(search=cls.search)
        cls.business = BusinessProfile(business_name="Demo Business",
                                       sector="Retail", location="Gauteng")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rt = MissionRuntime(memory_dir=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def gtm_mission_id(self) -> str:
        return self.rt.persist(self.orchestrator.create_mission(
            self.business, weak_acquisition()))

    def supply_mission_id(self) -> str:
        return self.rt.persist(self.orchestrator.create_mission(
            self.business, weak_supply()))

    def run_steps(self, mid: str, count: int, **kw):
        out = []
        for step in range(1, count + 1):
            out.append(self.rt.execute_step(mid, step, **kw))
        return out

    # -- 1-3. identity + persistence ------------------------------------------
    def test_deterministic_mission_id(self):
        id1 = self.gtm_mission_id()
        id2 = self.rt.persist(self.orchestrator.create_mission(
            self.business, weak_acquisition()))
        self.assertEqual(id1, id2)
        other = BusinessProfile(business_name="Other Business",
                                sector="Retail", location="Johannesburg")
        id3 = self.rt.persist(self.orchestrator.create_mission(other,
                                                               weak_acquisition()))
        self.assertNotEqual(id1, id3)
        self.assertTrue(id1.startswith("gm-"))

    def test_idempotent_persist_single_file(self):
        mid = self.gtm_mission_id()
        self.gtm_mission_id()
        self.assertEqual(self.rt.list_missions(), [mid])
        self.assertEqual(len(list(Path(self._tmp.name, "growth_missions")
                                  .glob("gm-*.json"))), 1)

    def test_persist_and_load_roundtrip(self):
        mid = self.gtm_mission_id()
        m = self.rt.load(mid)
        self.assertEqual(m.business_name, "Demo Business")
        self.assertEqual(m.lever, GrowthLever.ACQUISITION)
        self.assertEqual(len(m.workflow), 10)
        self.assertEqual(len(m.approval_gates), 1)
        self.assertEqual(m.status.value, "DRAFT")
        self.assertEqual(m.baseline["monthly_leads"], 0)

    # -- 4-7. execution control + consent ---------------------------------------
    def test_prepare_steps_run_without_consent(self):
        mid = self.gtm_mission_id()
        for r in self.run_steps(mid, 4):
            self.assertEqual(r.status, StepStatus.COMPLETED)
            self.assertFalse(r.blocked)
        # step 5 is the consent-gated experiment step
        blocked = self.rt.execute_step(mid, 5)
        self.assertTrue(blocked.blocked)
        self.assertEqual(blocked.status, StepStatus.PENDING)
        self.assertIn("customer_contact_authorized", blocked.reason)

    def test_external_step_runs_with_consent_applied(self):
        mid = self.gtm_mission_id()
        self.run_steps(mid, 4)
        self.rt.apply_consent(mid, FULL_CUSTOMER)
        r = self.rt.execute_step(mid, 5, result="experiment designed",
                                 evidence="channel audit notes")
        self.assertEqual(r.status, StepStatus.COMPLETED)
        self.assertFalse(r.blocked)

    def test_consent_gate_step_requires_granted_gate(self):
        mid = self.supply_mission_id()
        self.run_steps(mid, 5)
        # step 6: explicit supplier-contact consent gate
        blocked = self.rt.execute_step(mid, 6)
        self.assertTrue(blocked.blocked)
        self.assertIn("supplier_contact_authorized", blocked.reason)
        # grant consent, then the checkpoint and the external step pass
        ok = self.rt.execute_step(mid, 6, consent=FULL_SUPPLY,
                                  result="authorization verified")
        self.assertEqual(ok.status, StepStatus.COMPLETED)
        self.assertEqual(self.rt.execute_step(mid, 7).status,
                         StepStatus.COMPLETED)

    def test_out_of_order_step_rejected(self):
        mid = self.gtm_mission_id()
        with self.assertRaises(MissionExecutionError):
            self.rt.execute_step(mid, 3)  # step 1 is next actionable

    def test_completed_step_is_idempotent(self):
        mid = self.gtm_mission_id()
        first = self.rt.execute_step(mid, 1, result="audit done")
        again = self.rt.execute_step(mid, 1, result="ignored")
        self.assertEqual(first.attempts, 1)
        self.assertEqual(again.attempts, 1)
        state = self.rt.state(mid)
        self.assertEqual(state["steps"]["1"]["attempts"], 1)
        self.assertEqual(state["steps"]["1"]["result"], "audit done")

    # -- 8-10. failure, resume, blocked -------------------------------------------
    def test_failure_recorded_and_retryable(self):
        mid = self.gtm_mission_id()
        self.rt.execute_step(mid, 1)
        failed = self.rt.fail_step(mid, 2, reason="source data missing")
        self.assertEqual(failed.status, StepStatus.FAILED)
        self.assertEqual(failed.attempts, 1)
        self.assertEqual(self.rt.next_actionable(mid), 2)
        retried = self.rt.execute_step(mid, 2, result="recovered")
        self.assertEqual(retried.status, StepStatus.COMPLETED)
        state = self.rt.state(mid)
        self.assertEqual(state["steps"]["2"]["status"], "completed")
        self.assertEqual(state["steps"]["2"]["attempts"], 2)

    def test_resume_after_reload(self):
        mid = self.gtm_mission_id()
        self.rt.execute_step(mid, 1)
        fresh = MissionRuntime(memory_dir=self._tmp.name)  # same state dir
        self.assertEqual(fresh.next_actionable(mid), 2)
        self.assertEqual(fresh.execute_step(mid, 2).status,
                         StepStatus.COMPLETED)
        state = fresh.state(mid)
        self.assertEqual(state["steps"]["1"]["attempts"], 1)

    def test_blocked_mission_external_steps_stay_blocked(self):
        mid = self.supply_mission_id()
        self.rt.apply_consent(mid, OWNER_ONLY)  # not enough for suppliers
        self.assertEqual(self.rt.load(mid).status.value, "BLOCKED")
        self.run_steps(mid, 5)  # internal prep still allowed
        self.assertTrue(self.rt.execute_step(mid, 6).blocked)
        # the pending consent-gate step also blocks the external step after it
        with self.assertRaises(MissionExecutionError):
            self.rt.execute_step(mid, 7)
        # once authorized, both steps flow through
        self.rt.apply_consent(mid, FULL_SUPPLY)
        self.assertEqual(self.rt.execute_step(mid, 6).status,
                         StepStatus.COMPLETED)
        self.assertEqual(self.rt.execute_step(mid, 7).status,
                         StepStatus.COMPLETED)

    # -- 11-12. measurement ------------------------------------------------------------
    def test_measurement_direction_aware(self):
        mid = self.gtm_mission_id()  # higher is better
        m = self.rt.measure(mid, BusinessMetrics(
            monthly_leads=5, conversion_rate=0.05,
            average_customer_spend=1000, repeat_purchase_rate=0.5,
            customer_retention_rate=0.7, input_cost_ratio=0.3))
        self.assertAlmostEqual(m.progress["monthly_leads"], 0.5)   # 5 of 10
        self.assertAlmostEqual(m.progress["conversion_rate"], 0.0)  # still 0.05

        sid = self.supply_mission_id()  # lower input cost is better
        m2 = self.rt.measure(sid, BusinessMetrics(
            monthly_leads=100, conversion_rate=0.30,
            average_customer_spend=500, repeat_purchase_rate=0.5,
            customer_retention_rate=0.8, input_cost_ratio=0.85))
        self.assertAlmostEqual(m2.progress["input_cost_ratio"], 0.0)  # worse
        m3 = self.rt.measure(sid, BusinessMetrics(
            monthly_leads=100, conversion_rate=0.30,
            average_customer_spend=500, repeat_purchase_rate=0.5,
            customer_retention_rate=0.8, input_cost_ratio=0.72))
        self.assertAlmostEqual(m3.progress["input_cost_ratio"], 1.0)  # at target

    # -- 13-15. decisions ---------------------------------------------------------------
    def _metrics_with(self, leads: float, conv: float) -> BusinessMetrics:
        return BusinessMetrics(monthly_leads=leads, conversion_rate=conv,
                               average_customer_spend=1000,
                               repeat_purchase_rate=0.5,
                               customer_retention_rate=0.7,
                               input_cost_ratio=0.3)

    def test_decision_scale_on_targets_met(self):
        mid = self.gtm_mission_id()
        self.rt.measure(mid, self._metrics_with(10, 0.10))
        self.assertEqual(self.rt.decide(mid), DECISION_SCALE)
        self.assertEqual(self.rt.load(mid).status.value, "SCALED")

    def test_decision_optimize_on_partial_progress(self):
        mid = self.gtm_mission_id()
        self.rt.measure(mid, self._metrics_with(7.5, 0.075))  # 0.75 / 0.5
        self.assertEqual(self.rt.decide(mid), DECISION_OPTIMIZE)
        # OPTIMIZE does not change mission status; the next iteration acts
        self.assertEqual(self.rt.load(mid).status.value, "DRAFT")

    def test_decision_kill_on_no_progress(self):
        mid = self.gtm_mission_id()
        self.rt.measure(mid, self._metrics_with(0, 0.05))  # still at baseline
        self.assertEqual(self.rt.decide(mid), DECISION_KILL)
        self.assertEqual(self.rt.load(mid).status.value, "KILLED")

    def test_decision_requires_measurement(self):
        mid = self.gtm_mission_id()
        with self.assertRaises(MissionExecutionError):
            self.rt.decide(mid)

    # -- 16. status transitions -----------------------------------------------------------
    def test_status_transitions(self):
        mid = self.gtm_mission_id()
        self.assertEqual(self.rt.load(mid).status.value, "DRAFT")
        self.rt.apply_consent(mid, OWNER_ONLY)
        self.assertEqual(self.rt.load(mid).status.value, "BLOCKED")
        self.rt.apply_consent(mid, FULL_CUSTOMER)
        self.assertEqual(self.rt.load(mid).status.value, "READY")
        self.rt.execute_step(mid, 1)
        self.assertEqual(self.rt.load(mid).status.value, "IN_PROGRESS")
        self.run_steps(mid, 10)
        self.assertIsNotNone(self.rt.state(mid)["completed_at"])
        self.rt.measure(mid, self._metrics_with(10, 0.10))
        self.rt.decide(mid)
        self.assertEqual(self.rt.load(mid).status.value, "SCALED")

    # -- 17-19. events + report -----------------------------------------------------------
    def test_events_recorded_in_event_log(self):
        mid = self.gtm_mission_id()
        self.rt.apply_consent(mid, FULL_CUSTOMER)
        self.run_steps(mid, 2)
        self.rt.measure(mid, self._metrics_with(10, 0.10))
        self.rt.decide(mid)
        types = {e["type"] for e in self.rt.events.list(limit=200)}
        for expected in ("gm_mission_created", "gm_consent_applied",
                         "gm_step_completed", "gm_measured",
                         "gm_decision_made"):
            self.assertIn(expected, types)

    def test_execution_report_written_and_gated(self):
        mid = self.gtm_mission_id()
        self.run_steps(mid, 3)
        path = self.rt.write_execution_report(mid)
        self.assertTrue(path.exists())
        report = self.rt.state(mid)["report"]
        self.assertIn(report["verdict"], ("GO", "REVISE"))
        self.assertNotEqual(report["verdict"], "NO-GO")
        text = path.read_text(encoding="utf-8")
        self.assertIn(mid, text)
        self.assertIn("Demo Business", text)
        self.assertIn("Baseline -> Target", text)


if __name__ == "__main__":
    unittest.main()
