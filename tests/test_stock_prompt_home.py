import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import tools.agent_tools as agent_tools
import tools.artifacts.store as artifact_store
import scripts.doctor as doctor
import scripts.eval_tracker as eval_tracker
import scripts.handoff_store as handoff_store
import scripts.thesis_store as thesis_store
import scripts.update_manager as update_manager


class StockPromptHomKTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._keys = (
            "STOCK_PROMPT_HOME", "STOCK_PROMPT_ARTIFACT_DIR", "STOCK_PROMPT_STATE_DIR",
            "STOCK_PROMPT_THESIS_DIR", "STOCK_PROMPT_REPORT_DIR", "STOCK_PROMPT_LEDGER",
            "STOCK_PROMPT_EVAL_DIR", "STOCK_PROMPT_STATE_HOME",
        )
        self._prev = {k: os.environ.get(k) for k in self._keys}
        for k in self._keys:
            os.environ.pop(k, None)
        os.environ["STOCK_PROMPT_HOME"] = self._tmp.name

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_stock_prompt_home_redirects_all_substores(self):
        home = Path(self._tmp.name)
        self.assertEqual(artifact_store.state_root(), home / "artifacts")
        self.assertEqual(handoff_store.state_root(), home / "state")
        self.assertEqual(thesis_store.state_root(), home / "theses")
        self.assertEqual(Path(eval_tracker.default_ledger()), home / "eval" / "predictions.jsonl")
        self.assertEqual(agent_tools._report_root(), home / "reports")
        self.assertEqual(update_manager.cache_path(), home / "update-status.json")

    def test_specific_env_vars_take_precedence_over_home(self):
        home = Path(self._tmp.name)
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(home / "custom_art")
        os.environ["STOCK_PROMPT_STATE_DIR"] = str(home / "custom_state")
        os.environ["STOCK_PROMPT_THESIS_DIR"] = str(home / "custom_theses")
        os.environ["STOCK_PROMPT_REPORT_DIR"] = str(home / "custom_reports")
        os.environ["STOCK_PROMPT_LEDGER"] = str(home / "custom_ledger.jsonl")

        self.assertEqual(artifact_store.state_root(), home / "custom_art")
        self.assertEqual(handoff_store.state_root(), home / "custom_state")
        self.assertEqual(thesis_store.state_root(), home / "custom_theses")
        self.assertEqual(agent_tools._report_root(), home / "custom_reports")
        self.assertEqual(eval_tracker.resolve_ledger(), str(home / "custom_ledger.jsonl"))


if __name__ == "__main__":
    unittest.main()
