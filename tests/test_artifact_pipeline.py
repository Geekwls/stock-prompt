"""端到端验证 v7.3.0 Artifact 双写管线的五项关键约束。"""

import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import eval_tracker as EVAL  # noqa: E402
import handoff_store as HANDOFF  # noqa: E402
from tools.artifacts import adapters  # noqa: E402
from tools.artifacts import store as ARTIFACTS  # noqa: E402
from tools.calculations.market import calculate_atr_state  # noqa: E402
from tools.calculations.metrics import calculate_multiclass_brier  # noqa: E402


def run(func, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        func(argparse.Namespace(**kwargs))
    return buffer.getvalue()


def record_args(**overrides):
    base = dict(
        date="2026-09-08", regime="S3", p_up=55, p_side=30, p_down=15,
        opportunity=78, top_sector="半导体", top_sectors="半导体,PCB",
        r1=None, s1=None, model_version="test", formula_version="prediction-v2",
        source_snapshot=None, market_phase="preopen", coverage_band=None,
        volatility_band=None, data_status=None, revise=False, revision_reason=None,
        ledger=None, e1=None, e2=None, e3=None, e4=None,
    )
    base.update(overrides)
    return base


def result_args(**overrides):
    base = dict(
        date="2026-09-08", z_atr=0.62, top_sectors="半导体,农业",
        close=3842.0, high=3855.0, low=3805.0, top1_sector_change=3.8,
        model_version="test", formula_version="prediction-v2", source_snapshot=None,
        error_reasons="", revise=False, revision_reason=None, ledger=None,
    )
    base.update(overrides)
    return base


def stock_handoff(subject_id, name):
    return {
        "report_type": "stock", "as_of": f"2026-09-08 16:00 +08:00",
        "source_count": 6, "coverage": "82%", "scored_weight": "80%",
        "confidence": "中", "market_regime": "N/A", "primary_sectors": ["半导体"],
        "watchlist": [subject_id], "risk_flags": ["质押偏高"],
        "next_triggers": [{"id": "TRG-1", "condition": "站稳MA5", "status": "pending",
                           "deadline": "2026-09-10T15:00:00+08:00"}],
        "subject": {"type": "stock", "id": subject_id, "name": name},
    }


class ArtifactPipelineE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.ledger = str(self.base / "predictions.jsonl")
        self._env = {
            "STOCK_PROMPT_ARTIFACT_DIR": os.environ.get("STOCK_PROMPT_ARTIFACT_DIR"),
            "STOCK_PROMPT_STATE_DIR": os.environ.get("STOCK_PROMPT_STATE_DIR"),
        }
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(self.base / "artifacts")
        os.environ["STOCK_PROMPT_STATE_DIR"] = str(self.base / "state")

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_preopen_not_overwritten_by_auction(self):
        """场景1：PREOPEN_V1 不可被竞价 Artifact 覆盖，auction 必须挂接独立 parent。"""
        output = run(EVAL.cmd_record, **record_args(ledger=self.ledger))
        self.assertIn("[ARTIFACT] 双写 prediction", output)
        run(EVAL.cmd_record, **record_args(ledger=self.ledger, market_phase="auction",
                                           p_up=70, p_side=20, p_down=10, opportunity=None))
        predictions = ARTIFACTS.select_artifacts(artifact_type="prediction")
        auctions = ARTIFACTS.select_artifacts(artifact_type="auction")
        self.assertEqual(len(predictions), 1)
        self.assertEqual(len(auctions), 1)
        self.assertEqual(auctions[0]["parent_snapshot_id"], predictions[0]["snapshot_id"])
        with self.assertRaises(FileExistsError):
            ARTIFACTS.save_artifact(predictions[0])  # 同 ID 不可覆盖

    def test_stock_diagnostics_isolated_by_subject(self):
        """场景2：同日不同股票的诊断 Artifact 互不串票。"""
        for subject_id, name in (("300308", "中际旭创"), ("600519", "贵州茅台")):
            payload = HANDOFF.prepare_handoff(stock_handoff(subject_id, name), "test")
            path = HANDOFF.atomic_write(payload, Path(os.environ["STOCK_PROMPT_STATE_DIR"]))
            self.assertTrue(path.name.endswith(f"-{subject_id}.json"))
            HANDOFF.dual_write_artifact(payload)
        first = ARTIFACTS.select_artifacts(artifact_type="stock_diagnostic", subject="300308")
        second = ARTIFACTS.select_artifacts(artifact_type="stock_diagnostic", subject="600519")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["snapshot_id"], second[0]["snapshot_id"])
        self.assertEqual(first[0]["subject"]["id"], "300308")
        self.assertEqual(second[0]["subject"]["id"], "600519")
        self.assertEqual(set(first[0]["layers"]), {f"L{i}" for i in range(1, 9)})
        self.assertEqual(first[0]["layers"]["L1"]["status"], "unavailable")

    def test_low_coverage_suppresses_precise_scores(self):
        """场景3：覆盖率不足时 Artifact 不得携带精确概率与机会分。"""
        output = run(EVAL.cmd_record, **record_args(ledger=self.ledger, coverage_band="insufficient"))
        self.assertIn("双写 prediction", output)
        artifact = ARTIFACTS.select_artifacts(artifact_type="prediction")[0]
        self.assertIsNone(artifact["probabilities"])
        self.assertIsNone(artifact["opportunity_score"])
        self.assertEqual(artifact["status"], "degraded")
        self.assertEqual(ARTIFACTS.validate_artifact(artifact), [])

    def test_medium_low_coverage_suppresses_precise_scores(self):
        """场景3b：50%–69% 覆盖率同样只能输出条件化 Artifact。"""
        payload = adapters.mirror_prediction_record({
            "date": "2026-09-08", "coverage": "69%", "coverage_band": "medium",
            "probs": {"up": 0.55, "side": 0.30, "down": 0.15},
            "opportunity": 78, "regime": "S3", "market_phase": "preopen",
        })
        self.assertIsNone(payload["probabilities"])
        self.assertIsNone(payload["opportunity_score"])
        self.assertEqual(payload["status"], "degraded")

    def test_artifact_failure_does_not_block_analysis(self):
        """场景4：Artifact 双写失败时台账照常写入且仅告警。"""
        with patch.object(adapters, "mirror_and_store", side_effect=RuntimeError("disk full")):
            output = run(EVAL.cmd_record, **record_args(ledger=self.ledger))
        self.assertIn("[WARN] Artifact 双写失败", output)
        with open(self.ledger, encoding="utf-8") as stream:
            lines = [json.loads(line) for line in stream if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["type"], "prediction")

    def test_old_and_new_paths_agree_on_metrics(self):
        """场景5：新旧路径的 ATR 三态、Brier 与机会分完全一致。"""
        run(EVAL.cmd_record, **record_args(ledger=self.ledger, opportunity=76))
        run(EVAL.cmd_result, **result_args(ledger=self.ledger))
        with open(self.ledger, encoding="utf-8") as stream:
            ledger_pred = json.loads(stream.readline())
        artifact_pred = ARTIFACTS.select_artifacts(artifact_type="prediction")[0]
        artifact_close = ARTIFACTS.select_artifacts(artifact_type="close_actual")[0]

        self.assertEqual(artifact_pred["probabilities"]["up"], ledger_pred["probs"]["up"])
        self.assertEqual(artifact_pred["opportunity_score"], ledger_pred["opportunity"])
        self.assertEqual(artifact_close["actual_state"], EVAL.zatr_to_state(0.62))
        self.assertEqual(
            calculate_atr_state(0.62, 0, 1)["value"],
            EVAL.zatr_to_state(0.62),
        )
        legacy_brier = EVAL.brier_multiclass(ledger_pred["probs"], "up")
        unified_brier = calculate_multiclass_brier(artifact_pred["probabilities"], "up")["value"]
        self.assertAlmostEqual(legacy_brier, unified_brier, places=10)
        self.assertEqual(ARTIFACTS.validate_artifact(artifact_close), [])


if __name__ == "__main__":
    unittest.main()
