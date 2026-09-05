import importlib.util
import json
import unittest
import urllib.parse
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
        self.assertGreaterEqual(len(tools), 10)
        tool_names = {t["name"] for t in tools}
        self.assertIn("get_stock_quote", tool_names)
        self.assertIn("get_stock_kline", tool_names)
        self.assertIn("get_stock_timeline", tool_names)
        self.assertIn("get_market_sentiment", tool_names)
        self.assertIn("get_limit_up_ladder", tool_names)
        self.assertIn("get_index_kline", tool_names)
        self.assertIn("get_market_breadth", tool_names)
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
        SERVER.CACHE_STORE.clear()
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
            res = SERVER.fetch_market_sentiment()  # 当日路径走实时指数快照
            self.assertEqual(res.get("data_status"), "ok", res)
            self.assertEqual(res["zt_count"], 2)
            self.assertEqual(res["zb_count"], 1)
            self.assertEqual(res["exact_break_rate"], "33.33%")
        self.assertEqual(res["max_ladder_height"], "3 连板")

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_historical_uses_index_kline(self, mock_get):
        """历史日期的指数涨跌幅与成交额必须来自指数日K回补, 而非实时快照"""
        SERVER.CACHE_STORE.clear()

        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def fake_http_get(url, timeout=4, encoding="utf-8"):
            # 沪指: 09-02 收 3950, 09-03 收 3986 (+0.91%), 成交额 650 亿; 深证综指成交额 700 亿
            if "secid=1.000001" in url:
                klines = [
                    "2026-09-02,3920.00,3950.00,3960.00,3910.00,123000000,65000000000",
                    "2026-09-03,3955.00,3986.00,3990.00,3950.00,124000000,66000000000",
                ]
                return json.dumps({"data": {"klines": klines}})
            if "secid=0.399106" in url:
                klines = ["2026-09-03,2300.00,2310.00,2320.00,2290.00,99000000,70000000000"]
                return json.dumps({"data": {"klines": klines}})
            raise AssertionError("unexpected url: " + url)

        mock_get.side_effect = fake_http_get
        pools = [MockResp({"data": {"pool": [{"c": "000001", "lbc": 2}]}}),
                 MockResp({"data": {"pool": []}}),
                 MockResp({"data": {"pool": []}})]
        with patch("urllib.request.urlopen", side_effect=pools):
            res = SERVER.fetch_market_sentiment("2026-09-03")
        self.assertEqual(res.get("data_status"), "ok", res)
        self.assertEqual(res["sh_index_change"], "+0.91%")
        self.assertEqual(res["total_turnover_billion"], 1360.0)

    @patch.object(SERVER, "http_get")
    def test_market_sentiment_rejects_non_trading_date(self, mock_get):
        """非交易日的历史查询应显式 unavailable, 不得以零值伪装 ok"""
        SERVER.CACHE_STORE.clear()

        def fake_http_get(url, timeout=4, encoding="utf-8"):
            return json.dumps({"data": {"klines": ["2026-09-03,3955.00,3986.00,3990.00,3950.00,124000000,66000000000"]}})

        mock_get.side_effect = fake_http_get
        res = SERVER.fetch_market_sentiment("2026-09-06")  # 周日, 永远非交易日
        self.assertEqual(res["data_status"], "unavailable")
        self.assertIn("非交易日", res["error"])

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

        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def fake_urlopen(req, timeout=4):
            captured.append(req.full_url)
            return MockResp({"result": {"data": [{
                "SECURITY_CODE": "000017", "SECURITY_NAME_ABBR": "深中华A",
                "TRADE_DATE": "2026-09-04 00:00:00", "CHANGE_RATE": -7.5,
                "CLOSE_PRICE": 5.2, "TOTAL_NET": -45587543.84, "TURNRATE": 12.3,
                "EXPLANATION": "日跌幅偏离值达到7%",
            }]}})

        SERVER.CACHE_STORE.clear()
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = SERVER.fetch_longhubang_detail(symbol=None, date_str="20260904")
        self.assertEqual(res["data_status"], "ok")
        self.assertEqual(res["date"], "2026-09-04")
        self.assertEqual(res["top_net_buy_stocks"][0]["code"], "000017")
        self.assertTrue(any("2026-09-04" in urllib.parse.unquote(u) for u in captured))
        self.assertFalse(any("20260904" in urllib.parse.unquote(u).split("filter")[-1] for u in captured))

    def test_lhb_org_seat_net_merges_buy_and_sell_sides(self):
        """机构专用净额必须按席位合并买卖两榜的 NET, 单边相减会丢席位自身对冲"""
        SERVER.CACHE_STORE.clear()

        class MockResp:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        mock_buy = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 50000000, "SELL": 0, "NET": 50000000}]}}
        mock_sell = {"result": {"data": [{"OPERATEDEPT_NAME": "机构专用", "BUY": 0, "SELL": 30000000, "NET": -30000000}]}}
        mock_sum = {"result": {"data": [{"SECURITY_NAME_ABBR": "思泉新材", "TRADE_DATE": "2026-09-04 00:00:00",
                                          "TOTAL_BUY": 100000000, "TOTAL_SELL": 50000000, "TOTAL_NET": 50000000}]}}

        with patch("urllib.request.urlopen", side_effect=[MockResp(mock_buy), MockResp(mock_sell), MockResp(mock_sum)]):
            res = SERVER.fetch_longhubang_detail(symbol="301489")
        self.assertEqual(res["org_seat_count"], 1)
        self.assertEqual(res["org_seat_net_wan"], "+2000.00 万元")  # 5000万 - 3000万
        self.assertEqual(res["seat_quality_judgment"], "机构席位净买入")
        self.assertEqual(res["org_seat_net_details"][0]["net_wan"], "+2000.00 万")

    def test_unknown_tool_returns_error(self):
        res = SERVER.handle_tool_call("unknown_tool", {})
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
