import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import eval_tracker as EVAL  # noqa: E402


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_command(func, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        func(argparse.Namespace(**kwargs))
    return buffer.getvalue()


class ReplayTest(unittest.TestCase):
    def build_ledger(self, path):
        write_jsonl(path, [
            {"type": "prediction", "date": "2026-09-08", "market_phase": "preopen",
             "probs": {"up": 40, "side": 40, "down": 20}, "opportunity": 60, "revision": 1,
             "recorded_at": "2026-09-08T09:10:00+08:00"},
            {"type": "prediction", "date": "2026-09-08", "market_phase": "auction",
             "probs": {"up": 70, "side": 20, "down": 10}, "opportunity": 66, "revision": 1,
             "recorded_at": "2026-09-08T09:28:00+08:00"},
            {"type": "result", "date": "2026-09-08", "z_atr": 0.62, "actual_state": "up",
             "top_sectors": ["半导体"], "revision": 1},
        ])

    def test_replay_shows_phases_and_revision_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            self.build_ledger(ledger)
            output = run_command(EVAL.cmd_replay, date="2026-09-08", ledger=ledger)
            self.assertIn("推演化回放", output)
            self.assertIn("preopen r1", output)
            self.assertIn("auction r1", output)
            self.assertIn("收盘 实际", output)
            self.assertIn("竞价修订评价", output)
            self.assertIn("改对了", output)

    def test_replay_without_records_is_quiet(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            output = run_command(EVAL.cmd_replay, date="2026-09-08", ledger=ledger)
            self.assertIn("无任何台账记录", output)


class ValidateOpportunityTest(unittest.TestCase):
    def test_buckets_and_sector_change_stats(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            records = []
            for day, opportunity in (("2026-09-01", 82), ("2026-09-02", 55), ("2026-09-03", 30)):
                records.append({"type": "prediction", "date": day, "market_phase": "preopen",
                                "probs": {"up": 60, "side": 30, "down": 10},
                                "opportunity": opportunity, "top_sector": "半导体",
                                "revision": 1})
                records.append({"type": "result", "date": day, "z_atr": 0.5, "actual_state": "up",
                                "top_sectors": ["半导体"], "revision": 1,
                                "top1_sector_change": 4.0 if opportunity >= 75 else -1.0})
            write_jsonl(ledger, records)
            output = run_command(EVAL.cmd_report, ledger=ledger, window=20, market_phase="preopen",
                                 validate_opportunity=True, all_versions=False,
                                 filter_version=None, model_version=None)
            self.assertIn("机会分有效性验证", output)
            self.assertIn("高(>=75): n=1", output)
            self.assertIn("中(45-74): n=1", output)
            self.assertIn("低(<45): n=1", output)
            self.assertIn("第一主线均涨幅 +4.00%", output)


class EvidenceClusterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(self._tmp.name) / "artifacts")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("STOCK_PROMPT_ARTIFACT_DIR", None)
        else:
            os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = self._prev
        self._tmp.cleanup()

    def test_record_stores_and_report_reads_stances(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            args = argparse.Namespace(
                date="2026-09-08", regime="S3", p_up=60, p_side=30, p_down=10,
                opportunity=70, top_sector="半导体", top_sectors="半导体",
                r1=None, s1=None, model_version="test", formula_version="prediction-v2",
                source_snapshot=None, market_phase="preopen", coverage_band=None,
                volatility_band=None, data_status=None, revise=False, revision_reason=None,
                ledger=ledger, e1="偏多", e2="中性", e3="强偏多", e4="偏空",
            )
            run_command(EVAL.cmd_record, **vars(args))
            with open(ledger, encoding="utf-8") as stream:
                stored = json.loads(stream.readline())
            self.assertEqual(stored["evidence_clusters"], {"E1": "偏多", "E2": "中性", "E3": "强偏多", "E4": "偏空"})

            with open(ledger, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"type": "result", "date": "2026-09-08", "z_atr": 0.5,
                                         "actual_state": "up", "top_sectors": ["半导体"], "revision": 1,
                                         "model_version": "test"}, ensure_ascii=False) + "\n")
            output = run_command(EVAL.cmd_report, ledger=ledger, window=20, market_phase="preopen",
                                 validate_opportunity=False, all_versions=False,
                                 filter_version="test", model_version=None)
            self.assertIn("证据簇判读力", output)
            self.assertIn("E1 看多: 1/1", output)
            self.assertIn("E4 看空: 0/1", output)


class MainlineLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(self._tmp.name) / "artifacts")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("STOCK_PROMPT_ARTIFACT_DIR", None)
        else:
            os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = self._prev
        self._tmp.cleanup()

    def test_record_daily_mainline_and_transition_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            daily = str(Path(temporary) / "daily_scores.jsonl")
            states = [("2026-09-01", "半导体", "启动"), ("2026-09-02", "半导体", "启动"),
                      ("2026-09-03", "半导体", "强化"), ("2026-09-04", "半导体", "分歧"),
                      ("2026-09-05", "农业", "启动")]
            for day, sector, state in states:
                args = argparse.Namespace(
                    date=day, up_ratio=None, premium=None, promotion=None, break_rate=None,
                    volume_dev=None, sentiment_total=None, capital_continuity=None,
                    opportunity=None, top_sector="", mainline_sector=sector,
                    mainline_state=state, sei=None, model_version="test",
                    formula_version="daily-v2", source_snapshot=None, daily_ledger=daily,
                )
                run_command(EVAL.cmd_record_daily, **vars(args))
            output = run_command(EVAL.cmd_report_mainline, daily_ledger=daily, window=120,
                                 all_versions=False, filter_version="test", model_version=None)
            self.assertIn("主线状态机台账", output)
            self.assertIn("主线切换次数: 1", output)
            self.assertIn("启动 -> 强化: 1 次", output)
            self.assertIn("强化 -> 分歧: 1 次", output)
            self.assertIn("样本 5 日 < 30 日", output)

    def test_mainline_state_requires_sector(self):
        args = argparse.Namespace(
            date="2026-09-01", up_ratio=None, premium=None, promotion=None, break_rate=None,
            volume_dev=None, sentiment_total=None, capital_continuity=None, opportunity=None,
            top_sector="", mainline_sector="", mainline_state="强化", sei=None,
            model_version="test", formula_version="daily-v2", source_snapshot=None,
            daily_ledger="unused.jsonl",
        )
        with self.assertRaisesRegex(SystemExit, "mainline-state"):
            EVAL.cmd_record_daily(args)


