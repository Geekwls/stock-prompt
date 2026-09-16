"""个股生态分型、数据模式和用户状态的确定性测试。"""

import unittest

from tools.calculations.stock import (
    assess_wyckoff_applicability,
    calculate_chip_structure,
    classify_stock_archetype,
    resolve_stock_data_mode,
    select_stock_model,
    summarize_seat_evidence,
    validate_position_context,
    validate_stock_hard_gate,
)


class StockDataModeTest(unittest.TestCase):
    def test_full_mode_requires_120_adjusted_bars_and_two_baselines(self):
        output = resolve_stock_data_mode(120, True, True, True)
        self.assertEqual(output["value"]["mode"], "full")
        self.assertTrue(output["value"]["tradable"])
        self.assertTrue(validate_stock_hard_gate(120, True, True, True)["value"])

    def test_80_bars_use_reduced_mode_instead_of_abandoning_analysis(self):
        output = resolve_stock_data_mode(80, True, True, False)
        self.assertEqual(output["value"]["mode"], "reduced")
        self.assertIn("conditional_scenarios", output["value"]["allowed"])
        self.assertIn("composite_score", output["value"]["forbidden"])

    def test_new_or_event_stock_uses_event_mode(self):
        output = resolve_stock_data_mode(
            12, True, False, False, days_listed=12, event_driven=True,
            quote_available=True, timeline_available=True, turnover_available=True,
        )
        self.assertEqual(output["value"]["mode"], "event")
        self.assertEqual(output["status"], "complete")
        self.assertNotIn("composite_score", output["value"]["allowed"])

    def test_suspended_event_can_research_facts_but_not_execution(self):
        output = resolve_stock_data_mode(300, True, True, True, is_suspended=True)
        self.assertFalse(output["value"]["tradable"])
        self.assertIn("intraday_execution", output["value"]["forbidden"])


class StockArchetypeTest(unittest.TestCase):
    def test_each_archetype_selects_its_own_model(self):
        cases = (
            ({"limit_up_streak": 3, "sector_role": "核心龙头", "turnover_rate": 22}, "sentiment_leader", "sentiment-v1"),
            ({"trend_alignment": "bullish", "institutional_net_buy": 1, "sector_role": "容量中军"}, "institutional_trend", "institutional-trend-v1"),
            ({"dividend_yield": 4.2, "payout_stable": True, "operating_cashflow_positive": True}, "dividend_value", "dividend-value-v1"),
            ({"event_driven": True, "resumed_recently": True}, "event_special", "event-special-v1"),
        )
        for arguments, archetype, model in cases:
            with self.subTest(archetype=archetype):
                classified = classify_stock_archetype(**arguments)
                self.assertEqual(classified["value"]["archetype"], archetype)
                self.assertEqual(classified["value"]["model_selected"], model)

    def test_ambiguous_archetype_retains_competing_alternative(self):
        output = classify_stock_archetype(event_driven=True, limit_up_streak=2)
        self.assertEqual(output["value"]["confidence"], "低")
        self.assertTrue(output["value"]["alternatives"])

    def test_model_scores_are_same_model_only_and_disabled_outside_full(self):
        full = select_stock_model("sentiment_leader", "full")
        reduced = select_stock_model("sentiment_leader", "reduced")
        self.assertEqual(full["value"]["score_comparability"], "same_model_same_version_only")
        self.assertFalse(reduced["value"]["score_enabled"])


class StructureAndUserContextTest(unittest.TestCase):
    def test_wyckoff_is_not_applicable_to_event_or_continuous_limit_up(self):
        event = assess_wyckoff_applicability("event", event_driven=True)
        streak = assess_wyckoff_applicability("full", range_days=60, limit_up_streak=3)
        self.assertEqual(event["value"]["applicability"], "not_applicable")
        self.assertFalse(streak["value"]["use_in_score"])

    def test_position_context_routes_profit_loss_and_unknown(self):
        loss = validate_position_context("holding_loss", 18.2, 30, "short_swing", "medium")
        unknown = validate_position_context()
        self.assertEqual(loss["value"]["scenario"], "recovery_and_risk_reduction_plan")
        self.assertTrue(loss["value"]["personalized_actions_allowed"])
        self.assertFalse(unknown["value"]["personalized_actions_allowed"])

    def test_seat_identity_is_not_guessed(self):
        output = summarize_seat_evidence([
            {"seat_name": "机构专用", "net_buy": 10},
            {"seat_name": "某证券拉萨营业部", "net_buy": 20},
        ])
        self.assertEqual(len(output["value"]["institutional"]), 1)
        self.assertEqual(len(output["value"]["unclassified"]), 1)
        self.assertIn("不得自动标记", output["value"]["identity_boundary"])

    def test_chip_metrics_require_traceable_source_and_time(self):
        unavailable = calculate_chip_structure(profit_ratio=80)
        complete = calculate_chip_structure(profit_ratio=80, data_source="auditable", as_of="2026-09-16")
        self.assertEqual(unavailable["status"], "partial")
        self.assertEqual(complete["status"], "complete")


if __name__ == "__main__":
    unittest.main()
