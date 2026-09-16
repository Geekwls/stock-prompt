import unittest

from tools.calculations.sector import (
    assess_rotation_effectiveness,
    calculate_leader_core_divergence,
    resolve_rotation_timeframe,
)


class SectorRotationTacticsTest(unittest.TestCase):
    def test_assess_rotation_effectiveness_electric_fan(self):
        # 4个以上板块异动，领涨板块成交占比低且涨停少 -> 电风扇无效轮动
        res = assess_rotation_effectiveness(
            active_sectors_count=5,
            leader_turnover_share=4.5,
            limit_up_clusters=1,
            market_amount_ratio=0.95,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["rotation_type"], "electric_fan")
        self.assertFalse(res["value"]["is_effective"])
        self.assertEqual(res["value"]["risk_level"], "high")
        self.assertIn("无效轮动防诱多预警", res["value"]["tactical_guidance"])

    def test_assess_rotation_effectiveness_mainline(self):
        # 核心主线成交占比达标，涨停梯队完整 -> 主线聚焦有效轮动
        res = assess_rotation_effectiveness(
            active_sectors_count=2,
            leader_turnover_share=9.5,
            limit_up_clusters=4,
            market_amount_ratio=1.1,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["rotation_type"], "mainline_focused")
        self.assertTrue(res["value"]["is_effective"])
        self.assertEqual(res["value"]["risk_level"], "low")
        self.assertIn("核心主线成交额占比与梯队效应达标", res["value"]["tactical_guidance"])

    def test_calculate_leader_core_divergence_core_desertion(self):
        # 中军破位走弱净流出，龙头硬顶涨停 -> 假繁荣出货尾声背离
        res = calculate_leader_core_divergence(
            core_trend="break_ma20",
            core_net_flow=-15.0,
            leader_state="limit_up",
            leader_height=4,
            inner_up_ratio=30.0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["divergence_type"], "core_desertion")
        self.assertEqual(res["value"]["risk_level"], "severe_divergence")
        self.assertIn("百亿中军破位走弱", res["value"]["tactical_advice"])

    def test_calculate_leader_core_divergence_leader_collapse(self):
        # 龙头跌停A杀，后排反弹 -> 弱抽血陷阱
        res = calculate_leader_core_divergence(
            core_trend="above_ma20",
            core_net_flow=-2.0,
            leader_state="limit_down",
            leader_height=1,
            inner_up_ratio=40.0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["divergence_type"], "leader_collapse")
        self.assertEqual(res["value"]["risk_level"], "high_risk")
        self.assertIn("第一核心龙头已出现跌停", res["value"]["tactical_advice"])

    def test_calculate_leader_core_divergence_healthy_resonance(self):
        # 中军均线上方，龙头连板，板块内大面积红盘 -> 健康共振
        res = calculate_leader_core_divergence(
            core_trend="above_ma20",
            core_net_flow=12.0,
            leader_state="limit_up",
            leader_height=3,
            inner_up_ratio=75.0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["divergence_type"], "healthy_resonance")
        self.assertEqual(res["value"]["risk_level"], "healthy")
        self.assertIn("良性量价共振", res["value"]["tactical_advice"])

    def test_resolve_rotation_timeframe_major_trend(self):
        # 宏观产业革命，持续20日以上 -> 季度大主线
        res = resolve_rotation_timeframe(
            catalyst_scope="macro_trend",
            duration_days=30,
            trend_ma20_slope="up",
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["cycle_level"], "major_trend")
        self.assertIn("季度趋势大主线", res["value"]["cycle_name"])
        self.assertIn("依托 10 日与 20 日均线防守", res["value"]["appropriate_defense_line"])

    def test_resolve_rotation_timeframe_short_term(self):
        # 突发短命消息，活跃2天 -> 超短脉冲
        res = resolve_rotation_timeframe(
            catalyst_scope="pulsed",
            duration_days=2,
            trend_ma20_slope="flat",
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["cycle_level"], "short_term")
        self.assertIn("超短脉冲题材", res["value"]["cycle_name"])
        self.assertIn("严禁恋战与格局", res["value"]["appropriate_defense_line"])


if __name__ == "__main__":
    unittest.main()
