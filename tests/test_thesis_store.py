import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "thesis_store.py"
SPEC = importlib.util.spec_from_file_location("thesis_store", MODULE)
STORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STORE)


def payload():
    return {
        "stock_code": "300308",
        "stock_name": "中际旭创",
        "as_of": "2026-09-08 15:00 收盘",
        "thesis": "需求与盈利兑现仍是核心逻辑",
        "logic_health": "稳定",
        "catalysts": ["财报"],
        "risk_flags": ["估值偏高"],
        "next_triggers": [{"id": "T1", "condition": "财报确认增长", "status": "pending"}],
    }


class ThesisStoreTest(unittest.TestCase):
    def test_write_update_preserves_history_and_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "theses"
            first = STORE.prepare_thesis(payload())
            path = STORE.atomic_write(first, root)
            second_payload = payload()
            second_payload["logic_health"] = "强化"
            second = STORE.prepare_thesis(second_payload, STORE.load_existing(root, "300308"))
            STORE.atomic_write(second, root)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["logic_health"], "强化")
            self.assertEqual(len(saved["history"]), 1)
            self.assertEqual(saved["history"][0]["logic_health"], "稳定")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_sensitive_fields_require_opt_in(self):
        item = payload()
        item["cost_basis"] = 88.0
        with self.assertRaisesRegex(ValueError, "默认禁止"):
            STORE.prepare_thesis(item)
        prepared = STORE.prepare_thesis(item, allow_sensitive=True)
        self.assertEqual(prepared["cost_basis"], 88.0)

    def test_triggers_must_be_structured(self):
        item = payload()
        item["next_triggers"] = ["财报确认"]
        with self.assertRaisesRegex(ValueError, "必须是对象"):
            STORE.prepare_thesis(item)
