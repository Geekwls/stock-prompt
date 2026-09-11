import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"
SPEC = importlib.util.spec_from_file_location("doctor", MODULE)
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


class DoctorTest(unittest.TestCase):
    def test_collect_status_reports_core_components(self):
        status = DOCTOR.collect_status()
        self.assertTrue(status["version_parity"]["ok"])
        self.assertEqual(status["skills"]["ready"], status["skills"]["total"])
        self.assertEqual(status["mcp"]["tool_count"], 21)
        self.assertIn("last_trading_day", status["calendar"])
