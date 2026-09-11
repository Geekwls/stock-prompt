import unittest

from tools.calculations.market import (
    calculate_atr_state,
    calculate_bayesian_posterior,
    calculate_opportunity_score,
    calculate_price_range,
)
from tools.calculations.metrics import calculate_interval_score, calculate_multiclass_brier, calculate_ndcg
from tools.calculations.sector import calculate_capital_continuity, calculate_sector_exhaustion
from tools.calculations.stock import calculate_relative_strength, calculate_risk_reward, validate_stock_hard_gate


class MarketCalculationsTest(unittest.TestCase):
    def test_atr_boundaries_match_skill_contract(self):
        self.assertEqual(calculate_atr_state(100.3, 100, 1)["value"], "up")
        self.assertEqual(calculate_atr_state(99.701, 100, 1)["value"], "side")
        self.assertEqual(calculate_atr_state(99.7, 100, 1)["value"], "down")
        self.assertEqual(calculate_atr_state(101, 100, 0)["status"], "unavailable")

    def test_bayesian_update_normalizes_and_caps(self):
        output = calculate_bayesian_posterior(
            {"up": 60, "side": 30, "down": 10},
            [{"up": 10, "side": 0.5, "down": 0.1}],
        )
        self.assertAlmostEqual(sum(output["value"].values()), 100.0)
        self.assertLessEqual(output["value"]["up"], 80.0)

    def test_preopen_and_close_opportunity_are_distinct(self):
        preopen = calculate_opportunity_score(
            {"up": 60, "side": 30, "down": 10}, 8, 4, 80, 90, 20,
        )
        close = calculate_opportunity_score(80, mainline_quality=70, capital_continuity=90, mode="close")
        self.assertEqual(preopen["formula_version"], "opportunity-preopen-v1")
        self.assertEqual(close["value"], 79.0)
        self.assertEqual(calculate_opportunity_score(80, mainline_quality=70, capital_continuity=90, mode="close", brake_flags=4)["value"], 35.0)

    def test_price_range(self):
        self.assertEqual(calculate_price_range(100, 2)["value"], {"r1": 101.6, "s1": 98.4, "r2": 103.0, "s2": 97.0})


class SectorAndStockCalculationsTest(unittest.TestCase):
    def test_capital_continuity_and_small_sample_degrade(self):
        self.assertEqual(calculate_capital_continuity(1.2, 0.25, 4)["value"], 90.0)
        degraded = calculate_capital_continuity(0.8, 0.1, 2)
        self.assertEqual(degraded["value"], 80.0)
        self.assertEqual(degraded["status"], "partial")

    def test_sector_exhaustion(self):
        output = calculate_sector_exhaustion(30, 20, 15)
        self.assertEqual(output["value"], 65.0)
        self.assertEqual(output["state"], "exhausted")

    def test_stock_gate_rs_and_risk_reward(self):
        self.assertTrue(validate_stock_hard_gate(120, True, True, True)["value"])
        self.assertFalse(validate_stock_hard_gate(80, True, True, False)["value"])
        stock = list(range(100, 121))
        benchmark = list(range(100, 121))
        industry = list(range(100, 121))
        self.assertEqual(calculate_relative_strength(stock, benchmark, industry, windows=(5,))["value"]["5"]["vs_benchmark"], 0.0)
        self.assertAlmostEqual(calculate_risk_reward(100, 95, [112, 120], friction=1)["value"], 11 / 6, places=6)


class MetricCalculationsTest(unittest.TestCase):
    def test_brier_matches_existing_ledger_convention(self):
        self.assertAlmostEqual(calculate_multiclass_brier({"up": 60, "side": 30, "down": 10}, "up")["value"], 0.26)

    def test_interval_and_ndcg(self):
        self.assertEqual(calculate_interval_score(90, 110, 100)["value"], 20)
        self.assertEqual(calculate_ndcg(["a", "b"], {"a": 3, "b": 1})["value"], 1.0)


if __name__ == "__main__":
    unittest.main()
