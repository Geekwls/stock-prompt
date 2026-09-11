import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_registry as REGISTRY


class RegistryTest(unittest.TestCase):
    def test_registry_has_unique_live_skills_and_schemas(self):
        data = REGISTRY.load_registry()
        ids = [item["id"] for item in data["skills"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("stock-research-router", ids)
        for relative in data["schemas"].values():
            self.assertTrue(REGISTRY.resolve_path(relative).is_file())
        for relative in data["artifacts"].values():
            self.assertTrue(REGISTRY.resolve_path(relative).is_file())

    def test_mcp_registry_matches_public_docs_count(self):
        data = REGISTRY.load_registry()
        self.assertEqual(len(data["mcp"]["tools"]), 13)
        self.assertIn("get_sector_kline", data["mcp"]["tools"])
        self.assertIn("get_basket_index", data["mcp"]["tools"])

    def test_all_schema_files_are_valid_json(self):
        data = REGISTRY.load_registry()
        for relative in list(data["schemas"].values()) + list(data["artifacts"].values()):
            parsed = json.loads(REGISTRY.resolve_path(relative).read_text(encoding="utf-8"))
            self.assertEqual(parsed.get("type"), "object")
