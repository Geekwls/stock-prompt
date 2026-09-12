import importlib.util
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "handoff_store.py"
SPEC = importlib.util.spec_from_file_location("handoff_store", MODULE)
STORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STORE)


def payload(as_of="2026-09-04 15:00 +08:00", report_type="daily"):
    result = {
        "report_type": report_type,
        "as_of": as_of,
        "source_count": 8,
        "coverage": "82.5%",
        "scored_weight": "80%",
        "confidence": "中",
        "market_regime": "S2",
        "primary_sectors": ["半导体"],
        "watchlist": ["300308"],
        "risk_flags": [],
        "next_triggers": ["放量突破"],
    }
    if report_type == "stock":
        result["subject"] = {"type": "stock", "id": "300308", "name": "中际旭创"}
    return result


class HandoffStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = {k: os.environ.get(k) for k in ("STOCK_PROMPT_STATE_DIR", "STOCK_PROMPT_HOME", "STOCK_PROMPT_ARTIFACT_DIR")}
        os.environ["STOCK_PROMPT_STATE_DIR"] = str(Path(self._tmp.name) / "state")
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(self._tmp.name) / "artifacts")

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_state_root_with_stock_prompt_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["STOCK_PROMPT_HOME"] = temporary
            os.environ.pop("STOCK_PROMPT_STATE_DIR", None)
            self.assertEqual(STORE.state_root(), Path(temporary) / "state")

    def test_prepare_and_atomic_write(self):
        prepared = STORE.prepare_handoff(payload(), model_version="7.0.0")
        with tempfile.TemporaryDirectory() as temporary:
            path = STORE.atomic_write(prepared, Path(temporary))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], "1.0")
            self.assertEqual(saved["trading_date"], "2026-09-04")
            self.assertEqual(saved["model_version"], "7.0.0")

    def test_legacy_enums_are_normalized_on_write_and_read(self):
        legacy = payload(report_type="close_review")
        legacy["regime_namespace"] = "daily-s0-s6"
        prepared = STORE.prepare_handoff(legacy, model_version="7.0.0")
        self.assertEqual(prepared["report_type"], "daily")
        self.assertEqual(prepared["regime_namespace"], "market-s0-s6")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "handoff-20260904-close_review.json"
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            latest = STORE.select_latest(root, within_trading_days=2, reference=date(2026, 9, 7))
            self.assertEqual(latest["handoff"]["report_type"], "daily")
            self.assertEqual(latest["handoff"]["regime_namespace"], "market-s0-s6")

    def test_invalid_payload_is_rejected(self):
        bad = payload()
        bad["coverage"] = "很多"
        with self.assertRaisesRegex(ValueError, "coverage"):
            STORE.prepare_handoff(bad)

    def test_stock_handoffs_are_isolated_by_subject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = STORE.prepare_handoff(payload(report_type="stock"), "7.0.0")
            second_payload = payload(report_type="stock")
            second_payload["subject"] = {"type": "stock", "id": "600519", "name": "贵州茅台"}
            second = STORE.prepare_handoff(second_payload, "7.0.0")
            first_path = STORE.atomic_write(first, root)
            second_path = STORE.atomic_write(second, root)
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(first_path.name.endswith("stock-300308.json"))
            latest = STORE.select_latest(
                root, within_trading_days=5, report_type="stock",
                reference=date(2026, 9, 7), subject="600519",
            )
            self.assertEqual(latest["handoff"]["subject"]["name"], "贵州茅台")

    def test_stock_handoff_requires_subject(self):
        with self.assertRaisesRegex(ValueError, "subject"):
            STORE.prepare_handoff(payload(report_type="stock") | {"subject": None})

    def test_structured_trigger_is_validated(self):
        item = payload()
        item["next_triggers"] = [{"id": "T1", "condition": "放量突破", "status": "pending"}]
        self.assertEqual(STORE.validate_handoff(item), [])
        item["next_triggers"][0]["status"] = "maybe"
        self.assertTrue(any("status" in error for error in STORE.validate_handoff(item)))

    def test_optional_handoff_status_is_validated(self):
        item = payload() | {"status": "partial"}
        self.assertEqual(STORE.validate_handoff(item), [])
        item["status"] = "unknown"
        self.assertTrue(any("status" in error for error in STORE.validate_handoff(item)))

    def test_latest_skips_corrupt_and_uses_weekday_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            STORE.atomic_write(STORE.prepare_handoff(payload(), "7.0.0"), root)
            (root / "handoff-20260905-daily.json").write_text("not-json", encoding="utf-8")
            latest = STORE.select_latest(root, within_trading_days=2, reference=date(2026, 9, 7))
            self.assertEqual(latest["handoff"]["trading_date"], "2026-09-04")
            self.assertEqual(latest["calendar_precision"], "holiday_calendar")

    def test_holiday_calendar_skips_exchange_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before_holiday = payload(as_of="2026-02-13 15:00 +08:00")
            STORE.atomic_write(STORE.prepare_handoff(before_holiday, "7.1.0"), root)
            latest = STORE.select_latest(root, within_trading_days=1, reference=date(2026, 2, 23))
            self.assertEqual(latest["calendar_precision"], "holiday_calendar")
            self.assertEqual(latest["handoff"]["trading_date"], "2026-02-13")

    def test_file_date_window_extends_acceptance_within_ten_days(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older = payload(as_of="2026-09-03 15:00 +08:00")
            STORE.atomic_write(STORE.prepare_handoff(older, "7.0.0"), root)
            # reference=周一 9/7、within=1：工作日窗口只有 9/7，9/3 只能靠文件日期窗口（≤10 自然日）入选
            latest = STORE.select_latest(
                root, within_trading_days=1, reference=date(2026, 9, 7),
                calendar_path=str(root / "missing-calendar.json"),
            )
            self.assertIsNotNone(latest)
            self.assertEqual(latest["handoff"]["trading_date"], "2026-09-03")

    def test_file_date_window_rejects_beyond_ten_day_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stale = payload(as_of="2026-08-20 15:00 +08:00")
            STORE.atomic_write(STORE.prepare_handoff(stale, "7.0.0"), root)
            latest = STORE.select_latest(root, within_trading_days=3, reference=date(2026, 9, 7))
            self.assertIsNone(latest)

    def test_calendar_provides_precise_window_and_excludes_holidays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calendar = Path(temporary) / "calendar.json"
            calendar.write_text(json.dumps({
                "trading_days": ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-07"],
            }), encoding="utf-8")
            STORE.atomic_write(STORE.prepare_handoff(payload(as_of="2026-09-04 15:00 +08:00"), "7.0.0"), root)
            in_window = payload(as_of="2026-09-03 15:00 +08:00")
            STORE.atomic_write(STORE.prepare_handoff(in_window, "7.0.0"), root)
            latest = STORE.select_latest(
                root, within_trading_days=3, reference=date(2026, 9, 7), calendar_path=str(calendar),
            )
            self.assertEqual(latest["calendar_precision"], "calendar")
            self.assertIsNone(latest["warning"])
            self.assertEqual(latest["handoff"]["trading_date"], "2026-09-03")
