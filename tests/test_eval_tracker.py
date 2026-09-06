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


class DailyScoresLedgerTest(unittest.TestCase):
    def test_record_daily_writes_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            daily = str(Path(temporary) / "daily_scores.jsonl")
            record = argparse.Namespace(
                date="2026-09-04", up_ratio=43.44, premium=1.2, promotion=50.0,
                break_rate=48.0, volume_dev=-8.0, sentiment_total=62.0,
                capital_continuity=71.0, opportunity=66.0, top_sector="半导体",
                daily_ledger=daily,
            )
            with redirect_stdout(io.StringIO()):
                TRACKER.cmd_record_daily(record)
            lines = [json.loads(line) for line in Path(daily).read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            rec = lines[0]
            self.assertEqual(rec["type"], "daily_review")
            self.assertEqual(rec["date"], "2026-09-04")
            self.assertEqual(rec["up_ratio"], 43.44)
            self.assertEqual(rec["top_sector"], "半导体")

    def test_record_daily_requires_at_least_one_metric(self):
        record = argparse.Namespace(
            date="2026-09-04", up_ratio=None, premium=None, promotion=None,
            break_rate=None, volume_dev=None, sentiment_total=None,
            capital_continuity=None, opportunity=None, top_sector="",
            daily_ledger="unused.jsonl",
        )
        with self.assertRaises(SystemExit):
            TRACKER.cmd_record_daily(record)

    def test_record_daily_rejects_out_of_range(self):
        record = argparse.Namespace(
            date="2026-09-04", up_ratio=143.0, premium=None, promotion=None,
            break_rate=None, volume_dev=None, sentiment_total=None,
            capital_continuity=None, opportunity=None, top_sector="",
            daily_ledger="unused.jsonl",
        )
        with self.assertRaises(SystemExit):
            TRACKER.cmd_record_daily(record)

    def test_report_daily_threshold_percentiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            daily = str(Path(temporary) / "daily_scores.jsonl")
            for i, ratio in enumerate([30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]):
                record = argparse.Namespace(
                    date=f"2026-09-{i + 1:02d}", up_ratio=ratio, premium=1.0,
                    promotion=50.0, break_rate=30.0, volume_dev=0.0,
                    sentiment_total=60.0, capital_continuity=None, opportunity=None,
                    top_sector="", daily_ledger=daily,
                )
                with redirect_stdout(io.StringIO()):
                    TRACKER.cmd_record_daily(record)
            # 同日期重复写入 => 后写覆盖, 不产生重复样本
            dup = argparse.Namespace(
                date="2026-09-07", up_ratio=95.0, premium=1.0, promotion=50.0,
                break_rate=30.0, volume_dev=0.0, sentiment_total=60.0,
                capital_continuity=None, opportunity=None, top_sector="", daily_ledger=daily,
            )
            with redirect_stdout(io.StringIO()):
                TRACKER.cmd_record_daily(dup)
            report = argparse.Namespace(window=60, daily_ledger=daily)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                TRACKER.cmd_report_daily(report)
            output = buffer.getvalue()
            self.assertIn("涨跌家数比%", output)
            self.assertIn("固定阈值历史落位", output)
            # 70 阈值落位: 去重后 7 个值 (30..80,95), <=70 的有 5 个 => P71
            self.assertIn("70 -> P71", output)
            self.assertIn("样本 7 日 < 60 日", output)


if __name__ == "__main__":
    unittest.main()
