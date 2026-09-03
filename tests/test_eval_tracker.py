import argparse
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "eval_tracker.py"
SPEC = importlib.util.spec_from_file_location("eval_tracker", MODULE_PATH)
TRACKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACKER)


def load_fresh():
    """重新加载模块，捕获环境变量变化后的模块级状态。"""
    spec = importlib.util.spec_from_file_location("eval_tracker_fresh", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LedgerResolutionTest(unittest.TestCase):
    def setUp(self):
        self._env = {"STOCK_PROMPT_EVAL_DIR": os.environ.get("STOCK_PROMPT_EVAL_DIR"),
                     "STOCK_PROMPT_LEDGER": os.environ.get("STOCK_PROMPT_LEDGER")}
        self._cwd = os.getcwd()

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.chdir(self._cwd)

    def test_default_ledger_is_anchored_to_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["STOCK_PROMPT_EVAL_DIR"] = temporary
            module = load_fresh()
            ledger = module.resolve_ledger()
            self.assertEqual(Path(ledger), Path(temporary) / ".stock-prompt" / "eval" / "predictions.jsonl")
            self.assertNotIn(str(Path.cwd()), str(Path(ledger).resolve()))

    def test_explicit_argument_and_env_override_win(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["STOCK_PROMPT_EVAL_DIR"] = temporary
            module = load_fresh()
            self.assertEqual(module.resolve_ledger("custom.json"), "custom.json")
            os.environ["STOCK_PROMPT_LEDGER"] = "env-ledger.jsonl"
            self.assertEqual(module.resolve_ledger(), "env-ledger.jsonl")

    def test_legacy_ledger_is_migrated_to_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["STOCK_PROMPT_EVAL_DIR"] = temporary
            os.chdir(temporary)
            try:
                legacy = Path(temporary) / "eval" / "predictions.jsonl"
                legacy.parent.mkdir()
                legacy.write_text('{"type": "prediction", "date": "2026-09-01"}\n', encoding="utf-8")

                module = load_fresh()
                anchor = Path(temporary) / ".stock-prompt" / "eval" / "predictions.jsonl"
                with redirect_stdout(io.StringIO()):
                    resolved = module.resolve_ledger()
                self.assertEqual(Path(resolved), anchor)
                self.assertIn("2026-09-01", anchor.read_text(encoding="utf-8"))
                self.assertTrue(legacy.exists(), "迁移不得删除原文件")
            finally:
                os.chdir(self._cwd)


class LedgerRoundtripTest(unittest.TestCase):
    def test_record_result_report_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")

            record = argparse.Namespace(
                date="2026-09-03", regime="S3", p_up=55, p_side=30, p_down=15,
                opportunity=78, top_sector="半导体", r1=3850.0, s1=3800.0, ledger=ledger,
            )
            with redirect_stdout(io.StringIO()):
                TRACKER.cmd_record(record)

            result = argparse.Namespace(
                date="2026-09-03", z_atr=0.62, top_sectors="半导体, 低空经济",
                close=3842.0, high=3855.0, low=3805.0, ledger=ledger,
            )
            with redirect_stdout(io.StringIO()):
                TRACKER.cmd_result(result)

            with open(ledger, "r", encoding="utf-8") as stream:
                lines = [json.loads(line) for line in stream if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["type"], "prediction")
            self.assertEqual(lines[1]["actual_state"], "up")

            report = argparse.Namespace(window=20, ledger=ledger)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                TRACKER.cmd_report(report)
            output = buffer.getvalue()
            self.assertIn("Brier Score", output)
            self.assertIn("方向命中率", output)
            self.assertIn("点位有效率", output)


if __name__ == "__main__":
    unittest.main()
