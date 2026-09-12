import unittest

from tools.calculations.market import calculate_market_sentiment_score, calculate_opportunity_score, calculate_price_range
from tools.calculations.sector import calculate_5d_sentiment_score, calculate_capital_continuity, calculate_sector_exhaustion
from tools.calculations.stock import calculate_price_position, calculate_relative_strength, calculate_risk_reward, validate_stock_hard_gate


class CalculationAliasesTest(unittest.TestCase):
    def test_market_sentiment_weighting_missing_audit_and_cap(self):
        self.assertEqual(calculate_market_sentiment_score(60, 70, 60, 65, 75)["value"], 65.25)
        capped = calculate_market_sentiment_score(90, 90, 90, 90, 90, volume_dev=-5, up_ratio=60)
        self.assertEqual(capped["value"], 60.0)
        self.assertTrue(capped["cap_applied"])
        partial = calculate_market_sentiment_score(breadth_score=80, limit_score=60)
        self.assertEqual(partial["status"], "partial")
        self.assertIn("amount_score", partial["missing"])

    def test_market_and_sector_aliases(self):
        opportunity = calculate_opportunity_score(p_up=36, p_side=48, p_down=16, space_up=.7, space_down=.72, mainline_quality=80, capital_continuity=75, crowding=35)
        self.assertIsInstance(opportunity["value"], float)
        self.assertEqual(calculate_opportunity_score(sentiment_score=80, mainline_quality=70, capital_continuity=90, mode="close")["value"], 79.0)
        self.assertEqual(calculate_price_range(current_price=100, atr14=2, ma5=99)["value"]["r1"], 101.6)
        self.assertEqual(calculate_capital_continuity(turnover_ratio=1.2, blown_ratio=.25)["value"], 90.0)
        self.assertEqual(calculate_sector_exhaustion(price_divergence=30, relay_risk=20, capital_overflow=15)["value"], 65.0)

    def test_five_day_sentiment(self):
        self.assertAlmostEqual(calculate_5d_sentiment_score([50, 65, 55, 70, 68])["value"], 64.95)
        self.assertEqual(calculate_5d_sentiment_score([None, None, 55, 70, None])["status"], "unavailable")

    def test_stock_aliases(self):
        rs = calculate_relative_strength(stock_pct_5d=8.5, sector_pct_5d=2.1, index_pct_5d=-.8, stock_pct_20d=18.2, sector_pct_20d=6, index_pct_20d=1.2)
        self.assertEqual(rs["value"]["5"]["vs_benchmark"], 9.3)
        self.assertEqual(rs["value"]["20"]["vs_industry"], 12.2)
        self.assertEqual(calculate_price_position(close=15.2, ma20=14.1, ma50=13, atr14=.65, structure_level=14.3)["status"], "complete")
        self.assertAlmostEqual(calculate_risk_reward(current_price=15.2, stop_loss=14.3, target_conservative=17)["value"], 2.0)
        self.assertTrue(validate_stock_hard_gate(is_st=False, days_listed=450, kline_count=250, is_suspended=False)["value"])


if __name__ == "__main__":
    unittest.main()