class SentimentExtremesTest(unittest.TestCase):
    def test_extremes_join_forward_z_atr(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            daily = str(Path(temporary) / "daily_scores.jsonl")
            write_jsonl(ledger, [
                {"type": "result", "date": "2026-09-02", "z_atr": 0.6, "actual_state": "up", "revision": 1},
                {"type": "result", "date": "2026-09-03", "z_atr": 0.4, "actual_state": "up", "revision": 1},
            ])
            write_jsonl(daily, [
                {"type": "daily_review", "date": "2026-09-01", "sentiment_total": 22.0},
                {"type": "daily_review", "date": "2026-09-02", "sentiment_total": 60.0},
            ])
            output = run_command(EVAL.cmd_report_daily, daily_ledger=daily, window=60,
                                 all_versions=False, filter_version=None, model_version=None,
                                 extremes=True, ledger=ledger)
            self.assertIn("情绪极值与后续表现", output)
            self.assertIn("冰点(<=30): 1 次", output)
            self.assertIn("后续均值Z_ATR +0.50", output)


class ThesisDueAndDoctorTest(unittest.TestCase):
    def test_collect_due_filters_pending_with_deadline(self):
        import thesis_store as THESIS

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "300308.json").write_text(json.dumps({
                "stock_code": "300308", "stock_name": "中际旭创",
                "next_triggers": [
                    {"id": "TRG-1", "condition": "站稳MA5", "status": "pending",
                     "deadline": "2026-09-10T15:00:00+08:00"},
                    {"id": "TRG-2", "condition": "已确认", "status": "confirmed",
                     "deadline": "2026-09-09T15:00:00+08:00"},
                    {"id": "TRG-3", "condition": "无期限", "status": "pending"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            due = THESIS.collect_due(root, date(2026, 9, 8), 3)
            self.assertEqual([item["trigger_id"] for item in due], ["TRG-1"])
            self.assertEqual(due[0]["stock_code"], "300308")

    def test_doctor_reports_thesis_summary(self):
        os.environ["STOCK_PROMPT_STATE_HOME"] = tempfile.mkdtemp()
        self.addCleanup(os.environ.pop, "STOCK_PROMPT_STATE_HOME", None)
        import doctor

        base = Path(os.environ["STOCK_PROMPT_STATE_HOME"]) / "theses"
        base.mkdir()
        (base / "600519.json").write_text(json.dumps({
            "stock_code": "600519",
            "next_triggers": [{"id": "T", "condition": "x", "status": "pending",
                               "deadline": (date.today() + timedelta(days=1)).isoformat()}],
        }, ensure_ascii=False), encoding="utf-8")
        status = doctor.collect_status()
        self.assertEqual(status["theses"]["total"], 1)
        self.assertEqual(status["theses"]["pending_triggers"], 1)
        self.assertEqual(status["theses"]["due_soon"], 1)


class WeeklyDigestTest(unittest.TestCase):
    def test_digest_aggregates_all_sections(self):
        import weekly_digest as WEEKLY

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            ledger = str(base / "predictions.jsonl")
            daily = str(base / "daily_scores.jsonl")
            state_dir = base / "state"
            state_dir.mkdir()
            write_jsonl(ledger, [
                {"type": "prediction", "date": "2026-09-07", "market_phase": "preopen",
                 "probs": {"up": 60, "side": 30, "down": 10}, "opportunity": 70,
                 "top_sector": "半导体", "revision": 1},
                {"type": "result", "date": "2026-09-07", "z_atr": 0.5, "actual_state": "up",
                 "top_sectors": ["半导体"], "revision": 1},
            ])
            write_jsonl(daily, [
                {"type": "daily_review", "date": "2026-09-07", "sentiment_total": 62.0,
                 "opportunity": 66.0, "capital_continuity": 71.0,
                 "mainline_sector": "半导体", "mainline_state": "强化", "sei": 25.0},
            ])
            (state_dir / "handoff-20260907-daily.json").write_text(json.dumps({
                "report_type": "daily", "next_triggers": [
                    {"id": "TRG-A", "condition": "放量突破", "status": "pending",
                     "deadline": "2026-09-09T15:00:00+08:00"},
                    {"id": "TRG-B", "condition": "跌破MA5", "status": "failed"},
                ],
            }, ensure_ascii=False), encoding="utf-8")

            args = argparse.Namespace(as_of="2026-09-08", days=7, ledger=ledger,
                                      daily_ledger=daily, state_dir=str(state_dir))
            digest = WEEKLY.build_digest(args)
            self.assertIn("周度复盘摘要", digest)
            self.assertIn("盘前预测质量", digest)
            self.assertIn("方向命中 1/1", digest)
            self.assertIn("每日评分与主线状态", digest)
            self.assertIn("半导体【强化】", digest)
            self.assertIn("触发器核验", digest)
            self.assertIn("pending=1", digest)
            self.assertIn("failed=1", digest)
            self.assertIn("TRG-A", digest)


class MissesTest(unittest.TestCase):
    def test_misses_sorts_by_brier_and_renders_cards(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            write_jsonl(ledger, [
                {"type": "prediction", "date": "2026-09-01", "market_phase": "preopen",
                 "probs": {"up": 90, "side": 10, "down": 0}, "opportunity": 80,
                 "top_sector": "半导体", "revision": 1, "regime": "S3", "coverage_band": "high"},
                {"type": "result", "date": "2026-09-01", "z_atr": 0.8, "actual_state": "up",
                 "top_sectors": ["半导体"], "revision": 1},
                {"type": "prediction", "date": "2026-09-02", "market_phase": "preopen",
                 "probs": {"up": 80, "side": 15, "down": 5}, "opportunity": 75,
                 "top_sector": "消费电子", "revision": 1, "regime": "S2", "coverage_band": "high",
                 "volatility_band": "normal", "data_status": "ok"},
                {"type": "result", "date": "2026-09-02", "z_atr": -1.2, "actual_state": "down",
                 "top_sectors": ["煤炭", "石油"], "revision": 1,
                 "error_reasons": ["macro_event", "fake_breakout"]},
                {"type": "prediction", "date": "2026-09-03", "market_phase": "preopen",
                 "probs": {"up": 30, "side": 50, "down": 20}, "opportunity": 50,
                 "top_sector": "算力", "revision": 1, "regime": "S1"},
                {"type": "prediction", "date": "2026-09-03", "market_phase": "auction",
                 "probs": {"up": 10, "side": 30, "down": 60}, "opportunity": 35,
                 "top_sector": "算力", "revision": 1},
                {"type": "result", "date": "2026-09-03", "z_atr": -0.7, "actual_state": "down",
                 "top_sectors": ["贵金属"], "revision": 1, "error_reasons": ["liquidity_drain"]},
            ])

            output = run_command(EVAL.cmd_misses, ledger=ledger, top=2, min_brier=0.0,
                                 market_phase="preopen", all_versions=False,
                                 filter_version=None, model_version=None)
            self.assertIn("错案复盘集", output)
            self.assertIn("Top 2", output)
            self.assertIn("【错案 #1 | 2026-09-02", output)
            self.assertIn("消费电子", output)
            self.assertIn("macro_event, fake_breakout", output)
            self.assertIn("Regime S2", output)
            self.assertIn("【错案 #2 | 2026-09-03", output)
            self.assertIn("改对了", output)

    def test_misses_empty_when_no_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            output = run_command(EVAL.cmd_misses, ledger=ledger, top=5, min_brier=0.0,
                                 market_phase="preopen", all_versions=False,
                                 filter_version=None, model_version=None)
            self.assertIn("无成对的预测与收盘实际记录", output)


if __name__ == "__main__":
    unittest.main()
