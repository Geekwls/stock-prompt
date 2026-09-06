import importlib.util
import json
import unittest
import urllib.parse
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp" / "marketgraph-mcp" / "server.py"
SPEC = importlib.util.spec_from_file_location("marketgraph_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class MarketGraphMCPServerTest(unittest.TestCase):
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
        self.assertGreaterEqual(len(tools), 12)
        tool_names = {t["name"] for t in tools}
        self.assertIn("get_stock_quote", tool_names)
        self.assertIn("get_stock_kline", tool_names)
        self.assertIn("get_stock_timeline", tool_names)
        self.assertIn("get_market_sentiment", tool_names)
        self.assertIn("get_limit_up_ladder", tool_names)
        self.assertIn("get_index_kline", tool_names)
        self.assertIn("get_market_breadth", tool_names)
        self.assertIn("get_sector_fund_flow", tool_names)
        self.assertIn("get_sector_kline", tool_names)
        self.assertIn("get_basket_index", tool_names)
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
        # 构造连续 760 根日 K 线序列 (包含3年完整大周期)
        mock_bars = []
        base_price = 100.0
        for i in range(760):
            year = 2023 + (i // 250)
            day_in_year = i % 250
            month = (day_in_year // 22) + 1
            day = (day_in_year % 22) + 1
            date_str = f"{year}-{month:02d}-{day:02d}"
            p = base_price + i * 0.2
            mock_bars.append([date_str, f"{p:.2f}", f"{p+1:.2f}", f"{p+2:.2f}", f"{p-1:.2f}", "10000"])
        mock_resp = {
            "data": {
                "sz300308": {
                    "qfqday": mock_bars
                }
            }
        }
        mock_get.return_value = json.dumps(mock_resp)

        kline = SERVER.fetch_stock_kline("300308", count=750)
        self.assertEqual(kline["valid_bars"], 750)
        self.assertTrue(kline["hard_gate_passed"])
        self.assertTrue(kline["compact_mode"])
        self.assertEqual(len(kline["recent_30_bars"]), 30)
        self.assertNotIn("bars", kline)
        self.assertIn("ma20", kline)
        self.assertIn("ma50", kline)
        self.assertIsNotNone(kline["ma120_half_year"])
        self.assertIsNotNone(kline["ma250_year_line"])
        self.assertIsNotNone(kline["ma500_2year_line"])
        self.assertIn("atr14", kline)
        self.assertIn("bias_ma20", kline)
        self.assertIn("bias_ma250_year", kline)
        self.assertIn("bias_ma500_2year", kline)
        self.assertIn("high_3y", kline)
        self.assertIn("low_3y", kline)
        self.assertIn("percentile_3y", kline)
        self.assertIn("weekly_timeframe", kline)
        self.assertGreaterEqual(kline["weekly_timeframe"]["total_weeks"], 100)
        self.assertIn("weekly_alignment", kline["weekly_timeframe"])
        self.assertIsNotNone(kline["weekly_timeframe"]["weekly_ma10"])
        self.assertIsNotNone(kline["weekly_timeframe"]["weekly_ma30"])
        self.assertGreater(kline["atr14"], 0)
        self.assertEqual(kline["adjustment"], "qfq")
        self.assertIn("wyckoff_multi_timeframe", kline)
        self.assertIn("macro_wyckoff_phase", kline["wyckoff_multi_timeframe"])
        self.assertIn("trading_range_60d", kline["wyckoff_multi_timeframe"])
        self.assertIn("summary", kline["wyckoff_multi_timeframe"])
        # 量能结构: 固定成交量 10000 => 量比 1.0, 量能分位 100
        self.assertEqual(kline["volume_ratio_20d"], 1.0)
        self.assertEqual(kline["volume_percentile_120d"], 100.0)

        # 测试 full 模式 (compact=False)
        SERVER.CACHE_STORE.clear()
        kline_full = SERVER.fetch_stock_kline("300308", count=750, compact=False)
        self.assertFalse(kline_full["compact_mode"])
        self.assertIn("bars", kline_full)
        self.assertEqual(len(kline_full["bars"]), 750)

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
        def fake_get(url, timeout=4, encoding="utf-8"):
            if "qt.gtimg.cn" in url:
                return 'v_s_sh000001="1~上证指数~000001~3850.20~+12.30~+0.32~120000~45000000~0~45000000";v_s_sz399001="1~深证成指~399001~11500.50~+25.10~+0.22~150000~55000000~0~55000000";'
            if "getTopicZTPool" in url:
                return json.dumps({"data": {"pool": [{"c": "000001", "lbc": 3}, {"c": "000002", "lbc": 1}]}})
            if "getTopicZBPool" in url:
                return json.dumps({"data": {"pool": [{"c": "000003"}]}})
            if "getTopicDTPool" in url:
                return json.dumps({"data": {"pool": []}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_get
        res = SERVER.fetch_market_sentiment()  # 当日路径走实时指数快照
        self.assertEqual(res.get("data_status"), "ok", res)
        self.assertEqual(res["zt_count"], 2)
        self.assertEqual(res["zb_count"], 1)
        self.assertEqual(res["exact_break_rate"], "33.33%")
        self.assertEqual(res["max_ladder_height"], "3 连板")

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_historical_uses_index_kline(self, mock_get):
        """历史日期: 涨跌幅主源为腾讯指数日K, 两市成交额来自东财指数日K"""
        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url:
                days = [
                    ["2026-09-02", "3920.00", "3950.00", "3960.00", "3910.00", "123000000"],
                    ["2026-09-03", "3955.00", "3986.00", "3990.00", "3950.00", "124000000"],
                ]
                return json.dumps({"data": {"sh000001": {"day": days}}})
            if "secid=1.000001" in url:
                klines = [
                    "2026-09-02,3920.00,3950.00,3960.00,3910.00,123000000,65000000000",
                    "2026-09-03,3955.00,3986.00,3990.00,3950.00,124000000,66000000000",
                ]
                return json.dumps({"data": {"klines": klines}})
            if "secid=0.399106" in url:
                klines = ["2026-09-03,2300.00,2310.00,2320.00,2290.00,99000000,70000000000"]
                return json.dumps({"data": {"klines": klines}})
            if "getTopicZTPool" in url:
                return json.dumps({"data": {"pool": [{"c": "000001", "lbc": 2}]}})
            if "getTopicZBPool" in url:
                return json.dumps({"data": {"pool": []}})
            if "getTopicDTPool" in url:
                return json.dumps({"data": {"pool": []}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_get
        res = SERVER.fetch_market_sentiment("2026-09-03")
        self.assertEqual(res.get("data_status"), "ok", res)
        self.assertEqual(res["sh_index_change"], "+0.91%")
        self.assertEqual(res["total_turnover_billion"], 1360.0)

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_historical_falls_back_to_em_kline(self, mock_get):
        """腾讯指数日K不可用时, 历史涨跌幅自动回退东财日K"""
        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url:
                raise OSError("tencent down")
            if "secid=1.000001" in url:
                klines = [
                    "2026-09-02,3920.00,3950.00,3960.00,3910.00,123000000,65000000000",
                    "2026-09-03,3955.00,3986.00,3990.00,3950.00,124000000,66000000000",
                ]
                return json.dumps({"data": {"klines": klines}})
            if "secid=0.399106" in url:
                return json.dumps({"data": {"klines": ["2026-09-03,2300.00,2310.00,2320.00,2290.00,99000000,70000000000"]}})
            if "getTopicZTPool" in url:
                return json.dumps({"data": {"pool": []}})
            if "getTopicZBPool" in url:
                return json.dumps({"data": {"pool": []}})
            if "getTopicDTPool" in url:
                return json.dumps({"data": {"pool": []}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_get
        res = SERVER.fetch_market_sentiment("2026-09-03")
        self.assertEqual(res.get("data_status"), "ok", res)
        self.assertEqual(res["sh_index_change"], "+0.91%")
        self.assertEqual(res["total_turnover_billion"], 1360.0)

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_historical_partial_without_em(self, mock_get):
        """东财日K不可用时成交额缺失 => partial 且不输出情绪结论, 但涨跌幅仍可由腾讯提供"""
        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url:
                days = [
                    ["2026-09-02", "3920.00", "3950.00", "3960.00", "3910.00", "123000000"],
                    ["2026-09-03", "3955.00", "3986.00", "3990.00", "3950.00", "124000000"],
                ]
                return json.dumps({"data": {"sh000001": {"day": days}}})
            if "getTopicZTPool" in url:
                return json.dumps({"data": {"pool": []}})
            if "getTopicZBPool" in url:
                return json.dumps({"data": {"pool": []}})
            if "getTopicDTPool" in url:
                return json.dumps({"data": {"pool": []}})
            raise OSError("em down")

        mock_get.side_effect = fake_get
        res = SERVER.fetch_market_sentiment("2026-09-03")
        self.assertEqual(res["data_status"], "partial")
        self.assertNotIn("market_broad_status", res)
        self.assertTrue(any("成交额" in s for s in res["unavailable_sources"]))

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_rejects_non_trading_date(self, mock_get):
        """非交易日的历史查询应显式 unavailable, 不得以零值伪装 ok"""
        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url:
                return json.dumps({"data": {"sh000001": {"day": [["2026-09-03", "3955.00", "3986.00", "3990.00", "3950.00", "124000000"]]}}})
            if "secid=1.000001" in url:
                return json.dumps({"data": {"klines": ["2026-09-03,3955.00,3986.00,3990.00,3950.00,124000000,66000000000"]}})
            raise OSError("no data")

        mock_get.side_effect = fake_get
        res = SERVER.fetch_market_sentiment("2026-01-01")  # 元旦休市, 永远非交易日且必为历史日期
        self.assertEqual(res["data_status"], "unavailable")
        self.assertIn("非交易日", res["error"])

    @patch.object(SERVER, "http_get", side_effect=OSError("upstream unavailable"))
    def test_market_sentiment_marks_partial_data(self, mock_get):
        res = SERVER.fetch_market_sentiment()  # 当日: 各上游失败 => partial, 不伪造情绪结论
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

    @patch.object(SERVER, "http_get")
    def test_fetch_longhubang_detail_parsing(self, mock_get):
        mock_buy = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 50000000, "SELL": 1000000, "NET": 49000000}]}}
        mock_sell = {"result": {"data": [{"OPERATEDEPT_NAME": "东方证券拉萨营业部", "BUY": 1000000, "SELL": 20000000, "NET": -19000000}]}}
        mock_sum = {"result": {"data": [{"SECURITY_NAME_ABBR": "思泉新材", "TRADE_DATE": "2026-09-03 00:00:00", "TOTAL_BUY": 100000000, "TOTAL_SELL": 50000000, "TOTAL_NET": 50000000}]}}
        mock_get.side_effect = [json.dumps(mock_buy), json.dumps(mock_sell), json.dumps(mock_sum)]

        res = SERVER.fetch_longhubang_detail(symbol="301489")
        self.assertEqual(res["name"], "思泉新材")
        self.assertEqual(res["top5_buyers"][0]["seat_type"], "机构专用")
        self.assertEqual(res["seat_quality_judgment"], "机构席位净买入")

    @patch.object(SERVER, "http_get")
    def test_fetch_company_quality_parsing(self, mock_get):
        mock_fina = {"result": {"data": [{
            "SECURITY_NAME_ABBR": "思泉新材", "REPORT_DATE_NAME": "2026中报",
            "TOTALOPERATEREVE": 521000000, "TOTALOPERATEREVETZ": 34.95,
            "PARENTNETPROFIT": 33610000, "PARENTNETPROFITTZ": 10.17,
            "ROEJQ": 3.0, "XSMLL": 30.28, "ZCFZL": 34.5, "MGJYXJJE": 0.94
        }]}}
        mock_lift = {"result": {"data": [{"FREE_DATE": "2026-10-24", "CURRENT_FREE_SHARES": 2969.61, "TOTAL_RATIO": 0.2554, "FREE_SHARES_TYPE": "首发限售"}]}}
        mock_balance = {"result": {"data": [{"GOODWILL": 0, "TOTAL_EQUITY": 1123000000, "INVENTORY": 271280000}]}}

        mock_get.side_effect = [json.dumps(mock_fina), json.dumps(mock_lift), json.dumps(mock_balance)]
        res = SERVER.fetch_company_quality(symbol="301489")
        self.assertEqual(res["report_period"], "2026中报")
        self.assertEqual(res["financial_summary"]["revenue_billion"], "5.21 亿元")
        self.assertEqual(res["company_risk_level"], "待补充核验")
        self.assertTrue(res["audit_opinion_status"].startswith("N/A"))

    def test_normalize_date_str(self):
        self.assertEqual(SERVER.normalize_date_str("20260904"), "2026-09-04")
        self.assertEqual(SERVER.normalize_date_str("2026-09-04"), "2026-09-04")
        self.assertEqual(SERVER.normalize_date_str("2026/09/04"), "2026-09-04")
        self.assertIsNone(SERVER.normalize_date_str("2026-9-4"))
        self.assertIsNone(SERVER.normalize_date_str("abc"))
        self.assertIsNone(SERVER.normalize_date_str(""))

    def test_resolve_index_keys(self):
        self.assertEqual(SERVER.resolve_index_keys(None), ["SHCI", "SZCI", "CYB", "CSIALL"])
        self.assertEqual(SERVER.resolve_index_keys(["shci", "SHCI"]), ["SHCI"])
        self.assertEqual(SERVER.resolve_index_keys(["沪指", "深成指"]), ["SHCI", "SZCI"])
        self.assertEqual(SERVER.resolve_index_keys(["沪深300"]), ["HS300"])
        self.assertEqual(SERVER.resolve_index_keys(["不存在的指数"]), [])

    @patch.object(SERVER, "http_get")
    def test_fetch_index_kline_parsing(self, mock_get):
        SERVER.CACHE_STORE.clear()
        kline_days = [
            ["2026-08-28", "3900.00", "3910.00", "3920.00", "3890.00", "1000"],
            ["2026-08-31", "3910.00", "3986.30", "3990.00", "3905.00", "1100"],
            ["2026-09-01", "3986.30", "3979.89", "3995.00", "3970.00", "1200"],
        ]
        mock_get.return_value = json.dumps({"data": {"sh000001": {"day": kline_days}}})
        res = SERVER.fetch_index_kline(indices=["SHCI"], count=2)
        self.assertEqual(res["data_status"], "ok", res)
        days = res["indices"]["SHCI"]["days"]
        self.assertEqual(len(days), 2)
        self.assertEqual(days[0]["date"], "2026-08-31")
        self.assertEqual(days[0]["change_pct"], "+1.95%")  # (3986.30-3910)/3910
        self.assertEqual(days[1]["change_pct"], "-0.16%")
        # 技术指标字段: 短窗口无 ATR/MA, 但有 20 日高低
        self.assertIsNone(res["indices"]["SHCI"]["atr14"])
        self.assertIsNone(res["indices"]["SHCI"]["ma5"])
        self.assertEqual(res["indices"]["SHCI"]["high_20d"], 3995.0)
        self.assertEqual(res["indices"]["SHCI"]["low_20d"], 3890.0)

    @patch.object(SERVER, "http_get")
    def test_fetch_index_kline_atr_and_ma(self, mock_get):
        """count>=15 时指数 payload 输出 ATR14 与均线 (盘前 Z_ATR 判档与空间引擎输入)"""
        SERVER.CACHE_STORE.clear()
        mock_bars = []
        for i in range(17):  # fetch count+1 根; TR 恒为 3 (high-low=3 主导)
            p = 100.0 + i * 0.2
            mock_bars.append([f"2026-01-{i + 1:02d}", f"{p:.2f}", f"{p + 1:.2f}", f"{p + 2:.2f}", f"{p - 1:.2f}", "1000"])
        mock_get.return_value = json.dumps({"data": {"sh000001": {"day": mock_bars}}})

        res = SERVER.fetch_index_kline(indices=["SHCI"], count=16)
        self.assertEqual(res["data_status"], "ok", res)
        idx = res["indices"]["SHCI"]
        self.assertEqual(idx["atr14"], 3.0)
        self.assertEqual(idx["ma5"], 103.8)  # i=12..16 收盘 (p+1) 均值
        self.assertEqual(idx["high_20d"], 105.2)
        self.assertEqual(idx["low_20d"], 99.0)
        self.assertEqual(idx["atr14_pct"], "2.88%")  # 3.0/104.2

    @patch.object(SERVER, "http_get")
    def test_fetch_market_breadth(self, mock_get):
        SERVER.CACHE_STORE.clear()
        kline_days = [
            ["2026-09-02", "3950.00", "3941.39", "3960.00", "3930.00", "1000"],
            ["2026-09-03", "3941.39", "3942.09", "3965.00", "3935.00", "1100"],
            ["2026-09-04", "3942.09", "3930.12", "3966.00", "3925.00", "1200"],
        ]

        def fake_http_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url:
                return json.dumps({"data": {"sh000001": {"day": kline_days}}})
            if "getTopicZDFenBu" in url:
                return json.dumps({"data": {"qdate": 20260904, "fenbu": [{"1": 100}, {"2": 50}, {"-1": 60}, {"0": 10}]}})
            if "getTopicZTPool" in url:
                return json.dumps({"data": {"pool": [{"c": "000001", "lbc": 3}, {"c": "000002", "lbc": 1}]}})
            if "getTopicZBPool" in url:
                return json.dumps({"data": {"pool": [{"c": "000003"}]}})
            if "getTopicDTPool" in url:
                return json.dumps({"data": {"pool": []}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_http_get
        res = SERVER.fetch_market_breadth(days=2)
        self.assertEqual(res["data_status"], "ok", res)
        rows = res["days_window"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-09-03")
        self.assertEqual(rows[0]["breadth_precision"], "limit_pools_only")
        self.assertEqual(rows[0]["zt_count"], 2)
        self.assertEqual(rows[0]["sh_index_change"], "+0.02%")
        self.assertEqual(rows[1]["breadth_precision"], "exact")
        self.assertEqual(rows[1]["up_count"], 150)
        self.assertEqual(rows[1]["down_count"], 60)
        self.assertEqual(rows[1]["red_rate"], "68.18%")
        self.assertEqual(res["latest_exact_snapshot"]["date"], "2026-09-04")

    @patch.object(SERVER, "http_get")
    def test_fetch_basket_index_parsing(self, mock_get):
        """等权篮子指数: 日度再平衡口径, 基期 100, 成分覆盖度披露"""
        SERVER.CACHE_STORE.clear()
        stock_a = [["2026-09-03", "100.00", "100.00", "101.00", "99.00", "1000"],
                   ["2026-09-04", "101.00", "110.00", "111.00", "100.00", "2000"]]
        stock_b = [["2026-09-03", "200.00", "200.00", "202.00", "198.00", "3000"],
                   ["2026-09-04", "201.00", "210.00", "212.00", "200.00", "4000"]]

        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fqkline" in url and "sh600519" in url:
                return json.dumps({"data": {"sh600519": {"qfqday": stock_a}}})
            if "fqkline" in url and "sh601318" in url:
                return json.dumps({"data": {"sh601318": {"qfqday": stock_b}}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_get
        res = SERVER.fetch_basket_index(["600519", "601318"], count=5)
        self.assertEqual(res["data_status"], "ok", res)
        self.assertEqual(res["series_type"], "equal_weight_constructed")
        self.assertEqual(res["basket_size"], 2)
        self.assertEqual(res["valid_bars"], 1)
        self.assertEqual(res["latest_level"], 107.5)  # (10% + 5%) 等权均值 +7.5%
        self.assertEqual(res["recent_5d_return"], "+7.50%")
        self.assertEqual(res["series"][-1]["stocks_counted"], 2)
        self.assertIn("代理序列", res["note"])

    @patch.object(SERVER, "http_get")
    def test_fetch_basket_index_partial_coverage(self, mock_get):
        """个别成分拉取失败 => partial 且披露失败清单; 剩余成分照常构造"""
        SERVER.CACHE_STORE.clear()
        stock_a = [["2026-09-03", "100.00", "100.00", "101.00", "99.00", "1000"],
                   ["2026-09-04", "101.00", "110.00", "111.00", "100.00", "2000"]]
        stock_b = [["2026-09-03", "200.00", "200.00", "202.00", "198.00", "3000"],
                   ["2026-09-04", "201.00", "210.00", "212.00", "200.00", "4000"]]

        def fake_get(url, timeout=4, encoding="utf-8"):
            if "sh600519" in url:
                return json.dumps({"data": {"sh600519": {"qfqday": stock_a}}})
            if "sh601318" in url:
                return json.dumps({"data": {"sh601318": {"qfqday": stock_b}}})
            raise OSError("gateway flake")

        mock_get.side_effect = fake_get
        res = SERVER.fetch_basket_index(["600519", "601318", "601601"], count=5)
        self.assertEqual(res["data_status"], "partial", res)
        self.assertEqual(res["basket_size"], 2)
        self.assertEqual(res["stocks_failed"], ["601601"])
        self.assertEqual(res["latest_level"], 107.5)

    def test_basket_index_validation(self):
        res = SERVER.fetch_basket_index(["601318"], count=20)  # 少于 2 只
        self.assertEqual(res["data_status"], "unavailable")
        res2 = SERVER.fetch_basket_index(["601318", "600519"], count=70)  # count 超上限
        self.assertEqual(res2["data_status"], "unavailable")

    @patch.object(SERVER, "http_get")
    def test_fetch_sector_kline_full_ohlc(self, mock_get):
        """主源 kline/get 可用时输出完整 OHLCV+成交额口径, amount_ratio_1d 直供资金延续 V 项"""
        SERVER.CACHE_STORE.clear()
        kline_rows = [
            "2026-09-01,2700.00,2710.00,2720.00,2690.00,123456789,45000000000",
            "2026-09-02,2710.00,2705.00,2718.00,2695.00,120000000,42000000000",
            "2026-09-03,2700.00,2690.50,2710.00,2680.00,130000000,46000000000",
            "2026-09-04,2690.00,2635.14,2695.00,2620.00,210000000,62000000000",
        ]

        def fake_get(url, timeout=4, encoding="utf-8"):
            if "stock/kline/get" in url and "fflow" not in url and "secid=90.BK1036" in url:
                return json.dumps({"data": {"name": "半导体", "klines": kline_rows}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_get
        res = SERVER.fetch_sector_kline("BK1036", count=20)
        self.assertEqual(res["data_status"], "partial", res)  # 4 根 < 20 根 => partial
        self.assertTrue(res["ohlc_source"])
        self.assertEqual(res["sector_name"], "半导体")
        self.assertEqual(res["latest_close"], 2635.14)
        self.assertEqual(res["latest_high"], 2695.00)
        self.assertEqual(res["latest_low"], 2620.00)
        self.assertEqual(res["high_20d"], 2720.00)  # 真实 OHLC 高点
        self.assertEqual(res["low_20d"], 2620.00)
        self.assertEqual(res["latest_amount_billion"], 620.0)
        self.assertEqual(res["prev_amount_billion"], 460.0)
        self.assertEqual(res["amount_ratio_1d"], 1.35)
        self.assertEqual(res["latest_change_pct"], "-2.06%")  # (2635.14-2690.50)/2690.50 = -2.0576%

    def test_fetch_index_kline_rejects_oversized_count(self):
        res = SERVER.fetch_index_kline(indices=["SHCI"], count=200)
        self.assertEqual(res["data_status"], "unavailable")
        self.assertIn("130", res["error"])

    @patch.object(SERVER, "http_get")
    def test_fetch_sector_kline_parsing(self, mock_get):
        """BK 代码直查不触发名称解析; 收盘序列来自 fflow daykline"""
        SERVER.CACHE_STORE.clear()
        fflow_lines = [
            "2026-09-02,-10061659648.0,6260276224.0,3761343488.0,-2568673792.0,-7492985856.0,-2.96,1.84,1.11,-0.76,-2.21,2713.20,-0.30,2713.20,-0.30",
            "2026-09-03,-10061659648.0,6260276224.0,3761343488.0,-2568673792.0,-7492985856.0,-2.96,1.84,1.11,-0.76,-2.21,2690.50,-0.84,2690.50,-0.84",
            "2026-09-04,-32075334144.0,20167107584.0,11774541824.0,-10996860416.0,-21078473728.0,-7.48,4.70,2.75,-2.57,-4.92,2635.14,-2.88,2635.14,-2.88",
        ]

        def fake_get(url, timeout=4, encoding="utf-8"):
            if "fflow/daykline" in url and "secid=90.BK1036" in url:
                return json.dumps({"data": {"name": "半导体", "klines": fflow_lines}})
            raise OSError("primary kline/get unavailable")  # 主源不可用 => fflow 兜底

        mock_get.side_effect = fake_get
        res = SERVER.fetch_sector_kline("BK1036", count=20)
        self.assertEqual(res["data_status"], "partial", res)  # mock 仅 3 根 < 20 根 => partial 降级
        self.assertFalse(res["ohlc_source"])
        self.assertEqual(res["sector_name"], "半导体")
        self.assertEqual(res["valid_bars"], 3)
        self.assertEqual(res["latest_close"], 2635.14)
        self.assertEqual(res["latest_change_pct"], "-2.88%")
        self.assertEqual(res["recent_5d_return"], "-2.88%")  # 尾根对首根 (2635.14/2713.20)
        self.assertEqual(res["cum_main_net_inflow_5d_billion"], -521.99)  # 三日累计 (-100.62×2 + -320.75)
        self.assertIn("note", res)

    @patch.object(SERVER, "http_get")
    def test_sector_name_resolution_via_clist(self, mock_get):
        """中文板块名经 clist 全量表精确匹配为 BK 代码"""
        SERVER.CACHE_STORE.clear()

        def fake_get(url, timeout=4, encoding="utf-8"):
            if "clist/get" in url:
                return json.dumps({"data": {"diff": [
                    {"f12": "BK1036", "f14": "半导体"},
                    {"f12": "BK0475", "f14": "银行Ⅱ"},
                ]}})
            if "fflow/daykline" in url:
                return json.dumps({"data": {"name": "半导体", "klines": [
                    "2026-09-03,-1.0,0,0,0,0,0,0,0,0,0,2690.50,-0.84,2690.50,-0.84",
                    "2026-09-04,-2.0,0,0,0,0,0,0,0,0,0,2635.14,-2.88,2635.14,-2.88",
                ]}})
            raise OSError("primary kline/get unavailable")  # 主源不可用 => fflow 兜底

        mock_get.side_effect = fake_get
        res = SERVER.fetch_sector_kline("半导体", count=20)
        self.assertEqual(res["sector_code"], "BK1036")
        self.assertEqual(res["latest_close"], 2635.14)

    def test_sector_kline_rejects_unknown_name(self):
        with patch.object(SERVER, "http_get", side_effect=OSError("down")):
            res = SERVER.fetch_sector_kline("不存在的板块XYZ")
        self.assertEqual(res["data_status"], "unavailable")
        self.assertIn("无法解析板块", res["error"])

    @patch.object(SERVER, "http_get")
    def test_sector_fund_flow_with_history(self, mock_get):
        SERVER.CACHE_STORE.clear()
        mock_sectors = [
            {"f12": "BK1036", "f14": "半导体", "f3": 3.5, "f62": 2500000000.0, "f184": 5.2, "f204": "寒武纪", "f205": "688256"},
            {"f12": "BK0475", "f14": "银行", "f3": -1.2, "f62": -1500000000.0, "f184": -3.1, "f204": "工商银行", "f205": "601398"},
        ]
        fflow_kline = ",".join([
            "2026-09-04", "-32075334144.0", "20167107584.0", "11774541824.0",
            "-10996860416.0", "-21078473728.0", "-7.48", "4.70", "2.75", "-2.57", "-4.92",
            "2635.14", "-2.88", "2635.14", "-2.88",
        ])

        def fake_http_get(url, timeout=4, encoding="utf-8"):
            if "clist/get" in url:
                return json.dumps({"data": {"diff": mock_sectors}})
            if "fflow/daykline" in url:
                return json.dumps({"data": {"klines": [fflow_kline]}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_http_get
        res = SERVER.fetch_sector_fund_flow(count=2, days=2)
        self.assertEqual(res["data_status"], "ok", res)
        entry = res["top_inflow_sectors"][0] if res["top_inflow_sectors"][0]["code"] == "BK1036" else res["top_inflow_sectors"][1]
        self.assertEqual(len(entry["history"]), 1)
        self.assertEqual(entry["history"][0]["main_net_inflow_billion"], -320.75)
        self.assertEqual(entry["history"][0]["change_pct"], "-2.88%")
        self.assertEqual(entry["cum_net_inflow_billion"], -320.75)
        self.assertEqual(entry["fund_flow_trend"], "连续净流出")
        # days>1 时 count 上限收紧
        res2 = SERVER.fetch_sector_fund_flow(count=20, days=5)
        self.assertIn("error", res2)

    def test_lhb_market_summary_normalizes_compact_date(self):
        """全市场概览传 YYYYMMDD 紧凑日期必须归一化为横杠格式, 否则上游必然查空"""
        captured = []

        def fake_get(url, timeout=4, encoding="utf-8"):
            captured.append(url)
            return json.dumps({"result": {"data": [{
                "SECURITY_CODE": "000017", "SECURITY_NAME_ABBR": "深中华A",
                "TRADE_DATE": "2026-09-04 00:00:00", "CHANGE_RATE": -7.5,
                "CLOSE_PRICE": 5.2, "TOTAL_NET": -45587543.84, "TURNRATE": 12.3,
                "EXPLANATION": "日跌幅偏离值达到7%",
            }]}})

        with patch.object(SERVER, "http_get", side_effect=fake_get):
            res = SERVER.fetch_longhubang_detail(symbol=None, date_str="20260904")
        self.assertEqual(res["data_status"], "ok")
        self.assertEqual(res["date"], "2026-09-04")
        self.assertEqual(res["top_net_buy_stocks"][0]["code"], "000017")
        self.assertTrue(any("2026-09-04" in urllib.parse.unquote(u) for u in captured))
        self.assertFalse(any("20260904" in urllib.parse.unquote(u).split("filter")[-1] for u in captured))

    def test_lhb_org_seat_net_merges_buy_and_sell_sides(self):
        """机构专用净额必须按席位合并买卖两榜的 NET, 单边相减会丢席位自身对冲"""
        mock_buy = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 50000000, "SELL": 0, "NET": 50000000}]}}
        mock_sell = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 0, "SELL": 30000000, "NET": -30000000}]}}
        mock_sum = {"result": {"data": [{"SECURITY_NAME_ABBR": "思泉新材", "TRADE_DATE": "2026-09-04 00:00:00",
                                          "TOTAL_BUY": 100000000, "TOTAL_SELL": 50000000, "TOTAL_NET": 50000000}]}}

        with patch.object(SERVER, "http_get", side_effect=[json.dumps(mock_buy), json.dumps(mock_sell), json.dumps(mock_sum)]):
            res = SERVER.fetch_longhubang_detail(symbol="301489")
        self.assertEqual(res["org_seat_count"], 1)
        self.assertEqual(res["org_seat_net_wan"], "+2000.00 万元")  # 5000万 - 3000万
        self.assertEqual(res["seat_quality_judgment"], "机构席位净买入")
        self.assertEqual(res["org_seat_net_details"][0]["net_wan"], "+2000.00 万")

    def test_host_throttle_enforces_min_interval(self):
        """同一主机第二次请求必须先经过最小间隔限速; 不同主机不受影响"""
        class MockResp:
            def read(self, n=-1):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", return_value=MockResp()):
            SERVER.http_get("https://push2.eastmoney.com/a?req=1")   # 首次不限速
            SERVER.http_get("https://push2.eastmoney.com/a?req=2")   # 同主机 => 限速
            SERVER.http_get("https://web.ifzq.gtimg.cn/b?req=1")     # 不同主机 => 不限速
        self.assertEqual(self.sleep_mock.call_count, 1)
        args, _ = self.sleep_mock.call_args
        self.assertGreaterEqual(args[0], 0.3)
        self.assertLessEqual(args[0], SERVER.HOST_MIN_INTERVAL_SECONDS + 0.01)

    def test_circuit_breaker_opens_after_consecutive_failures(self):
        """同主机连续 3 次连接失败后熔断: 第 4 次快速抛 ConnectionError 且不再发起真实请求"""
        url = "https://push2.eastmoney.com/api/qt/clist/get?x=1"
        with patch("urllib.request.urlopen", side_effect=OSError("down")):
            for _ in range(SERVER.BREAKER_FAILURE_THRESHOLD):
                with self.assertRaises(OSError):
                    SERVER.http_get(url)
            # 若仍发起真实请求, urlopen mock 会抛 OSError 而非 ConnectionError, 断言即失败
            with self.assertRaises(ConnectionError):
                SERVER.http_get("https://push2.eastmoney.com/api/qt/clist/get?x=2")

    def test_circuit_breaker_resets_on_success(self):
        """任一请求成功即清空该主机失败计数, 不影响后续正常调用"""
        host = "push2.eastmoney.com"
        SERVER._breaker_record_failure(host)
        SERVER._breaker_record_failure(host)
        self.assertIsNone(SERVER._HOST_FAILURE_STATE[host]["opened_at"])  # 2次未达阈值, 未熔断

        class MockResp:
            def read(self, n=-1):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", return_value=MockResp()):
            SERVER.http_get("https://push2.eastmoney.com/x?ok=1")
        self.assertNotIn(host, SERVER._HOST_FAILURE_STATE)

    def test_ttl_for_history_long_caches_completed_days(self):
        """收盘定格的历史日期用长缓存, 当日或无日期用短缓存"""
        self.assertEqual(SERVER.ttl_for_history("2026-09-04 00:00:00"), SERVER.HISTORICAL_CACHE_TTL_SECONDS)
        self.assertEqual(SERVER.ttl_for_history("2026-09-04"), SERVER.HISTORICAL_CACHE_TTL_SECONDS)
        self.assertEqual(SERVER.ttl_for_history(datetime.now().strftime("%Y-%m-%d")), SERVER.CACHE_TTL_SECONDS)
        self.assertEqual(SERVER.ttl_for_history(None), SERVER.CACHE_TTL_SECONDS)

    def test_unknown_tool_returns_error(self):
        res = SERVER.handle_tool_call("unknown_tool", {})
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
