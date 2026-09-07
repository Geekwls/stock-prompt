import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "eval_tracker.py"
SPEC = importlib.util.spec_from_file_location("eval_tracker", MODULE_PATH)
TRACKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACKER)


def write_ledger(path, records):
    with open(path, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


class ZatrToStateTest(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(TRACKER.zatr_to_state(0.3), "up")
        self.assertEqual(TRACKER.zatr_to_state(1.5), "up")
        self.assertEqual(TRACKER.zatr_to_state(0.2999), "side")
        self.assertEqual(TRACKER.zatr_to_state(0.0), "side")
        self.assertEqual(TRACKER.zatr_to_state(-0.2999), "side")
        self.assertEqual(TRACKER.zatr_to_state(-0.3), "down")
        self.assertEqual(TRACKER.zatr_to_state(-1.2), "down")


class BrierTest(unittest.TestCase):
    def test_perfect_prediction_scores_zero(self):
        probs = {"up": 100.0, "side": 0.0, "down": 0.0}
        self.assertEqual(TRACKER.brier_multiclass(probs, "up"), 0.0)

    def test_uniform_prediction_scores_two_thirds(self):
        probs = {"up": 100 / 3, "side": 100 / 3, "down": 100 / 3}
        self.assertAlmostEqual(TRACKER.brier_multiclass(probs, "up"), 2 / 3, places=3)

    def test_confident_wrong_prediction_scores_higher(self):
        wrong = {"up": 90.0, "side": 5.0, "down": 5.0}
        right = {"up": 10.0, "side": 10.0, "down": 80.0}
        self.assertGreater(
            TRACKER.brier_multiclass(wrong, "down"),
            TRACKER.brier_multiclass(right, "down"),
        )


class ParseProbsTest(unittest.TestCase):
    def test_valid_probs_pass_through(self):
        args = SimpleNamespace(p_up=55, p_side=30, p_down=15)
        probs = TRACKER.parse_probs(args)
        self.assertEqual(sum(probs.values()), 100.0)

    def test_off_total_is_renormalized(self):
        args = SimpleNamespace(p_up=50, p_side=30, p_down=10)
        probs = TRACKER.parse_probs(args)
        self.assertAlmostEqual(sum(probs.values()), 100.0, places=6)

    def test_out_of_range_exits(self):
        args = SimpleNamespace(p_up=-5, p_side=60, p_down=45)
        with self.assertRaises(SystemExit):
            TRACKER.parse_probs(args)


class SectorMatchTest(unittest.TestCase):
    def test_substring_matches_both_directions(self):
        self.assertTrue(TRACKER.sector_match("半导体", ["半导体/算力硬件"]))
        self.assertTrue(TRACKER.sector_match("半导体/算力硬件", ["半导体"]))
        self.assertFalse(TRACKER.sector_match("农业", ["半导体/算力硬件"]))


class LedgerTest(unittest.TestCase):
    def test_roundtrip_and_last_write_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = os.path.join(temporary, "eval", "predictions.jsonl")
            first = {"type": "prediction", "date": "2026-09-01", "probs": {"up": 50, "side": 30, "down": 20}}
            second = {"type": "prediction", "date": "2026-09-01", "probs": {"up": 60, "side": 30, "down": 10}}
            result = {"type": "result", "date": "2026-09-01", "actual_state": "up"}
            TRACKER.append_record(ledger, first)
            TRACKER.append_record(ledger, second)
            TRACKER.append_record(ledger, result)

            preds, results = TRACKER.load_ledger(ledger)
            self.assertEqual(list(preds), ["2026-09-01"])
            self.assertEqual(preds["2026-09-01"]["probs"]["up"], 60)
            self.assertEqual(results["2026-09-01"]["actual_state"], "up")

    def test_corrupt_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = os.path.join(temporary, "predictions.jsonl")
            with open(ledger, "w", encoding="utf-8") as stream:
                stream.write("not-json\n")
                stream.write(json.dumps({"type": "prediction", "date": "2026-09-02", "probs": {}}) + "\n")
            preds, _ = TRACKER.load_ledger(ledger)
            self.assertEqual(list(preds), ["2026-09-02"])


class DefaultLedgerTest(unittest.TestCase):
    def test_repo_checkout_anchors_to_repo_root(self):
        expected = MODULE_PATH.parents[1] / "eval" / "predictions.jsonl"
        self.assertEqual(TRACKER.default_ledger(), expected)


class ReportTest(unittest.TestCase):
    def build_paired_ledger(self, path):
        write_ledger(path, [
            {
                "type": "prediction", "date": "2026-09-01", "regime": "S3",
                "probs": {"up": 60, "side": 30, "down": 10}, "opportunity": 78,
                "top_sector": "半导体", "top_sectors": ["半导体", "PCB", "低空经济"],
                "r1": 3860, "s1": 3800,
            },
            {
                "type": "result", "date": "2026-09-01", "z_atr": 0.62, "actual_state": "up",
                "top_sectors": ["半导体/算力", "农业", "化工"], "close": 3842, "high": 3855, "low": 3805,
            },
            {
                "type": "prediction", "date": "2026-09-02", "regime": "S2",
                "probs": {"up": 25, "side": 50, "down": 25}, "opportunity": 40,
                "top_sector": "农业",
            },
            {
                "type": "result", "date": "2026-09-02", "z_atr": 0.1, "actual_state": "side",
                "top_sectors": ["农业种植", "军工"],
            },
        ])

    def test_report_outputs_all_metric_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = os.path.join(temporary, "predictions.jsonl")
            self.build_paired_ledger(ledger)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                TRACKER.cmd_report(SimpleNamespace(ledger=ledger, window=20))
            output = buffer.getvalue()
            for fragment in (
                "Brier Score",
                "三态方向命中率",
                "主线 Top1 命中率",
                "主线 Top3>=1 命中率",
                "主线 Top3>=2 命中率",
                "点位有效率",
                "概率校准度",
            ):
                self.assertIn(fragment, output)

    def test_report_without_pairs_explains_ledger_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = os.path.join(temporary, "predictions.jsonl")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                TRACKER.cmd_report(SimpleNamespace(ledger=ledger, window=20))
            self.assertIn("暂无配对完成", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
