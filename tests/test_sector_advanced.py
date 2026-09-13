import unittest

from tools.calculations.sector import (
    calculate_capital_continuity,
    calculate_ladder_health,
    calculate_sector_cannibalization,
    calculate_sector_exhaustion,
)


class SectorAdvancedCalculationTest(unittest.TestCase):
    def test_ladder_health_pyramid(self):
        output = calculate_ladder_health({"5": 1, "4": 2, "3": 3, "2": 5, "1": 10})
        self.assertEqual(output["value"]["max_height"], 5)
        self.assertEqual(output["value"]["fault_gap"], 0)
        self.assertEqual(output["value"]["warning_level"], "healthy")
        self.assertEqual(output["value"]["ladder_score"], 100.0)

    def test_ladder_health_mild_and_severe_faults(self):
        mild = calculate_ladder_health({"4": 1, "3": 1, "2": 0, "1": 3})
        self.assertEqual(mild["value"]["fault_gap"], 1)
        self.assertEqual(mild["value"]["warning_level"], "mild_gap")
        severe = calculate_ladder_health({"7": 1, "6": 0, "5": 0, "4": 0, "3": 0, "2": 2, "1": 15})
        self.assertEqual(severe["value"]["fault_gap"], 4)
        self.assertEqual(severe["value"]["warning_level"], "severe_fault")
        self.assertIn("isolated_leader_risk", severe["value"]["risk_flag"])

    def test_ladder_health_rejects_invalid_distribution(self):
        with self.assertRaises(ValueError):
            calculate_ladder_health({"4": -1})
        self.assertEqual(calculate_ladder_health({"4": 0})["status"], "unavailable")

    def test_sector_cannibalization_regimes(self):
        balanced = calculate_sector_cannibalization(5, 1.15, 0.5)
        self.assertEqual(balanced["value"]["market_dynamic"], "balanced_growth")
        self.assertAlmostEqual(balanced["value"]["siphon_index"], 24.1667, places=3)
        extreme = calculate_sector_cannibalization(12.5, 0.95, 2.1)
        self.assertEqual(extreme["value"]["market_dynamic"], "siphon_extreme")
        self.assertGreaterEqual(extreme["value"]["siphon_index"], 70)
        self.assertTrue(extreme["value"]["affected_sectors"])
        diffuse = calculate_sector_cannibalization(6, 0.98, 1.0)
        self.assertEqual(diffuse["value"]["market_dynamic"], "diffuse_rotation")

    def test_sector_cannibalization_matrix_and_transfer(self):
        output = calculate_sector_cannibalization(
            10, 1.0, 1.8,
            outflow_sectors=[
                {"name": "红利", "loss_rate": 2.2, "net_outflow": 100, "flow_to_leader": 40},
                {"name": "医药", "loss_rate": 1.9, "net_outflow": 50, "flow_to_leader": 10},
                {"name": "地产", "loss_rate": 1.6, "net_outflow": 25, "flow_to_leader": 5},
                {"name": "传媒", "loss_rate": 1.2, "net_outflow": 10, "flow_to_leader": 0},
            ],
        )
        self.assertEqual(output["value"]["affected_sectors"], ["红利", "医药", "地产"])
        self.assertAlmostEqual(output["value"]["redirected_flow_ratio"], 29.7297, places=3)

    def test_sector_exhaustion_objective_mode_matches_direct_mode(self):
        objective = calculate_sector_exhaustion(
            new_high_shrink_days=2,
            divergence_ratio=0.5,
            relay_failed_ratio=0.4,
            break_rate=0.2,
            sector_turnover_share=12,
            low_position_spillover=0.2,
            auto_derive=True,
        )
        direct = calculate_sector_exhaustion(18, 9, 28)
        self.assertEqual(objective["value"], direct["value"])
        self.assertEqual(objective["derivation"], "objective")
        self.assertEqual(calculate_sector_exhaustion(auto_derive=True)["value"], "N/A")

    def test_ratio_disambiguation(self):
        # 1. 裸数值 1 或 1.0 必须熔断报错，防止 100 倍歧义
        with self.assertRaises(ValueError) as ctx:
            calculate_sector_exhaustion(divergence_ratio=1, auto_derive=True)
        self.assertIn("存在 1% 与 100% 的 100 倍比例歧义", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            calculate_sector_exhaustion(divergence_ratio=1.0, auto_derive=True)
        self.assertIn("存在 1% 与 100% 的 100 倍比例歧义", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            calculate_capital_continuity(amount_ratio=1.0, break_rate=1)
        self.assertIn("存在 1% 与 100% 的 100 倍比例歧义", str(ctx.exception))

        # 2. 百分比字符串无歧义解析：'1%' 严格等同于 0.01
        res_pct_str = calculate_sector_exhaustion(
            new_high_shrink_days=0,
            relay_risk=0,
            capital_spillover=0,
            divergence_ratio="1%",
            auto_derive=True,
        )
        res_decimal = calculate_sector_exhaustion(
            new_high_shrink_days=0,
            relay_risk=0,
            capital_spillover=0,
            divergence_ratio=0.01,
            auto_derive=True,
        )
        self.assertEqual(res_pct_str["value"], res_decimal["value"])
        self.assertAlmostEqual(res_pct_str["value"], 0.2, places=3)

        # 3. 100% 的明确形式：100 与 '100%' 均解析为 1.0
        res_100_num = calculate_sector_exhaustion(
            new_high_shrink_days=0,
            relay_risk=0,
            capital_spillover=0,
            divergence_ratio=100,
            auto_derive=True,
        )
        res_100_str = calculate_sector_exhaustion(
            new_high_shrink_days=0,
            relay_risk=0,
            capital_spillover=0,
            divergence_ratio="100%",
            auto_derive=True,
        )
        self.assertEqual(res_100_num["value"], 20.0)
        self.assertEqual(res_100_str["value"], 20.0)

        # 4. calculate_capital_continuity 支持带 % 字符串
        cap_pct = calculate_capital_continuity(amount_ratio=1.0, break_rate="25%")
        cap_dec = calculate_capital_continuity(amount_ratio=1.0, break_rate=0.25)
        self.assertEqual(cap_pct["value"], cap_dec["value"])


if __name__ == "__main__":
    unittest.main()
