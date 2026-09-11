# -*- coding: utf-8 -*-
"""Agent 工具经 UI 事件路由执行的端到端测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from tools.orchestration import execute_ui_event


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "artifacts"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def event(name, payload, artifact_ids=None):
    value = {"event": name, "timestamp": "2026-09-11T16:00:00+08:00", "payload": payload}
    if artifact_ids:
        value["context"] = {"artifact_ids": artifact_ids, "source": "e2e-test"}
    return value


class AgentToolEventE2E(unittest.TestCase):
    def test_save_load_evaluate_and_render_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            artifacts = base / "artifacts"
            reports = base / "reports"
            prediction = fixture("prediction.json")
            actual = fixture("close-actual.json")

            for payload in (prediction, actual):
                result = execute_ui_event(
                    event("save_artifact", {"artifact": payload}),
                    artifact_root=artifacts,
                    report_root=reports,
                )
                self.assertTrue(result["executed"])
                self.assertEqual(result["result"]["data_status"], "ok")

            loaded = execute_ui_event(
                event("load_artifact", {"snapshot_id": prediction["snapshot_id"]}),
                artifact_root=artifacts,
                report_root=reports,
            )
            self.assertEqual(loaded["result"]["payload"]["artifact_type"], "prediction")

            evaluated = execute_ui_event(
                event("evaluate_prediction", {
                    "prediction_snapshot_id": prediction["snapshot_id"],
                    "actual_snapshot_id": actual["snapshot_id"],
                }),
                artifact_root=artifacts,
                report_root=reports,
            )
            metrics = evaluated["result"]["payload"]
            self.assertEqual(metrics["actual_state"], "side")
            self.assertTrue(metrics["direction_hit"])
            self.assertAlmostEqual(metrics["brier_score"], 0.38)

            rendered = execute_ui_event(
                event("render_report", {
                    "snapshot_id": prediction["snapshot_id"],
                    "output_format": "markdown",
                    "output_name": "prediction-e2e",
                }),
                artifact_root=artifacts,
                report_root=reports,
            )
            output = Path(rendered["result"]["payload"]["path"])
            self.assertTrue(output.is_file())
            self.assertIn(prediction["snapshot_id"], output.read_text(encoding="utf-8"))

    def test_view_evidence_loads_only_requested_layer(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary) / "artifacts"
            stock = fixture("stock-diagnostic.json")
            save = execute_ui_event(event("save_artifact", {"artifact": stock}), artifact_root=artifacts)
            self.assertEqual(save["result"]["data_status"], "ok")
            viewed = execute_ui_event(
                event("view_evidence", {"layer_id": "L1"}, [stock["snapshot_id"]]),
                artifact_root=artifacts,
            )
            self.assertEqual(viewed["result"]["payload"]["layer_id"], "L1")
            self.assertEqual(viewed["result"]["payload"]["evidence"], "S2")

    def test_analysis_event_returns_skill_dispatch_without_fake_execution(self):
        routed = execute_ui_event(event("diagnose_stock", {"symbol": "300308"}))
        self.assertFalse(routed["executed"])
        self.assertEqual(routed["result"]["payload"]["target_skill"], "stock-analysis")


if __name__ == "__main__":
    unittest.main()
