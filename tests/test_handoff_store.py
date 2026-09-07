import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "handoff_store.py"
SPEC = importlib.util.spec_from_file_location("handoff_store", MODULE)
STORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STORE)


def payload(as_of="2026-09-04 15:00 +08:00", report_type="daily"):
    return {
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


class HandoffStoreTest(unittest.TestCase):
    def test_prepare_and_atomic_write(self):
        prepared = STORE.prepare_handoff(payload(), model_version="7.0.0")
        with tempfile.TemporaryDirectory() as temporary:
            path = STORE.atomic_write(prepared, Path(temporary))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], "1.0")
            self.assertEqual(saved["trading_date"], "2026-09-04")
            self.assertEqual(saved["model_version"], "7.0.0")

    def test_invalid_payload_is_rejected(self):
        bad = payload()
        bad["coverage"] = "很多"
        with self.assertRaisesRegex(ValueError, "coverage"):
            STORE.prepare_handoff(bad)

    def test_latest_skips_corrupt_and_uses_weekday_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            STORE.atomic_write(STORE.prepare_handoff(payload(), "7.0.0"), root)
            (root / "handoff-20260905-daily.json").write_text("not-json", encoding="utf-8")
            latest = STORE.select_latest(root, within_trading_days=2, reference=date(2026, 9, 7))
            self.assertEqual(latest["handoff"]["trading_date"], "2026-09-04")
            self.assertEqual(latest["calendar_precision"], "weekday_fallback")

    def test_file_date_window_extends_acceptance_within_ten_days(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older = payload(as_of="2026-09-03 15:00 +08:00")
            STORE.atomic_write(STORE.prepare_handoff(older, "7.0.0"), root)
            # reference=周一 9/7、within=1：工作日窗口只有 9/7，9/3 只能靠文件日期窗口（≤10 自然日）入选
            latest = STORE.select_latest(root, within_trading_days=1, reference=date(2026, 9, 7))
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

