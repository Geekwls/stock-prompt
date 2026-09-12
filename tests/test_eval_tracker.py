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


_MODULE_TMP = None
_PREV_ARTIFACT_DIR = None


def setUpModule():
    global _MODULE_TMP, _PREV_ARTIFACT_DIR
    _MODULE_TMP = tempfile.TemporaryDirectory()
    _PREV_ARTIFACT_DIR = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
    os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(_MODULE_TMP.name) / "artifacts")


def tearDownModule():
    global _MODULE_TMP, _PREV_ARTIFACT_DIR
    if _PREV_ARTIFACT_DIR is None:
        os.environ.pop("STOCK_PROMPT_ARTIFACT_DIR", None)
    else:
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = _PREV_ARTIFACT_DIR
    if _MODULE_TMP:
        _MODULE_TMP.cleanup()


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

    def test_default_ledger_with_stock_prompt_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["STOCK_PROMPT_HOME"] = temporary
            os.environ.pop("STOCK_PROMPT_EVAL_DIR", None)
            module = load_fresh()
            ledger = module.resolve_ledger()
            self.assertEqual(Path(ledger), Path(temporary) / "eval" / "predictions.jsonl")

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
                opportunity=78, top_sector="半导体", top_sectors="半导体, 低空经济",
                r1=3850.0, s1=3800.0, ledger=ledger,
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
            self.assertEqual(lines[0]["revision"], 1)
            self.assertEqual(lines[0]["market_phase"], "preopen")
            self.assertEqual(lines[0]["top_sectors"], ["半导体", "低空经济"])
            self.assertEqual(lines[1]["actual_state"], "up")

            report = argparse.Namespace(window=20, ledger=ledger)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                TRACKER.cmd_report(report)
            output = buffer.getvalue()
            self.assertIn("Brier Score", output)
            self.assertIn("方向命中率", output)
            self.assertIn("点位有效率", output)


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
        args = argparse.Namespace(p_up=55, p_side=30, p_down=15)
        probs = TRACKER.parse_probs(args)
        self.assertEqual(sum(probs.values()), 100.0)

    def test_off_total_is_renormalized(self):
        args = argparse.Namespace(p_up=50, p_side=30, p_down=10)
        probs = TRACKER.parse_probs(args)
        self.assertAlmostEqual(sum(probs.values()), 100.0, places=6)

    def test_out_of_range_exits(self):
        args = argparse.Namespace(p_up=-5, p_side=60, p_down=45)
        with self.assertRaises(SystemExit):
            TRACKER.parse_probs(args)


class SectorMatchTest(unittest.TestCase):
    def test_substring_matches_both_directions(self):
        self.assertTrue(TRACKER.sector_match("半导体", ["半导体/算力硬件"]))
        self.assertTrue(TRACKER.sector_match("半导体/算力硬件", ["半导体"]))
        self.assertFalse(TRACKER.sector_match("农业", ["半导体/算力硬件"]))


class LedgerEdgeCasesTest(unittest.TestCase):
    def write_ledger(self, path, records):
        with open(path, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def test_same_date_last_write_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            self.write_ledger(ledger, [
                {"type": "prediction", "date": "2026-09-01", "probs": {"up": 50, "side": 30, "down": 20}},
                {"type": "prediction", "date": "2026-09-01", "probs": {"up": 60, "side": 30, "down": 10}},
                {"type": "result", "date": "2026-09-01", "actual_state": "up"},
            ])
            preds, results = TRACKER.load_ledger(ledger)
            self.assertEqual(list(preds), ["2026-09-01"])
            self.assertEqual(preds["2026-09-01"]["probs"]["up"], 60)
            self.assertEqual(results["2026-09-01"]["actual_state"], "up")

    def test_corrupt_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            with open(ledger, "w", encoding="utf-8") as stream:
                stream.write("not-json\n")
                stream.write(json.dumps({"type": "prediction", "date": "2026-09-02", "probs": {}}) + "\n")
            preds, _ = TRACKER.load_ledger(ledger)
            self.assertEqual(list(preds), ["2026-09-02"])

    def test_duplicate_prediction_requires_explicit_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            args = argparse.Namespace(
                date="2026-09-08", regime="S2", p_up=30, p_side=50, p_down=20,
                opportunity=50, top_sector="半导体", top_sectors="", r1=None, s1=None,
                ledger=ledger, market_phase="preopen", revise=False,
            )
            TRACKER.cmd_record(args)
            with self.assertRaises(SystemExit):
                TRACKER.cmd_record(args)
            args.revise = True
            args.revision_reason = "竞价前证据修正"
            TRACKER.cmd_record(args)
            rows = [json.loads(line) for line in Path(ledger).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["revision"] for row in rows], [1, 2])
            self.assertEqual(rows[1]["supersedes"], rows[0]["snapshot_id"])

    def test_prediction_cannot_be_written_after_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            Path(ledger).write_text(json.dumps({"type": "result", "date": "2026-09-08"}) + "\n", encoding="utf-8")
            args = argparse.Namespace(
                date="2026-09-08", regime="S2", p_up=30, p_side=50, p_down=20,
                opportunity=50, top_sector="", top_sectors="", r1=None, s1=None,
                ledger=ledger,
            )
            with self.assertRaises(SystemExit):
                TRACKER.cmd_record(args)

    def test_market_phases_are_evaluated_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            self.write_ledger(ledger, [
                {"type": "prediction", "date": "2026-09-08", "market_phase": "preopen", "probs": {"up": 30}},
                {"type": "prediction", "date": "2026-09-08", "market_phase": "auction", "probs": {"up": 60}},
            ])
            preopen, _ = TRACKER.load_ledger(ledger, market_phase="preopen")
            auction, _ = TRACKER.load_ledger(ledger, market_phase="auction")
            self.assertEqual(preopen["2026-09-08"]["probs"]["up"], 30)
            self.assertEqual(auction["2026-09-08"]["probs"]["up"], 60)


class ReportOutputTest(unittest.TestCase):
    def build_paired_ledger(self, path):
        Path(path).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
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
        ]), encoding="utf-8")

    def test_report_outputs_top3_metric_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            self.build_paired_ledger(ledger)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                TRACKER.cmd_report(argparse.Namespace(ledger=ledger, window=20))
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
            ledger = str(Path(temporary) / "predictions.jsonl")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                TRACKER.cmd_report(argparse.Namespace(ledger=ledger, window=20))
            self.assertIn("暂无配对完成", buffer.getvalue())


class DailyScoresLedgerTest(unittest.TestCase):
    def test_load_daily_ledger_normalizes_legacy_state_suffix(self):
        with tempfile.TemporaryDirectory() as temporary:
            daily = Path(temporary) / "daily_scores.jsonl"
            daily.write_text(json.dumps({
                "type": "daily_review", "date": "2026-09-04",
                "mainline_sector": "半导体", "mainline_state": "强化期",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            records = TRACKER.load_daily_ledger(str(daily))
            self.assertEqual(records[0]["mainline_state"], "强化")

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
