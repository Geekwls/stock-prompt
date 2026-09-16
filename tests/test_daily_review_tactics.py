import unittest

from tools.calculations.market import (
    calculate_market_divergence_index,
    filter_intraday_impulse,
    reconcile_watchlist_triggers,
)
from tools.calculations.stock import validate_stock_hard_gate


class DailyReviewTacticsTest(unittest.TestCase):
    def test_market_divergence_extreme_polarization(self):
        # 指数上涨，但红盘率只有 25%，中位数为 -2.0% -> 极端二八撕裂
        res = calculate_market_divergence_index(
            index_pct=0.4,
            breadth_ratio=25.0,
            median_pct=-2.0,
            is_fake_positive=True,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["divergence_type"], "extreme_polarization")
        self.assertTrue(res["value"]["cap_applied"])
        self.assertEqual(res["value"]["score_penalty"], 20.0)
        self.assertIn("权重掩护出货警示", res["value"]["tactical_guidance"])

    def test_market_divergence_healthy_rise(self):
        # 指数收红，红盘率 70%，中位数 +1.2% -> 健康普涨
        res = calculate_market_divergence_index(
            index_pct=0.8,
            breadth_ratio=70.0,
            median_pct=1.2,
            is_fake_positive=False,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["divergence_type"], "healthy_broad_rise")
        self.assertFalse(res["value"]["cap_applied"])
        self.assertEqual(res["value"]["score_penalty"], 0.0)

    def test_filter_intraday_impulse_early_trap(self):
        # 跌破分时均线 -> 早盘诱多陷阱
        res = filter_intraday_impulse(
            current_time="09:55",
            sector_gain=3.0,
            is_above_vwap=False,
            turnover_increasing=True,
            pullback_broken=True,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["impulse_quality"], "early_morning_trap")
        self.assertFalse(res["value"]["is_valid"])
        self.assertIn("诱多出货陷阱", res["value"]["tactical_guidance"])

    def test_filter_intraday_impulse_confirmed_strength(self):
        # 企稳分时黄线上方且持续放量 -> 确认日内强势
        res = filter_intraday_impulse(
            current_time="10:15",
            sector_gain=2.8,
            is_above_vwap=True,
            turnover_increasing=True,
            pullback_broken=False,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["impulse_quality"], "confirmed_intraday_strength")
        self.assertTrue(res["value"]["is_valid"])
        self.assertIn("日内真实强势主线", res["value"]["tactical_guidance"])

    def test_filter_intraday_impulse_before_ten_is_not_confirmed(self):
        res = filter_intraday_impulse(current_time="09:35", sector_gain=3.0)
        self.assertEqual(res["value"]["gate_status"], "pre_threshold")
        self.assertFalse(res["value"]["is_valid"])

    def test_watchlist_reconciliation_is_deterministic(self):
        res = reconcile_watchlist_triggers(
            [{"id": "A"}, {"id": "B"}, {"id": "C"}],
            {"A": {"met": True}, "B": {"broken": True}, "C": {"met": False}},
        )
        self.assertEqual(res["value"]["counts"], {"confirmed": 1, "abandoned": 1, "stop_loss": 1, "unverifiable": 0})

    def test_validate_stock_hard_gate_tactical_retreat_block(self):
        # 所属板块处于退潮期，触发战术硬拦截
        res = validate_stock_hard_gate(
            bar_count=120,
            adjusted=True,
            benchmark_complete=True,
            industry_complete=True,
            sector_lifecycle_state="退潮期",
        )
        self.assertEqual(res["status"], "failed")
        self.assertFalse(res["value"])
        self.assertTrue(res["tactical_gate_blocked"])
        self.assertFalse(res["entry_allowed"])
        self.assertEqual(res["position_cap"], 0)
        self.assertIn("sector_not_in_retreat", res["missing"])
        self.assertIn("退潮衰竭期", res["tactical_warning"])

    def test_validate_stock_hard_gate_tactical_follower_block(self):
        # 所属板块处于加速期，且股票为跟风杂毛，触发战术硬拦截
        res = validate_stock_hard_gate(
            bar_count=120,
            adjusted=True,
            benchmark_complete=True,
            industry_complete=True,
            sector_lifecycle_state="加速期",
            stock_role="跟风",
        )
        self.assertEqual(res["status"], "failed")
        self.assertFalse(res["value"])
        self.assertTrue(res["tactical_gate_blocked"])
        self.assertIn("not_acceleration_follower", res["missing"])
        self.assertIn("严禁追高开仓后排跟风杂毛", res["tactical_warning"])


if __name__ == "__main__":
    unittest.main()
