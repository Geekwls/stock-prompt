import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp" / "marketgraph-mcp" / "server.py"
SPEC = importlib.util.spec_from_file_location("marketgraph_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class MarketGraphMCPServerTest(unittest.TestCase):
    def test_normalize_symbol(self):
        self.assertEqual(SERVER.normalize_symbol("600519"), "sh600519")
        self.assertEqual(SERVER.normalize_symbol("300308"), "sz300308")
        self.assertEqual(SERVER.normalize_symbol("000938"), "sz000938")
        self.assertEqual(SERVER.normalize_symbol("sh600519"), "sh600519")
        self.assertEqual(SERVER.normalize_symbol("300308.sz"), "sz300308")
        self.assertEqual(SERVER.normalize_symbol("600519.SH"), "sh600519")
        self.assertEqual(SERVER.normalize_symbol("830000"), "bj830000")

    @patch.object(SERVER, "http_get")
    def test_resolve_symbol_by_name(self, mock_get):
        mock_get.return_value = 'v_hint="sh~600519~贵州茅台~gzmt~GP-A";\n'
        res = SERVER.normalize_symbol("贵州茅台")
        self.assertEqual(res, "sh600519")

    def test_tools_schema_validity(self):
        tools = SERVER.AVAILABLE_TOOLS
        self.assertGreaterEqual(len(tools), 8)
        tool_names = {t["name"] for t in tools}
        self.assertIn("get_stock_quote", tool_names)
        self.assertIn("get_stock_kline", tool_names)
        self.assertIn("get_stock_timeline", tool_names)
        self.assertIn("get_market_sentiment", tool_names)
        self.assertIn("get_limit_up_ladder", tool_names)
        self.assertIn("get_sector_fund_flow", tool_names)
        self.assertIn("get_longhubang_detail", tool_names)
        self.assertIn("get_company_quality", tool_names)
        for t in tools:
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_cache_mechanism(self):
        SERVER.set_cached("test_key", {"val": 123}, ttl=2)
        self.assertEqual(SERVER.get_cached("test_key"), {"val": 123})
        SERVER.set_cached("test_expired", {"val": 456}, ttl=-1)
        self.assertIsNone(SERVER.get_cached("test_expired"))

    @patch.object(SERVER, "http_get")
    def test_fetch_stock_quote_parsing(self, mock_get):
        # 构造标准的腾讯行情返回模拟数组 (50项)
        mock_parts = ["0"] * 50
        mock_parts[0] = "51"
        mock_parts[1] = "中际旭创"
        mock_parts[2] = "300308"
        mock_parts[3] = "859.30"
        mock_parts[4] = "854.00"
        mock_parts[5] = "852.00"
        mock_parts[6] = "123456"
        mock_parts[30] = "20260903150000"
        mock_parts[32] = "+0.62"
        mock_parts[33] = "865.00"
        mock_parts[34] = "845.00"
        mock_parts[37] = "1050000.00"
        mock_parts[38] = "1.85"
        mock_parts[39] = "49.20"
        mock_parts[43] = "2.34"
        mock_parts[44] = "9500.00"
        mock_parts[45] = "10040.00"
        mock_parts[46] = "24.10"
        mock_raw = f'v_sz300308="{"~".join(mock_parts)}";\n'
        mock_get.return_value = mock_raw

        quote = SERVER.fetch_stock_quote("300308")
        self.assertEqual(quote["name"], "中际旭创")
        self.assertEqual(quote["price"], 859.30)
        self.assertEqual(quote["pe_ttm"], 49.20)
        self.assertEqual(quote["pb"], 24.10)
        self.assertEqual(quote["total_market_cap_billion"], 10040.00)
        self.assertEqual(quote["change_pct"], "+0.62%")

    @patch.object(SERVER, "http_get")
    def test_fetch_stock_kline_and_indicators(self, mock_get):
        # 构造连续 125 根日 K 线序列
        mock_bars = []
        base_price = 100.0
        for i in range(125):
            date_str = f"2026-01-{i+1:02d}" if i < 30 else f"2026-03-{i-29:02d}"
            p = base_price + i * 0.5
            mock_bars.append([date_str, f"{p:.2f}", f"{p+1:.2f}", f"{p+2:.2f}", f"{p-1:.2f}", "10000"])
        mock_resp = {
            "data": {
                "sz300308": {
                    "qfqday": mock_bars
                }
            }
        }
        mock_get.return_value = json.dumps(mock_resp)

        kline = SERVER.fetch_stock_kline("300308", count=120)
        self.assertEqual(kline["valid_bars"], 120)
        self.assertTrue(kline["hard_gate_passed"])
        self.assertIn("ma20", kline)
        self.assertIn("ma50", kline)
        self.assertIn("atr14", kline)
        self.assertIn("bias_ma20", kline)
        self.assertGreater(kline["atr14"], 0)
        self.assertEqual(kline["adjustment"], "qfq")

    @patch.object(SERVER, "http_get")
    def test_kline_rejects_unadjusted_fallback(self, mock_get):
        SERVER.CACHE_STORE.clear()
        mock_get.return_value = json.dumps({"data": {"sz300308": {"day": [["2026-09-01", "1", "1", "1", "1", "1"]]}}})
        res = SERVER.fetch_stock_kline("300308")
        self.assertEqual(res["data_status"], "unavailable")

    @patch.object(SERVER, "http_get")
    def test_fetch_stock_timeline_parsing(self, mock_get):
        mock_trends = [
            "2026-09-03 09:25,100.00,102.00,102.00,100.00,500,5100000.00,102.000",
            "2026-09-03 09:30,102.00,103.00,103.50,101.50,1000,10300000.00,102.500",
            "2026-09-03 15:00,103.00,105.00,105.00,103.00,2000,21000000.00,103.500",
        ]
        mock_resp = {
            "data": {
                "name": "测试股",
                "preClose": 100.0,
                "trends": mock_trends,
            }
        }
        mock_get.return_value = json.dumps(mock_resp)

        res = SERVER.fetch_stock_timeline("300308")
        self.assertEqual(res["name"], "测试股")
        self.assertEqual(res["latest_price"], 105.0)
        self.assertEqual(res["change_pct"], "+5.00%")
        self.assertEqual(res["morning_call_auction"]["auction_change_pct"], "+2.00%")
        self.assertEqual(res["intraday_strength_label"], "强势放量：全天站上分时均线上方运行")

    @patch.object(SERVER, "http_get")
    def test_fetch_market_sentiment_parsing(self, mock_get):
        mock_get.return_value = 'v_s_sh000001="1~上证指数~000001~3850.20~+12.30~+0.32~120000~45000000~0~45000000";v_s_sz399001="1~深证成指~399001~11500.50~+25.10~+0.22~150000~55000000~0~55000000";'
        
        mock_zt = {"data": {"pool": [{"c": "000001", "lbc": 3}, {"c": "000002", "lbc": 1}]}}
        mock_zb = {"data": {"pool": [{"c": "000003"}]}}
        mock_dt = {"data": {"pool": []}}

        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", side_effect=[MockResp(mock_zt), MockResp(mock_zb), MockResp(mock_dt)]):
            res = SERVER.fetch_market_sentiment("20260903")
            self.assertEqual(res.get("data_status"), "ok", res)
            self.assertEqual(res["zt_count"], 2)
            self.assertEqual(res["zb_count"], 1)
            self.assertEqual(res["exact_break_rate"], "33.33%")
        self.assertEqual(res["max_ladder_height"], "3 连板")

    @patch.object(SERVER, "http_get", side_effect=OSError("upstream unavailable"))
    def test_market_sentiment_marks_partial_data(self, mock_get):
        SERVER.CACHE_STORE.clear()
        with patch("urllib.request.urlopen", side_effect=OSError("upstream unavailable")):
            res = SERVER.fetch_market_sentiment("20260903")
        self.assertEqual(res["data_status"], "partial")
        self.assertNotIn("market_broad_status", res)

    @patch.object(SERVER, "http_get")
    def test_fetch_sector_fund_flow(self, mock_get):
        mock_sectors = [
            {"f12": "BK001", "f14": "半导体", "f3": 3.5, "f62": 2500000000.0, "f184": 5.2, "f204": "寒武纪", "f205": "688256"},
            {"f12": "BK002", "f14": "医药生物", "f3": -1.2, "f62": -1500000000.0, "f184": -3.1, "f204": "药明康德", "f205": "603259"},
        ]
        mock_get.return_value = json.dumps({"data": {"diff": mock_sectors}})
        res = SERVER.fetch_sector_fund_flow(count=5)
        self.assertEqual(res["total_sectors_tracked"], 2)
        self.assertEqual(res["top_inflow_sectors"][0]["name"], "半导体")
        self.assertEqual(res["top_inflow_sectors"][0]["net_inflow_billion"], "+25.00 亿")
        self.assertEqual(res["top_outflow_sectors"][0]["name"], "医药生物")

    def test_fetch_longhubang_detail_parsing(self):
        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        mock_buy = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 50000000, "SELL": 1000000, "NET": 49000000}]}}
        mock_sell = {"result": {"data": [{"OPERATEDEPT_NAME": "东方证券拉萨营业部", "BUY": 1000000, "SELL": 20000000, "NET": -19000000}]}}
        mock_sum = {"result": {"data": [{"SECURITY_NAME_ABBR": "思泉新材", "TRADE_DATE": "2026-09-03 00:00:00", "TOTAL_BUY": 100000000, "TOTAL_SELL": 50000000, "TOTAL_NET": 50000000}]}}

        with patch("urllib.request.urlopen", side_effect=[MockResp(mock_buy), MockResp(mock_sell), MockResp(mock_sum)]):
            res = SERVER.fetch_longhubang_detail(symbol="301489")
            self.assertEqual(res["name"], "思泉新材")
            self.assertEqual(res["top5_buyers"][0]["seat_type"], "机构专用")
            self.assertEqual(res["seat_quality_judgment"], "机构席位净买入")

    def test_fetch_company_quality_parsing(self):
        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        mock_fina = {"result": {"data": [{
            "SECURITY_NAME_ABBR": "思泉新材", "REPORT_DATE_NAME": "2026中报",
            "TOTALOPERATEREVE": 521000000, "TOTALOPERATEREVETZ": 34.95,
            "PARENTNETPROFIT": 33610000, "PARENTNETPROFITTZ": 10.17,
            "ROEJQ": 3.0, "XSMLL": 30.28, "ZCFZL": 34.5, "MGJYXJJE": 0.94
        }]}}
        mock_lift = {"result": {"data": [{"FREE_DATE": "2026-10-24", "CURRENT_FREE_SHARES": 2969.61, "TOTAL_RATIO": 0.2554, "FREE_SHARES_TYPE": "首发限售"}]}}
        mock_balance = {"result": {"data": [{"GOODWILL": 0, "TOTAL_EQUITY": 1123000000, "INVENTORY": 271280000}]}}

        with patch("urllib.request.urlopen", side_effect=[MockResp(mock_fina), MockResp(mock_lift), MockResp(mock_balance)]):
            res = SERVER.fetch_company_quality(symbol="301489")
            self.assertEqual(res["report_period"], "2026中报")
            self.assertEqual(res["financial_summary"]["revenue_billion"], "5.21 亿元")
            self.assertEqual(res["company_risk_level"], "待补充核验")
            self.assertTrue(res["audit_opinion_status"].startswith("N/A"))

    def test_unknown_tool_returns_error(self):
        res = SERVER.handle_tool_call("unknown_tool", {})
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
