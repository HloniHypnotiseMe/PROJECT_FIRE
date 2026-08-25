"""Quality / Reality Engine + Memory + Revenue tests."""
import json
import tempfile
import unittest
from pathlib import Path

from fire.models import RevenueEngine
from fire.quality import evaluate_artifact
from fire.memory import EventLog
from fire.revenue import capacity_scenario, portfolio


class TestQuality(unittest.TestCase):
    def test_missing_file_is_no_go(self):
        ev = evaluate_artifact("/nonexistent/file.md")
        self.assertEqual(ev.verdict, "NO-GO")

    def test_good_report_is_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "report.md"
            p.write_text(
                "# Opportunity Ranking\n\n## Evidence\n\n"
                "https://example.com/source\n\n## Economics\n\n## Customer\n\n"
                "## Problem\n\n## Proposed Solution\n\n## Validation Experiment\n\n"
                "## Required Agent Team\n\n## Execution Workflow\n\n"
                "## Success Criteria\n\n## Kill Criteria\n\n## Scale Criteria\n\n"
                "detailed content " * 20, encoding="utf-8")
            ev = evaluate_artifact(p)
            self.assertEqual(ev.verdict, "GO", ev.summary)

    def test_forbidden_claim_triggers_no_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "report.md"
            p.write_text("We achieved R1,000,000/day already. " + "x" * 400,
                         encoding="utf-8")
            ev = evaluate_artifact(p)
            self.assertEqual(ev.verdict, "NO-GO")

    def test_missing_sections_revise(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "report.md"
            p.write_text("Just a small file. " * 30, encoding="utf-8")
            ev = evaluate_artifact(p)
            self.assertIn(ev.verdict, ("REVISE", "NO-GO"))


class TestMemory(unittest.TestCase):
    def test_event_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp))
            log.append("test_event", {"a": 1})
            evs = log.list("test_event")
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["a"], 1)

    def test_mission_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp))
            rec = log.start_mission("Test mission", "build", [])
            self.assertEqual(rec.status, "running")
            upd = log.update_mission(rec.mission_id, status="done")
            self.assertEqual(upd.status, "done")
            missions = log.all_missions()
            self.assertEqual(len(missions), 1)
            self.assertEqual(missions[0].status, "done")


class TestRevenue(unittest.TestCase):
    def test_mrr_math(self):
        e = RevenueEngine("subs", 199, "month", 10)
        port = portfolio([e])
        self.assertAlmostEqual(port["total_mrr"], 1990.0)
        self.assertAlmostEqual(port["total_arr"], 1990.0 * 12)

    def test_percent_model(self):
        e = RevenueEngine("chaser", 0.03, "percent", 20_000)
        port = portfolio([e])
        self.assertAlmostEqual(port["total_mrr"], 600.0)

    def test_capacity_scenario(self):
        cap = capacity_scenario(target_daily_zar=1_000_000, avg_daily_rev_per_engine=500)
        self.assertEqual(cap["engines_needed"], 2000)
        self.assertIn("CAPACITY", cap["label"])


if __name__ == "__main__":
    unittest.main()
