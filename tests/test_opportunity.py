"""Opportunity Engine tests."""
import unittest

from fire.opportunity import CRITERIA, run_hunt, save_hunt_report, score_opportunity
from fire.registry import CapabilitySearch, build_registry
from fire.quality import evaluate_opportunity

WEIGHT_SUM = sum(w for _, w, _ in CRITERIA)


class TestScoring(unittest.TestCase):
    def test_weights_approx_one(self):
        self.assertAlmostEqual(WEIGHT_SUM, 1.0, delta=0.05)

    def test_score_within_bounds(self):
        for opp in run_hunt():
            self.assertGreaterEqual(opp.weighted_score, 0.0)
            self.assertLessEqual(opp.weighted_score, 10.0)

    def test_direction_applied(self):
        # same everything except competition: worse competition must lower score
        base = run_hunt()[0]
        import copy
        better = copy.deepcopy(base)
        better.scores["competition"] = 2  # low competition (good)
        worse = copy.deepcopy(base)
        worse.scores["competition"] = 9  # high competition (bad)
        self.assertGreater(score_opportunity(better).weighted_score,
                           score_opportunity(worse).weighted_score)

    def test_ranking_deterministic(self):
        a = [o.agent_id if hasattr(o, 'agent_id') else o.name for o in run_hunt()]
        b = [o.agent_id if hasattr(o, 'agent_id') else o.name for o in run_hunt()]
        self.assertEqual(a, b)


class TestOpportunityQuality(unittest.TestCase):
    def test_top_opportunity_passes_gate(self):
        opps = run_hunt()
        top = opps[0].to_dict()
        ev = evaluate_opportunity(top)
        self.assertEqual(ev.verdict, "GO", f"top opportunity should pass gate: {ev.summary}")

    def test_agents_resolved_against_registry(self):
        records, _ = build_registry()
        s = CapabilitySearch(records)
        opps = run_hunt(search=s)
        for opp in opps:
            for aid in opp.required_agents:
                self.assertIsNotNone(s.get(aid), f"{aid} should exist in registry")

    def test_every_opportunity_has_kill_and_scale_criteria(self):
        for opp in run_hunt():
            self.assertTrue(opp.kill_criteria, f"{opp.name} missing kill criteria")
            self.assertTrue(opp.scale_criteria, f"{opp.name} missing scale criteria")
            self.assertTrue(opp.validation_experiment)


if __name__ == "__main__":
    unittest.main()
