# -*- coding: utf-8 -*-
"""UI 事件协议与调度器单元测试。"""

import unittest
from tools.orchestration import route_ui_event, validate_ui_event


class UIEventRouterTest(unittest.TestCase):
    def test_deterministic_events_do_not_require_llm(self):
        """测试确定性事件（查看证据、渲染战报、校准视图）不需要 LLM 介入。"""
        for event_name in ("view_evidence", "view_calibration", "retry_data", "render_report"):
            event = {
                "event": event_name,
                "timestamp": "2026-09-11T10:00:00+08:00",
                "payload": {"report_type": "prediction"},
            }
            res = route_ui_event(event)
            self.assertTrue(res["valid"])
            self.assertFalse(res["requires_llm"])
            self.assertIsNone(res["target_skill"])
            self.assertEqual(res["action"], f"execute_tool_{event_name}")

    def test_analysis_events_route_to_target_skills(self):
        """测试投研分析事件定向分发给对应专业 Skill。"""
        cases = [
            ("start_preopen", {}, "market-prediction"),
            ("update_auction", {}, "market-prediction"),
            ("run_close_review", {}, "daily-review"),
            ("run_rotation", {}, "sector-rotation"),
            ("diagnose_stock", {"symbol": "300308"}, "stock-analysis"),
        ]
        for event_name, payload, expected_skill in cases:
            event = {
                "event": event_name,
                "timestamp": "2026-09-11T10:00:00+08:00",
                "payload": payload,
            }
            res = route_ui_event(event)
            self.assertTrue(res["valid"])
            self.assertTrue(res["requires_llm"])
            self.assertEqual(res["target_skill"], expected_skill)

    def test_invalid_event_rejection(self):
        """测试未知事件与缺失字段被拒绝。"""
        # 1. 未知事件
        res1 = route_ui_event({"event": "buy_stock_now", "timestamp": "2026-09-11"})
        self.assertFalse(res1["valid"])
        self.assertIn("未知事件类型", res1["errors"][0])

        # 2. 个股诊断缺失 symbol
        res2 = route_ui_event({"event": "diagnose_stock", "timestamp": "2026-09-11", "payload": {}})
        self.assertFalse(res2["valid"])
        self.assertTrue(any("symbol" in err for err in res2["errors"]))


if __name__ == "__main__":
    unittest.main()
