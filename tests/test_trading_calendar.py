import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "trading_calendar.py"
SPEC = importlib.util.spec_from_file_location("trading_calendar", MODULE_PATH)
TC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TC)

HANDOFF_PATH = Path(__file__).resolve().parents[1] / "scripts" / "handoff_store.py"
HANDOFF_SPEC = importlib.util.spec_from_file_location("handoff_store_tc", HANDOFF_PATH)
STORE = importlib.util.module_from_spec(HANDOFF_SPEC)
HANDOFF_SPEC.loader.exec_module(STORE)

TRACKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "eval_tracker.py"
TRACKER_SPEC = importlib.util.spec_from_file_location("eval_tracker_tc", TRACKER_PATH)
TRACKER = importlib.util.module_from_spec(TRACKER_SPEC)
TRACKER_SPEC.loader.exec_module(TRACKER)

EMPTY_CLOSED = set()


class TradingCalendarPureTest(unittest.TestCase):
    """周末规则 + closed_dates 节假日表的确定性推算 (显式传入 closed_days, 不依赖真实时钟)。"""

    def test_is_trading_day_weekend_and_weekday(self):
        self.assertFalse(TC.is_trading_day(date(2026, 11, 15), EMPTY_CLOSED))  # 星期日
        self.assertFalse(TC.is_trading_day(date(2026, 11, 14), EMPTY_CLOSED))  # 星期六
        self.assertTrue(TC.is_trading_day(date(2026, 11, 13), EMPTY_CLOSED))  # 星期五
        self.assertTrue(TC.is_trading_day(date(2026, 11, 16), EMPTY_CLOSED))  # 星期一

    def test_closed_dates_table_is_honored(self):
        closed = {date(2026, 11, 16)}
        self.assertFalse(TC.is_trading_day(date(2026, 11, 16), closed))
        self.assertEqual(TC.next_trading_day(date(2026, 11, 13), closed), date(2026, 11, 17))

    def test_next_and_prev_across_weekend(self):
        self.assertEqual(TC.next_trading_day(date(2026, 11, 13), EMPTY_CLOSED), date(2026, 11, 16))
        self.assertEqual(TC.prev_trading_day(date(2026, 11, 16), EMPTY_CLOSED), date(2026, 11, 13))

    def test_resolve_target_trading_day(self):
        self.assertEqual(TC.resolve_target_trading_day(date(2026, 11, 15), EMPTY_CLOSED), date(2026, 11, 16))
        self.assertEqual(TC.resolve_target_trading_day(date(2026, 11, 16), EMPTY_CLOSED), date(2026, 11, 16))

    def test_repo_calendar_covers_november_2026(self):
        # 真实日历文件下的 2026-11 案例回归 (11 月无 A 股法定假日)
        self.assertEqual(TC.resolve_target_trading_day(date(2026, 11, 15)), date(2026, 11, 16))
        self.assertEqual(TC.next_trading_day(date(2026, 11, 13)), date(2026, 11, 16))


class ValidateRecordDateGateTest(unittest.TestCase):
    def test_future_date_must_equal_next_trading_day(self):
        ok, message = TC.validate_record_date("2026-11-17", "preopen", EMPTY_CLOSED, today=date(2026, 11, 15))
        self.assertFalse(ok)
        self.assertIn("应为 2026-11-16", message)

    def test_next_trading_day_target_passes(self):
        ok, _ = TC.validate_record_date("2026-11-16", "preopen", EMPTY_CLOSED, today=date(2026, 11, 15))
        self.assertTrue(ok)

    def test_non_trading_day_is_rejected_even_for_backfill(self):
        ok, message = TC.validate_record_date("2026-11-15", "preopen", EMPTY_CLOSED, today=date(2026, 11, 15))
        self.assertFalse(ok)
        self.assertIn("不是 A 股交易日", message)

    def test_backfill_past_trading_day_passes_without_future_rule(self):
        ok, _ = TC.validate_record_date("2026-11-13", "result", EMPTY_CLOSED, today=date(2026, 11, 15))
        self.assertTrue(ok)


