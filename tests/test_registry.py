"""Registry tests against the real vendored agent library."""
import unittest

from fire.config import load_config, paths
from fire.registry import (
    CapabilitySearch,
    build_registry,
    discover_agents,
    load_registry,
    parse_agent_file,
)


class TestRegistryBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.stats = build_registry()

    def test_agent_count(self):
        # Canonical library has 270 agent definitions (laptop copy was 200+)
        self.assertGreaterEqual(self.stats.total_agents, 250)
        self.assertEqual(self.stats.total_agents, len(self.records))

    def test_divisions(self):
        self.assertIn("engineering", self.stats.departments)
        self.assertIn("marketing", self.stats.departments)
        self.assertIn("specialized", self.stats.departments)

    def test_all_records_well_formed(self):
        for r in self.records:
            self.assertIn(".", r.agent_id)
            self.assertTrue(r.name)
            self.assertTrue(r.department)
            self.assertTrue(r.source_path)
            self.assertIn(r.risk_level, {"low", "medium", "high"})

    def test_registry_index_written(self):
        cfg = load_config()
        p = paths(cfg)
        self.assertTrue(p["registry_file"].exists())
        self.assertEqual(self.stats.index_file, str(p["registry_file"]))

    def test_known_agent_present(self):
        ids = {r.agent_id for r in self.records}
        self.assertIn("engineering.rapid-prototyper", ids)
        self.assertIn("engineering.voice-ai-integration-engineer", ids)
        self.assertIn("specialized.agents-orchestrator", ids)
        self.assertIn("finance.financial-analyst", ids)
        self.assertIn("marketing.tiktok-strategist", ids)

    def test_rapid_prototyper_parsed(self):
        rec = next(r for r in self.records if r.agent_id == "engineering.rapid-prototyper")
        self.assertGreaterEqual(len(rec.capabilities), 3)
        self.assertTrue(rec.description)
        self.assertIn("build", rec.lifecycle_stages)
        self.assertTrue(rec.emoji)

    def test_frontmatter_and_filenames_consistent(self):
        # filenames with department prefix -> agent_id strips it
        rec = next(r for r in self.records if r.agent_id == "engineering.senior-developer")
        self.assertEqual(rec.slug, "engineering-senior-developer")


class TestSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, _ = build_registry()
        cls.search = CapabilitySearch(cls.records)

    def test_voice_quote_mission(self):
        hits = self.search.search(
            "voice note quoting service south african tradespeople whatsapp pdf quote",
            top=10,
        )
        ids = [h["agent_id"] for h in hits]
        self.assertIn("engineering.voice-ai-integration-engineer", ids[:6])

    def test_build_mission(self):
        hits = self.search.search("rapid mvp prototype build software product", top=6)
        ids = [h["agent_id"] for h in hits]
        self.assertIn("engineering.rapid-prototyper", ids[:6])

    def test_sales_mission(self):
        hits = self.search.search("outbound sales pitch proposal close deals", top=5)
        self.assertTrue(any(h["department"] == "sales" for h in hits))

    def test_department_filter(self):
        hits = self.search.search("build mvp", top=5, department="engineering")
        self.assertTrue(hits)
        self.assertTrue(all(h["department"] == "engineering" for h in hits))

    def test_finance_mission(self):
        hits = self.search.search("invoice bookkeeping cash flow financial analyst", top=5)
        ids = [h["agent_id"] for h in hits]
        self.assertTrue(any("finance" in i for i in ids))

    def test_index_meta(self):
        meta = self.search.snapshot_meta()
        self.assertEqual(meta["indexed"], len(self.records))
        self.assertGreater(meta["terms"], 1000)


class TestDiscovery(unittest.TestCase):
    def test_discover_excludes_non_agent_dirs(self):
        cfg = load_config()
        p = paths(cfg)
        found = discover_agents(p["agent_library"])
        for f in found:
            parts = f.relative_to(p["agent_library"]).parts
            self.assertNotIn(parts[0], ("integrations", "strategy", "examples", "scripts", ".github"))


if __name__ == "__main__":
    unittest.main()
