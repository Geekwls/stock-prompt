# -*- coding: utf-8 -*-
"""板块轮动逻辑修复回归测试。

对应「交易员视角审计」提出的 P0/P1 修复项：
- assess_rotation_effectiveness 取消乐观默认值（缺参必须 unavailable，而非静默判定主线聚焦）；
- calculate_sector_cannibalization 分类互斥有序，broad_retreat / concentrated_mainline 可达；
- validate_sector_capacity 修复 mega 判定的 OR 后门，并支持成交额基准归一化；
- calculate_rotation_state 补齐 state_2「畏高切低」证据状态；
- map_capital_seesaw_matrix 显式披露结论是规则推演还是已核验证据；
- 新增 calculate_rotation_migration（持续流入 vs 单日爆量）与 map_exhaustion_to_lifecycle（SEI 与生命周期一致性）；
- calculate_5d_sentiment_score 权重单调性校验；
- calculate_sector_ranking 缺失评分板块排序兜底。
"""

import unittest

from tools.calculations.sector import (
    assess_rotation_effectiveness,
    calculate_5d_sentiment_score,
    calculate_rotation_migration,
    calculate_rotation_state,
    calculate_sector_cannibalization,
    calculate_sector_ranking,
    map_capital_seesaw_matrix,
    map_exhaustion_to_lifecycle,
    validate_sector_capacity,
)


class RotationEffectivenessNoOptimisticDefaultTest(unittest.TestCase):
    def test_missing_inputs_return_unavailable(self):
        """任一输入缺失都不得静默给出「主线聚焦 / 有效」的乐观结论。"""
        for kwargs in (
            {},
            {"active_sectors_count": 3},
            {"leader_turnover_share": 9.0, "limit_up_clusters": 4},
            {"market_amount_ratio": 1.1},
            {"active_sectors_count": 2, "leader_turnover_share": 9.5},
        ):
            res = assess_rotation_effectiveness(**kwargs)
            self.assertEqual(res["status"], "unavailable", msg=str(kwargs))
            self.assertEqual(res["value"], "N/A")
            self.assertTrue(res["missing"])
        self.assertEqual(
            assess_rotation_effectiveness()["formula_version"], "rotation-effectiveness-v2"
        )

    def test_explicit_mainline_still_detected(self):
        res = assess_rotation_effectiveness(
            active_sectors_count=2,
            leader_turnover_share=9.5,
            limit_up_clusters=4,
            market_amount_ratio=1.1,
        )
        self.assertEqual(res["status"], "complete")
        self.assertEqual(res["value"]["rotation_type"], "mainline_focused")


class SectorCannibalizationClassificationTest(unittest.TestCase):
    def test_broad_retreat_reachable(self):
        """普跌退潮：失血严重、缩量且无强主线承接 —— 历史死分支现已可达。"""
        res = calculate_sector_cannibalization(
            leader_sector_turnover_share=5.0,
            market_amount_ratio=0.9,
            outflow_sectors_loss_rate=2.6,
        )
        self.assertEqual(res["value"]["market_dynamic"], "broad_retreat")

    def test_concentrated_mainline_new_state(self):
        """缩量 + 强主线 + 轻微失血 = 最健康的主线聚焦形态。"""
        res = calculate_sector_cannibalization(
            leader_sector_turnover_share=9.0,
            market_amount_ratio=0.98,
            outflow_sectors_loss_rate=1.0,
        )
        self.assertEqual(res["value"]["market_dynamic"], "concentrated_mainline")

    def test_siphon_extreme_requires_strong_leader(self):
        """缩量 + 明显失血时，只有强主线承接（leader_share >= 8）才算吸血极化。"""
        weak = calculate_sector_cannibalization(
            leader_sector_turnover_share=6.0,
            market_amount_ratio=0.98,
            outflow_sectors_loss_rate=2.1,
        )
        self.assertEqual(weak["value"]["market_dynamic"], "broad_retreat")
        strong = calculate_sector_cannibalization(
            leader_sector_turnover_share=12.0,
            market_amount_ratio=0.98,
            outflow_sectors_loss_rate=2.1,
        )
        self.assertEqual(strong["value"]["market_dynamic"], "siphon_extreme")

    def test_missing_inputs_unavailable(self):
        self.assertEqual(calculate_sector_cannibalization()["status"], "unavailable")
        self.assertEqual(
            calculate_sector_cannibalization()["formula_version"], "sector-cannibalization-v2"
        )


