import unittest

from tools.calculations.market import (
    assess_catalyst_exhaustion,
    calculate_auction_traffic_light,
    calculate_sentiment_opportunity_score,
)


class MarketPredictionTacticsTest(unittest.TestCase):
    def test_auction_traffic_light_green_scenario_a(self):
        # 龙头超预期大幅高开抢筹，大盘平开无拖累，无核按钮 -> 绿灯 剧本 A
        res = calculate_auction_traffic_light(
            index_gap=0.2,
            leader_gap=4.5,
            leader_amount_ratio=1.5,
            nuclear_count=0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["traffic_light"], "green")
        self.assertEqual(res["value"]["matched_scenario"], "A")
        self.assertEqual(res["value"]["auction_sentiment"], "bullish")
        self.assertIn("允许打板第一身位先锋", res["value"]["action_guidance"])

    def test_auction_traffic_light_red_scenario_c(self):
        # 存在 2 只跌停核按钮，或龙头大低开 -> 红灯 剧本 C
        res = calculate_auction_traffic_light(
            index_gap=-0.5,
            leader_gap=-6.0,
            leader_amount_ratio=2.0,
            nuclear_count=2,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["traffic_light"], "red")
        self.assertEqual(res["value"]["matched_scenario"], "C")
        self.assertEqual(res["value"]["auction_sentiment"], "bearish")
        self.assertIn("严禁开新仓", res["value"]["action_guidance"])

    def test_auction_traffic_light_yellow_scenario_b(self):
        # 常态平开震荡，无极端核按钮与超强封单 -> 黄灯 剧本 B
        res = calculate_auction_traffic_light(
            index_gap=-0.1,
            leader_gap=1.0,
            leader_amount_ratio=0.9,
            nuclear_count=0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["traffic_light"], "yellow")
        self.assertEqual(res["value"]["matched_scenario"], "B")
        self.assertEqual(res["value"]["auction_sentiment"], "neutral")
        self.assertIn("等待9:45分时均线确认", res["value"]["action_guidance"])

    def test_sentiment_opportunity_ice_breaking(self):
        # 冰点破局出妖股，短线情绪机会分高
        res = calculate_sentiment_opportunity_score(
            ladder_health_score=80,
            leader_premium=85,
            limit_up_count=50,
            nuclear_count=0,
            emotion_cycle="ice_breaking",
        )
        self.assertEqual(res["status"], "complete")
        self.assertGreater(res["value"], 85.0)
        self.assertEqual(res["emotion_cycle"], "ice_breaking")

    def test_sentiment_opportunity_retreat_penalty(self):
        # 退潮期且有核按钮，大幅扣减
        res = calculate_sentiment_opportunity_score(
            ladder_health_score=40,
            leader_premium=30,
            limit_up_count=20,
            nuclear_count=2,
            emotion_cycle="retreat",
        )
        self.assertEqual(res["status"], "complete")
        self.assertLess(res["value"], 30.0)

    def test_sentiment_opportunity_low_coverage(self):
        res = calculate_sentiment_opportunity_score(
            ladder_health_score=80,
            leader_premium=85,
            limit_up_count=50,
            coverage=65.0,
        )
        self.assertEqual(res["status"], "unavailable")

    def test_catalyst_exhaustion_high_risk(self):
        # 前期大涨 + 重磅利好 + 大幅高开 -> 高透支/冲高回落诱多风险
        res = assess_catalyst_exhaustion(
            catalyst_level="heavy",
            yesterday_gain=5.0,
            expected_gap=3.0,
            consecutive_up_days=3,
            cumulative_gain=12.0,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["exhaustion_risk"], "high")
        self.assertTrue(res["value"]["fade_warning"])
        self.assertIn("严禁开盘追高", res["value"]["tactical_advice"])

    def test_catalyst_exhaustion_low_risk(self):
        # 底部首发催化 -> 低透支风险
        res = assess_catalyst_exhaustion(
            catalyst_level="heavy",
            yesterday_gain=0.5,
            expected_gap=1.0,
            consecutive_up_days=1,
            cumulative_gain=1.5,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["exhaustion_risk"], "low")
        self.assertFalse(res["value"]["fade_warning"])


if __name__ == "__main__":
    unittest.main()
