import unittest
from tools.calculations.market import (
    calculate_tactical_position_budget,
    calculate_extreme_loss_effect,
)
from tools.calculations.sector import (
    validate_sector_capacity,
    map_capital_seesaw_matrix,
)
from tools.calculations.stock import (
    calculate_dynamic_trailing_stop,
    validate_stock_hard_gate,
)


class TacticalPositionAndRiskTest(unittest.TestCase):
    def test_position_budget_regimes_and_caps(self):
        # 1. 常规 S2 震荡市，中性
        res_s2 = calculate_tactical_position_budget(sentiment_total=50.0, market_regime="S2")
        self.assertEqual(res_s2["status"], "complete")
        self.assertEqual(res_s2["value"]["max_position_cap"], 40.0)
        self.assertEqual(res_s2["value"]["cash_buffer_min"], 60.0)
        self.assertEqual(res_s2["value"]["single_leader_cap"], 15.0)  # min(15, 40*0.4=16) -> 15.0
        self.assertEqual(res_s2["value"]["single_core_cap"], 24.0)    # min(25, 40*0.6=24) -> 24.0

        # 2. S4 趋势主升市，高情绪
        res_s4 = calculate_tactical_position_budget(sentiment_total=80.0, market_regime="S4")
        self.assertEqual(res_s4["value"]["max_position_cap"], 80.0)  # 80 + 10 -> cap at 80

        # 3. S6 无序退潮市，清零
        res_s6 = calculate_tactical_position_budget(sentiment_total=30.0, market_regime="S6")
        self.assertEqual(res_s6["value"]["max_position_cap"], 0.0)
        self.assertEqual(res_s6["value"]["tactical_guidance"], "绝对防守空仓")

        # 4. 二八极端割裂强制封顶
        res_div = calculate_tactical_position_budget(
            sentiment_total=60.0, market_regime="S3", divergence_level="severe_divergence"
        )
        self.assertEqual(res_div["value"]["max_position_cap"], 30.0)
        self.assertTrue(res_div["value"]["divergence_capped"])

        # 5. 极端恶性亏钱扣减
        res_loss = calculate_tactical_position_budget(
            sentiment_total=50.0, market_regime="S2", extreme_loss_ratio=18.0
        )
        self.assertEqual(res_loss["value"]["max_position_cap"], 20.0)

    def test_extreme_loss_effect_quantification(self):
        # 1. 正常安全区间
        res_safe = calculate_extreme_loss_effect(
            limit_down_count=3, limit_down_sealed_amount_yi=2.5, nuclear_count=0, big_face_count=2
        )
        self.assertEqual(res_safe["status"], "complete")
        self.assertEqual(res_safe["value"]["loss_effect_level"], "low")
        self.assertFalse(res_safe["value"]["short_term_veto"])

        # 2. 局部亏钱效应
        res_med = calculate_extreme_loss_effect(
            limit_down_count=12, limit_down_sealed_amount_yi=12.0, nuclear_count=1, big_face_count=9
        )
        self.assertEqual(res_med["value"]["loss_effect_level"], "medium")
        self.assertFalse(res_med["value"]["short_term_veto"])

        # 3. 巨额跌停封死触发流动性踩踏与一票否决
        res_severe = calculate_extreme_loss_effect(
            limit_down_count=25, limit_down_sealed_amount_yi=38.0, nuclear_count=4, big_face_count=20
        )
        self.assertEqual(res_severe["value"]["loss_effect_level"], "severe")
        self.assertTrue(res_severe["value"]["short_term_veto"])
        self.assertTrue(res_severe["value"]["is_liquidity_frozen"])
        self.assertIn("流动性踩踏", res_severe["value"]["risk_prompt"])

    def test_sector_capacity_validation(self):
        # 1. 超级大容量主线
        res_mega = validate_sector_capacity(sector_amount_yi=450.0, market_total_amount_yi=10000.0)
        self.assertEqual(res_mega["status"], "complete")
        self.assertEqual(res_mega["value"]["capacity_type"], "mega_mainline")
        self.assertTrue(res_mega["value"]["is_mainline_eligible"])

        # 2. 标准主力题材
        res_std = validate_sector_capacity(sector_amount_yi=250.0, market_total_amount_yi=10000.0)
        self.assertEqual(res_std["value"]["capacity_type"], "standard_mainline")
        self.assertTrue(res_std["value"]["is_mainline_eligible"])

        # 3. 微型小众题材剥夺主线资格
        res_micro = validate_sector_capacity(sector_amount_yi=35.0, market_total_amount_yi=10000.0)
        self.assertEqual(res_micro["value"]["capacity_type"], "micro_niche")
        self.assertFalse(res_micro["value"]["is_mainline_eligible"])
        self.assertIn("小微游击题材", res_micro["value"]["tradable_scale"])

    def test_capital_seesaw_matrix(self):
        # 1. 科技退潮对流红利防御
        res_tech = map_capital_seesaw_matrix(current_mainline="AI算力与CPO", current_lifecycle="retreat")
        self.assertEqual(res_tech["status"], "complete")
        self.assertTrue(res_tech["value"]["is_active_outflow"])
        self.assertIn("红利防御", res_tech["value"]["seesaw_counterpart"])
        self.assertIn("retreat", res_tech["value"]["tactical_instruction"])

        # 2. 资源分歧对流新能源
        res_res = map_capital_seesaw_matrix(current_mainline="黄金有色资源", current_lifecycle="divergence")
        self.assertIn("新能源", res_res["value"]["seesaw_counterpart"])

        # 3. 主线健康期
        res_health = map_capital_seesaw_matrix(current_mainline="半导体芯片", current_lifecycle="markup")
        self.assertFalse(res_health["value"]["is_active_outflow"])

    def test_dynamic_trailing_stop(self):
        # 1. 浮盈未达 8%（常规止损）
        res_init = calculate_dynamic_trailing_stop(
            entry_price=10.0, current_price=10.5, highest_price=10.6
        )
        self.assertEqual(res_init["status"], "complete")
        self.assertEqual(res_init["value"]["stage"], "initial_risk")
        self.assertEqual(res_init["value"]["trailing_stop_price"], 9.5)

        # 2. 浮盈达 10%（保本铁律上移至 10.05）
        res_bk = calculate_dynamic_trailing_stop(
            entry_price=10.0, current_price=10.8, highest_price=11.0, ma5=10.6
        )
        self.assertEqual(res_bk["value"]["stage"], "breakeven_protection")
        self.assertEqual(res_bk["value"]["trailing_stop_price"], 10.6)  # max(10*1.005, 10.6) -> 10.6
        self.assertIn("第一铁律", res_bk["value"]["action_advice"])

        # 3. 浮盈超 25%（大趋势锁定高点回撤 10% 或 10日线）
        res_lock = calculate_dynamic_trailing_stop(
            entry_price=10.0, current_price=12.2, highest_price=13.0, ma10=11.9
        )
        self.assertEqual(res_lock["value"]["stage"], "profit_lock_major")
        self.assertEqual(res_lock["value"]["trailing_stop_price"], 11.9)  # max(13*0.9=11.7, 11.9) -> 11.9
        self.assertIn("启动大趋势锁利", res_lock["value"]["action_advice"])

    def test_hard_gate_blocks_averaging_down_in_downtrend(self):
        # 1. 破位且浮亏触发战术拦截
        res_block = validate_stock_hard_gate(
            kline_count=150, adjusted=True, benchmark_complete=True, industry_complete=True,
            is_st=False, position_state="holding_loss", trend_state="break_ma20"
        )
        self.assertEqual(res_block["status"], "failed")
        self.assertFalse(res_block["value"])
        self.assertTrue(res_block["tactical_gate_blocked"])
        self.assertEqual(res_block["blocked_reason"], "averaging_down_in_downtrend")
        self.assertIn("禁止逆势加仓摊平", res_block["tactical_warning"])

        # 2. 破位但无持仓观察中（不触发补仓拦截，可按右侧条件观察）
        res_watch = validate_stock_hard_gate(
            kline_count=150, adjusted=True, benchmark_complete=True, industry_complete=True,
            is_st=False, position_state="watching", trend_state="break_ma20"
        )
        self.assertFalse(res_watch["tactical_gate_blocked"])


if __name__ == "__main__":
    unittest.main()