class TradingCalendarCliTest(unittest.TestCase):
    def test_resolve_target_cli(self):
        env = dict(os.environ, STOCK_PROMPT_FAKE_TODAY="2026-11-15")
        proc = subprocess.run(
            [sys.executable, "scripts/trading_calendar.py", "resolve-target", "--date", "2026-11-15"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["target_trading_date"], "2026-11-16")
        self.assertTrue(payload["derived"])

    def test_validate_record_cli_blocks_wrong_target(self):
        env = dict(os.environ, STOCK_PROMPT_FAKE_TODAY="2026-11-15")
        proc = subprocess.run(
            [sys.executable, "scripts/trading_calendar.py", "validate-record", "--date", "2026-11-17", "--phase", "preopen"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("2026-11-16", payload["message"])


class EvalRecordGateIntegrationTest(unittest.TestCase):
    """eval record 经 cmd_record 走真实门禁: 错期目标被 [BLOCKED], 正确目标落盘为 11-16。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_fake = os.environ.get("STOCK_PROMPT_FAKE_TODAY")
        self._prev_artifact = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
        os.environ["STOCK_PROMPT_FAKE_TODAY"] = "2026-11-15"
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(self._tmp.name) / "artifacts")

    def tearDown(self):
        if self._prev_fake is None:
            os.environ.pop("STOCK_PROMPT_FAKE_TODAY", None)
        else:
            os.environ["STOCK_PROMPT_FAKE_TODAY"] = self._prev_fake
        if self._prev_artifact is None:
            os.environ.pop("STOCK_PROMPT_ARTIFACT_DIR", None)
        else:
            os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = self._prev_artifact
        self._tmp.cleanup()

    @staticmethod
    def _namespace(date_str, ledger):
        return argparse.Namespace(
            date=date_str, regime="S6", p_up=6, p_side=25, p_down=69,
            opportunity=24, top_sector="影视院线", top_sectors="影视院线, 银行",
            r1=3676.0, s1=3593.0, ledger=ledger,
        )

    def test_wrong_future_target_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            with self.assertRaises(SystemExit) as ctx:
                TRACKER.cmd_record(self._namespace("2026-11-17", ledger))
            self.assertIn("[BLOCKED]", str(ctx.exception))
            self.assertFalse(Path(ledger).exists(), "门禁拦截后不得落盘")

    def test_correct_target_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            with redirect_stdout(io.StringIO()):
                TRACKER.cmd_record(self._namespace("2026-11-16", ledger))
            lines = [json.loads(line) for line in Path(ledger).read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(lines[0]["date"], "2026-11-16")
            self.assertEqual(lines[0]["market_phase"], "preopen")


class HandoffDateGateTest(unittest.TestCase):
    @staticmethod
    def _payload(as_of, report_type="prediction", trading_date=None):
        payload = {
            "report_type": report_type,
            "as_of": as_of,
            "source_count": 3,
            "coverage": "87.5%",
            "scored_weight": "87.5%",
            "confidence": "中",
            "market_regime": "S6",
            "primary_sectors": [],
            "watchlist": [],
            "risk_flags": [],
            "next_triggers": [],
        }
        if trading_date:
            payload["trading_date"] = trading_date
        return payload

    def test_weekend_as_of_auto_advances_to_next_trading_day(self):
        with patch.dict(os.environ, {"STOCK_PROMPT_FAKE_TODAY": "2026-11-15"}):
            prepared = STORE.prepare_handoff(self._payload("2026-11-15 22:00 + 周末盘前推演"), model_version="8.1.1")
        self.assertEqual(prepared["trading_date"], "2026-11-16")
        self.assertIn("自动顺延", prepared.get("trading_date_note", ""))

    def test_explicit_non_trading_trading_date_is_rejected(self):
        with patch.dict(os.environ, {"STOCK_PROMPT_FAKE_TODAY": "2026-11-15"}):
            with self.assertRaises(ValueError):
                STORE.prepare_handoff(self._payload("2026-11-15 22:00", trading_date="2026-11-15"), "8.1.1")

    def test_trading_day_payload_unchanged(self):
        prepared = STORE.prepare_handoff(
            self._payload("2026-11-16 08:35", trading_date="2026-11-16"), model_version="8.1.1")
        self.assertEqual(prepared["trading_date"], "2026-11-16")
        self.assertNotIn("trading_date_note", prepared)

    def test_non_prediction_types_keep_original_semantics(self):
        prepared = STORE.prepare_handoff(self._payload("2026-11-15 20:00", report_type="daily"), model_version="8.1.1")
        self.assertEqual(prepared["trading_date"], "2026-11-15")


if __name__ == "__main__":
    unittest.main()
