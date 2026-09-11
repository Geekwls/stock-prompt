# -*- coding: utf-8 -*-
"""MarketGraph MCP 四个上下文型工具的单元测试集。"""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp" / "marketgraph-mcp" / "server.py"
SPEC = importlib.util.spec_from_file_location("marketgraph_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class MCPContextToolsTest(unittest.TestCase):
    def setUp(self):
        SERVER.CACHE_STORE.clear()
        SERVER._HOST_FAILURE_STATE.clear()
        SERVER._HOST_LAST_REQUEST.clear()
        self._sleep_patch = patch.object(SERVER.time, "sleep")
        self.sleep_mock = self._sleep_patch.start()

    def tearDown(self):
        self._sleep_patch.stop()
        SERVER.CACHE_STORE.clear()
        SERVER._HOST_FAILURE_STATE.clear()
        SERVER._HOST_LAST_REQUEST.clear()

    def test_context_tools_in_available_tools(self):
        """验证上下文和研究闭环工具已声明，且工具总数为 21。"""
        tools = SERVER.AVAILABLE_TOOLS
        self.assertEqual(len(tools), 21)
        tool_names = {t["name"] for t in tools}
        for expected in (
            "get_preopen_context",
            "get_close_review_context",
            "get_rotation_context",
            "get_stock_diagnostic_context",
            "save_artifact",
            "load_artifact",
            "evaluate_prediction",
            "render_report",
        ):
            self.assertIn(expected, tool_names)

    def test_preopen_context_aggregation_and_envelope(self):
        """测试 get_preopen_context 正常聚合核心指数、情绪、天梯、广度及板块。"""
        mock_idx = {
            "source": "P3_Tencent_Index_KLine", "data_status": "ok",
            "latest_date": "2026-09-10",
            "indices": {
                "SHCI": {"name": "上证指数", "close": 3950.0, "change_pct": "0.50%", "atr14": 35.0},
            },
        }
        mock_sent = {
            "source": "P3_Eastmoney_Market_Sentiment", "data_status": "ok",
            "date": "2026-09-10", "total_turnover_billion": 1950.0,
            "limit_up_count": 70, "blown_ratio": "32.0%", "max_limit_ladder": 4,
        }
        mock_ladder = {
            "source": "P3_Eastmoney_Limit_Up_Ladder", "data_status": "ok",
            "max_height": 4, "total_limit_up": 70,
            "ladder_distribution": {"4连板": 2, "3连板": 3},
            "highest_tier_stocks": [{"code": "600108", "name": "亚盛集团", "lbc": 4}],
        }
        mock_breadth = {
            "source": "P3_Eastmoney_Market_Breadth", "data_status": "ok",
            "red_ratio": "62.5%", "up_count": 3200, "down_count": 1800,
        }
        mock_quality = {"source": "P3_Eastmoney_Sector_Limit_Quality", "data_status": "ok", "seal_quality_score": 85.0}

        with patch.object(SERVER, "fetch_index_kline", return_value=mock_idx), \
             patch.object(SERVER, "fetch_market_sentiment", return_value=mock_sent), \
             patch.object(SERVER, "fetch_limit_up_ladder", return_value=mock_ladder), \
             patch.object(SERVER, "fetch_market_breadth", return_value=mock_breadth), \
             patch.object(SERVER, "fetch_sector_limit_quality", return_value=mock_quality):

            res = SERVER.fetch_preopen_context(indices=["SHCI"], sectors=["农业种植"])

            self.assertEqual(res["data_status"], "ok")
            self.assertEqual(res["source"], "P3_MarketGraph_Preopen")
            self.assertEqual(res["source_family"], "MarketGraph_Aggregator")
            self.assertEqual(res["data_date"], "2026-09-10")
            self.assertIn("indices", res["payload"])
            self.assertIn("sentiment", res["payload"])
            self.assertIn("ladder_summary", res["payload"])
            self.assertIn("breadth", res["payload"])
            self.assertIn("sectors_preview", res["payload"])
            self.assertEqual(res["missing"], [])

    def test_close_review_context_aggregation_and_conflict(self):
        """测试 get_close_review_context 聚合及指数涨红盘率低的冲突判定。"""
        mock_idx = {
            "source": "P3_Tencent_Index_KLine", "data_status": "ok",
            "latest_date": "2026-09-10",
            "indices": {"SHCI": {"name": "上证指数", "change_pct": "0.85%"}},
        }
        mock_sent = {"source": "P3_Eastmoney_Market_Sentiment", "data_status": "ok", "date": "2026-09-10"}
        mock_breadth = {"source": "P3_Eastmoney_Market_Breadth", "data_status": "ok", "red_ratio": "35.0%"}
        mock_fund = {
            "source": "P3_Eastmoney_Sector_Fund_Flow", "data_status": "ok",
            "rankings": [{"sector_name": "半导体", "net_inflow_million": 1200.0}],
        }
        mock_ladder = {"source": "P3_Eastmoney_Limit_Up_Ladder", "data_status": "ok"}
        mock_quality = {"source": "P3_Eastmoney_Sector_Limit_Quality", "data_status": "ok", "seal_quality_score": 78.0}

        with patch.object(SERVER, "fetch_index_kline", return_value=mock_idx), \
             patch.object(SERVER, "fetch_market_sentiment", return_value=mock_sent), \
             patch.object(SERVER, "fetch_market_breadth", return_value=mock_breadth), \
             patch.object(SERVER, "fetch_sector_fund_flow", return_value=mock_fund), \
             patch.object(SERVER, "fetch_limit_up_ladder", return_value=mock_ladder), \
             patch.object(SERVER, "fetch_sector_limit_quality", return_value=mock_quality):

            res = SERVER.fetch_close_review_context(top_sectors_count=3)
            self.assertEqual(res["data_status"], "ok")
            self.assertEqual(res["source"], "P3_MarketGraph_Close_Review")
            self.assertTrue(any("二八分化" in c for c in res["conflicts"]))

    def test_rotation_context_aggregation(self):
        """测试 get_rotation_context 聚合资金、指数与广度趋势。"""
        mock_fund = {"source": "P3_Eastmoney_Sector_Fund_Flow", "data_status": "ok", "date": "2026-09-10"}
        mock_idx = {"source": "P3_Tencent_Index_KLine", "data_status": "ok", "latest_date": "2026-09-10"}
        mock_breadth = {"source": "P3_Eastmoney_Market_Breadth", "data_status": "ok"}

        with patch.object(SERVER, "fetch_sector_fund_flow", return_value=mock_fund), \
             patch.object(SERVER, "fetch_index_kline", return_value=mock_idx), \
             patch.object(SERVER, "fetch_market_breadth", return_value=mock_breadth):

            res = SERVER.fetch_rotation_context(days=5, sector_count=10)
            self.assertEqual(res["data_status"], "ok")
            self.assertEqual(res["source"], "P3_MarketGraph_Rotation")
            self.assertIn("sector_fund_flows", res["payload"])
            self.assertIn("index_trend", res["payload"])
            self.assertIn("breadth_trend", res["payload"])

    def test_stock_diagnostic_context_aggregation(self):
        """测试 get_stock_diagnostic_context 聚合个股八层诊断所需数据。"""
        mock_quote = {"source": "P3_Tencent_Public_Gateway", "data_status": "ok", "date": "2026-09-10", "current_price": 50.0}
        mock_kline = {"source": "P3_Tencent_Qfq_Kline", "data_status": "ok", "latest_kline_date": "2026-09-10", "valid_bars": 750}
        mock_quality = {"source": "P3_Eastmoney_Financial_Quality", "data_status": "ok", "roe": 18.5}
        mock_timeline = {"source": "P3_Eastmoney_Intraday_Timeline", "data_status": "ok"}
        mock_lhb = {"source": "P3_Eastmoney_Longhubang", "data_status": "ok"}
        mock_idx = {"source": "P3_Tencent_Index_KLine", "data_status": "ok"}

        with patch.object(SERVER, "fetch_stock_quote", return_value=mock_quote), \
             patch.object(SERVER, "fetch_stock_kline", return_value=mock_kline), \
             patch.object(SERVER, "fetch_company_quality", return_value=mock_quality), \
             patch.object(SERVER, "fetch_stock_timeline", return_value=mock_timeline), \
             patch.object(SERVER, "fetch_longhubang_detail", return_value=mock_lhb), \
             patch.object(SERVER, "fetch_index_kline", return_value=mock_idx):

            res = SERVER.fetch_stock_diagnostic_context("300308", benchmark="CSIALL")
            self.assertEqual(res["data_status"], "ok")
            self.assertEqual(res["source"], "P3_MarketGraph_Stock_Diagnostic")
            self.assertIn("quote", res["payload"])
            self.assertIn("kline_structure", res["payload"])
            self.assertIn("company_quality", res["payload"])
            self.assertIn("timeline", res["payload"])
            self.assertIn("longhubang", res["payload"])
            self.assertIn("benchmark_kline", res["payload"])

    def test_partial_failure_graceful_degradation(self):
        """测试子数据源部分故障时标记 partial 且记录 missing 列表。"""
        mock_idx = {"source": "P3_Tencent_Index_KLine", "data_status": "ok", "latest_date": "2026-09-10"}
        mock_sent = {"error": "网络超时", "data_status": "unavailable"}

        with patch.object(SERVER, "fetch_index_kline", return_value=mock_idx), \
             patch.object(SERVER, "fetch_market_sentiment", return_value=mock_sent), \
             patch.object(SERVER, "fetch_limit_up_ladder", side_effect=RuntimeError("connection broken")), \
             patch.object(SERVER, "fetch_market_breadth", return_value={"data_status": "ok"}):

            res = SERVER.fetch_preopen_context()
            self.assertEqual(res["data_status"], "partial")
            self.assertIn("indices", res["payload"])
            self.assertIn("sentiment", res["missing"])
            self.assertTrue(any("ladder" in m for m in res["missing"]))

    def test_all_failure_returns_unavailable(self):
        """测试全部子源失败时标记 unavailable。"""
        with patch.object(SERVER, "fetch_index_kline", side_effect=RuntimeError("down")), \
             patch.object(SERVER, "fetch_market_sentiment", side_effect=RuntimeError("down")), \
             patch.object(SERVER, "fetch_limit_up_ladder", side_effect=RuntimeError("down")), \
             patch.object(SERVER, "fetch_market_breadth", side_effect=RuntimeError("down")):

            res = SERVER.fetch_preopen_context()
            self.assertEqual(res["data_status"], "unavailable")
            self.assertEqual(res["payload"], {})
            self.assertEqual(len(res["missing"]), 4)

    def test_dispatch_parameter_validations(self):
        """测试通过 _dispatch_tool_call 入参校验被正确触发。"""
        # 1. stock_diagnostic_context 必须传非空 symbol
        err = SERVER._dispatch_tool_call("get_stock_diagnostic_context", {"symbol": ""})
        self.assertIn("symbol", err.get("error", ""))

        # 2. rotation_context days 越界
        err2 = SERVER._dispatch_tool_call("get_rotation_context", {"days": 15})
        self.assertIn("days", err2.get("error", ""))

        # 3. close_review_context top_sectors_count 越界
        err3 = SERVER._dispatch_tool_call("get_close_review_context", {"top_sectors_count": 0})
        self.assertIn("top_sectors_count", err3.get("error", ""))

        # 4. preopen_context indices 非数组
        err4 = SERVER._dispatch_tool_call("get_preopen_context", {"indices": "SHCI"})
        self.assertIn("indices", err4.get("error", ""))

    def test_handle_tool_call_envelope_integration(self):
        """测试 handle_tool_call 返回规范的 v2 信封结构。"""
        with patch.object(SERVER, "fetch_rotation_context", return_value={
            "source": "P3_MarketGraph_Rotation",
            "data_status": "ok",
            "data_date": "2026-09-10",
            "payload": {"test": 123},
            "missing": [],
            "conflicts": [],
        }):
            res = SERVER.handle_tool_call("get_rotation_context", {"days": 5})
            self.assertEqual(res["api_version"], "2.0")
            self.assertEqual(res["data_status"], "ok")
            self.assertEqual(res["source"], "P3_MarketGraph_Rotation")
            self.assertIn("payload", res["data"])


if __name__ == "__main__":
    unittest.main()
