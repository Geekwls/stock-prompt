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

    def test_tools_schema_validity(self):
        tools = SERVER.AVAILABLE_TOOLS
        self.assertGreaterEqual(len(tools), 4)
        tool_names = {t["name"] for t in tools}
        self.assertIn("get_stock_quote", tool_names)
        self.assertIn("get_stock_kline", tool_names)
        self.assertIn("get_market_sentiment", tool_names)
        self.assertIn("get_limit_up_ladder", tool_names)
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

    @patch.object(SERVER, "http_get")
    def test_fetch_market_sentiment_parsing(self, mock_get):
        mock_get.return_value = 'v_s_sh000001="1~上证指数~000001~3850.20~+12.30~+0.32~120000~45000000";v_s_sz399001="1~深证成指~399001~11500.50~+25.10~+0.22~150000~55000000";'
        
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
            self.assertEqual(res["zt_count"], 2)
            self.assertEqual(res["zb_count"], 1)
            self.assertEqual(res["exact_break_rate"], "33.33%")
            self.assertEqual(res["max_ladder_height"], "3 连板")

    def test_unknown_tool_returns_error(self):
        res = SERVER.handle_tool_call("unknown_tool", {})
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