class SectorCapacityOrBackdoorTest(unittest.TestCase):
    def test_mega_requires_both_share_and_absolute(self):
        """份额不足 4% 但绝对额达标，只能算标准主线，不得混入超级主线。"""
        res = validate_sector_capacity(sector_amount_yi=400.0, market_total_amount_yi=20000.0)
        self.assertEqual(res["value"]["amount_share_pct"], 2.0)
        self.assertEqual(res["value"]["capacity_type"], "standard_mainline")

    def test_baseline_normalization(self):
        """提供成交额基准后，绝对额门槛按 baseline / 10000 同比缩放。"""
        res = validate_sector_capacity(
            sector_amount_yi=400.0,
            market_total_amount_yi=20000.0,
            market_amount_baseline_yi=20000.0,
        )
        self.assertEqual(res["value"]["standard_amount_threshold_yi"], 360.0)
        self.assertIn("normalized_to_baseline", res["value"]["threshold_basis"])
        self.assertEqual(res["value"]["capacity_type"], "standard_mainline")

    def test_mega_when_both_hold(self):
        res = validate_sector_capacity(sector_amount_yi=1500.0, market_total_amount_yi=20000.0)
        self.assertEqual(res["value"]["capacity_type"], "mega_mainline")
        self.assertTrue(res["value"]["is_mainline_eligible"])

    def test_invalid_baseline_unavailable(self):
        res = validate_sector_capacity(
            sector_amount_yi=400.0, market_total_amount_yi=20000.0, market_amount_baseline_yi=0
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("market_amount_baseline_yi", res["missing"])


class RotationStateEvidenceTest(unittest.TestCase):
    def test_state2_high_to_low_status(self):
        confirmed = calculate_rotation_state(high_level_selloff=True, low_position_inflow=True)
        self.assertEqual(confirmed["value"], "state_2")
        self.assertEqual(confirmed["high_to_low_status"], "confirmed")

        failed = calculate_rotation_state(high_level_selloff=True, low_position_inflow=False)
        self.assertEqual(failed["high_to_low_status"], "failed")

        unverified = calculate_rotation_state(high_level_selloff=True)
        self.assertEqual(unverified["high_to_low_status"], "unverified")

    def test_state1_has_no_high_to_low_status(self):
        res = calculate_rotation_state(core_share=9.0, positive_days=4)
        self.assertEqual(res["value"], "state_1")
        self.assertIsNone(res["high_to_low_status"])

    def test_insufficient_evidence_unavailable(self):
        res = calculate_rotation_state(defensive_flow=True)
        self.assertEqual(res["status"], "unavailable")
        self.assertEqual(res["formula_version"], "rotation-state-rules-v2")


class CapitalSeesawEvidenceTest(unittest.TestCase):
    def test_rule_only_by_default(self):
        res = map_capital_seesaw_matrix(current_mainline="AI算力与CPO", current_lifecycle="retreat")
        self.assertEqual(res["value"]["evidence_status"], "unverified_rule_only")
        self.assertIsNone(res["value"]["counterpart_evidence"])
        self.assertIn("ai", res["value"]["matched_keywords"])
        self.assertIn("不得表述为已发生事实", res["value"]["evidence_note"])

    def test_verified_when_counterpart_supplied(self):
        res = map_capital_seesaw_matrix(
            current_mainline="AI算力与CPO",
            current_lifecycle="retreat",
            counterpart_change_pct=1.8,
            counterpart_net_flow_yi=32.0,
        )
        self.assertEqual(res["value"]["evidence_status"], "verified")
        self.assertEqual(res["value"]["counterpart_evidence"]["net_flow_yi"], 32.0)
        self.assertEqual(res["formula_version"], "capital-seesaw-matrix-v2")

    def test_unmatched_mainline_has_empty_keywords(self):
        res = map_capital_seesaw_matrix(current_mainline="未知题材", current_lifecycle="retreat")
        self.assertEqual(res["value"]["matched_keywords"], [])
        self.assertTrue(res["value"]["seesaw_counterpart"])


class RotationMigrationTest(unittest.TestCase):
    def test_persistence_and_spike_separation(self):
        rankings = [
            ["半导体", "通信", "医药", "有色", "军工"],
            ["半导体", "通信", "医药", "有色", "军工"],
            ["半导体", "通信", "医药", "有色", "军工"],
            ["半导体", "通信", "医药", "有色", "军工"],
            ["半导体", "通信", "医药", "AI应用", "算力"],
        ]
        res = calculate_rotation_migration(rankings, top_n=5)
        self.assertEqual(res["status"], "complete")
        value = res["value"]
        self.assertEqual(value["days_observed"], 5)
        self.assertAlmostEqual(value["persistence_ratio"]["半导体"], 1.0)
        self.assertAlmostEqual(value["persistence_ratio"]["有色"], 0.8)
        self.assertIn("半导体", value["sustained_sectors"])
        self.assertEqual(set(value["one_day_spike_sectors"]), {"AI应用", "算力"})
        self.assertEqual(value["entrants_vs_first_day"], ["AI应用", "算力"])
        self.assertEqual(value["exits_vs_first_day"], ["军工", "有色"])

    def test_requires_three_observed_days(self):
        res = calculate_rotation_migration([["A", "B"], None, ["A"], None, None])
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("observed_days>=3", res["missing"])

    def test_invalid_top_n_and_shapes(self):
        self.assertEqual(calculate_rotation_migration([["A"]], top_n=0)["status"], "unavailable")
        with self.assertRaises(ValueError):
            calculate_rotation_migration([["A"], ["B"], "not-a-list"])
        with self.assertRaises(ValueError):
            calculate_rotation_migration([[{"no_name": 1}], ["A"], ["A"]])


class ExhaustionLifecycleMapTest(unittest.TestCase):
    def test_band_lookup_and_consistency(self):
        consistent = map_exhaustion_to_lifecycle(sei=55, lifecycle_state="高位分歧")
        self.assertEqual(consistent["value"]["band"], "31-60")
        self.assertTrue(consistent["value"]["consistent"])

        conflict = map_exhaustion_to_lifecycle(sei=55, lifecycle_state="启动期")
        self.assertFalse(conflict["value"]["consistent"])
        self.assertIn("conflict_note", conflict["value"])

    def test_lifecycle_only_returns_candidate_bands(self):
        res = map_exhaustion_to_lifecycle(lifecycle_state="退潮期")
        bands = {item["band"] for item in res["value"]["candidate_sei_bands"]}
        self.assertEqual(bands, {"61-80", "81-100"})

    def test_both_missing_unavailable(self):
        res = map_exhaustion_to_lifecycle()
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("sei_or_lifecycle_state", res["missing"])


class SentimentWeightsMonotonicTest(unittest.TestCase):
    def test_reject_descending_weights(self):
        with self.assertRaises(ValueError) as ctx:
            calculate_5d_sentiment_score(
                [50, 60, 70, 80, 90], weights=[0.40, 0.30, 0.20, 0.05, 0.05]
            )
        self.assertIn("非递减", str(ctx.exception))

    def test_ascending_weights_ok(self):
        res = calculate_5d_sentiment_score([50, 60, 70, 80, 90])
        self.assertEqual(res["status"], "complete")


class SectorRankingNoneSortTest(unittest.TestCase):
    def test_missing_score_sorts_last(self):
        res = calculate_sector_ranking([
            {"id": "low", "strength": 30, "flow": 30, "breadth": 30, "continuity": 30},
            {"id": "missing"},
            {"id": "high", "strength": 90, "flow": 90, "breadth": 90, "continuity": 90},
        ])
        ids = [item["id"] for item in res["value"]]
        self.assertEqual(ids, ["high", "low", "missing"])


if __name__ == "__main__":
    unittest.main()
