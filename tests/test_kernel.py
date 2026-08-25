"""Command Kernel tests: objective parsing, team assembly, workflow."""
import unittest

from fire.kernel import build_workflow, mission_to_plan, parse_objective
from fire.registry import CapabilitySearch, build_registry


class TestObjectiveParser(unittest.TestCase):
    def test_find_intent(self):
        o = parse_objective(
            "Find the highest-potential business opportunity that can be validated quickly "
            "in South Africa with a credible path to scalable recurring revenue"
        )
        self.assertEqual(o.intent, "find")
        self.assertTrue(o.constraints.get("location") == "South Africa")
        self.assertTrue(o.constraints.get("recurring") is True)
        self.assertIn("discover", o.stages)

    def test_build_intent(self):
        o = parse_objective("Build an MVP for a WhatsApp voice-note quoting bot")
        self.assertEqual(o.intent, "build")
        self.assertIn("engineering", o.departments)

    def test_audit_intent(self):
        o = parse_objective("Audit this business for revenue leakages")
        self.assertEqual(o.intent, "audit")

    def test_constraints(self):
        o = parse_objective("Build a tool priced at R199 per month for plumbers in Johannesburg")
        self.assertAlmostEqual(o.constraints["price_zar"], 199.0)
        self.assertEqual(o.constraints["location"], "South Africa")


class TestTeamAssembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, _ = build_registry()
        cls.search = CapabilitySearch(cls.records)

    def test_mission_plan_voice_quote(self):
        plan = mission_to_plan(
            "Build an MVP for a WhatsApp voice-note to PDF quote service for South African "
            "tradespeople priced at R199 per month",
            self.search,
        )
        self.assertGreaterEqual(len(plan["team"]), 3)
        self.assertLessEqual(len(plan["team"]), 6)
        ids = [m["agent_id"] for m in plan["team"]]
        self.assertIn("specialized.agents-orchestrator", ids)
        self.assertTrue(any("engineering" in i for i in ids))
        self.assertTrue(plan["workflow"]["steps"])

    def test_workflow_ordered_by_stages(self):
        plan = mission_to_plan("Build an MVP for a WhatsApp voice-note quoting bot", self.search)
        phases = [s["phase"] for s in plan["workflow"]["steps"]]
        self.assertTrue(phases)

    def test_no_duplicate_agents(self):
        plan = mission_to_plan("Launch a TikTok marketing campaign for a CV optimizer", self.search)
        ids = [m["agent_id"] for m in plan["team"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_quality_gate_included(self):
        plan = mission_to_plan("Build an MVP for a WhatsApp voice-note quoting bot", self.search)
        roles = [m["role"] for m in plan["team"]]
        self.assertIn("quality-gate", roles)


if __name__ == "__main__":
    unittest.main()
