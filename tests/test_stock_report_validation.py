import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_report_card.py"
SPEC = importlib.util.spec_from_file_location("generate_report_card", MODULE_PATH)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def valid_stock_data():
    data = {field: "x" for field in REPORT.REQUIRED_FIELDS["stock"]}
    planned = [25, 12, 10, 13, 20, 10, 10]
    obtained = [20, 10, 8, 12, 15, 5, 5]
    data.update({
        "coverage": "75%",
        "company_risk_status": "高",
        "hard_gate_status": "失败",
        "technical_layers_scored": False,
        "composite_score_status": "not_applicable",
        "structure_timing": "暂不评级",
        "confidence_level": "数据不足",
        "coverage_breakdown": [
            [f"group-{index}", f"{plan}%", f"{got}%", "F01", "无"]
            for index, (plan, got) in enumerate(zip(planned, obtained))
        ],
        "audit_status": "未经审计",
        "pledge_details": [["占总股本", "13.5%"], ["占控股股东持股", "84.1%"]],
        "company_details": [["财务", "已核验"]],
        "next_review_triggers": ["突破结构位", "发布定期报告"],
    })
    return data


class StockReportValidationTest(unittest.TestCase):
    def test_failed_market_gate_blocks_technical_scoring(self):
        data = valid_stock_data()
        data["technical_layers_scored"] = True
        with self.assertRaisesRegex(ValueError, "technical_layers_scored"):
            REPORT.validate_report_data("stock", data)

    def test_failed_market_gate_accepts_not_applicable_score(self):
        REPORT.validate_report_data("stock", valid_stock_data())

    def test_approximate_coverage_is_rejected(self):
        data = valid_stock_data()
        data["coverage"] = "约75%"
        with self.assertRaisesRegex(ValueError, "coverage"):
            REPORT.validate_report_data("stock", data)

    def test_unaudited_status_must_be_explicit(self):
        data = valid_stock_data()
        data["audit_status"] = "未发现非标"
        with self.assertRaisesRegex(ValueError, "audit_status"):
            REPORT.validate_report_data("stock", data)


class AllTypesValidationTest(unittest.TestCase):
    NON_STOCK_TYPES = ("prediction", "daily", "rotation")

    def test_minimal_complete_data_passes_for_non_stock_types(self):
        for report_type in self.NON_STOCK_TYPES:
            data = {field: "x" for field in REPORT.REQUIRED_FIELDS[report_type]}
            REPORT.validate_report_data(report_type, data)

    def test_missing_required_field_rejected_for_every_type(self):
        for report_type, fields in REPORT.REQUIRED_FIELDS.items():
            with self.subTest(report_type=report_type):
                data = valid_stock_data() if report_type == "stock" else {field: "x" for field in fields}
                data.pop(sorted(fields)[0])
                with self.assertRaisesRegex(ValueError, "缺少必要字段"):
                    REPORT.validate_report_data(report_type, data)

    def test_empty_list_counts_as_missing(self):
        data = {field: "x" for field in REPORT.REQUIRED_FIELDS["prediction"]}
        data["evidence"] = []
        with self.assertRaisesRegex(ValueError, "evidence"):
            REPORT.validate_report_data("prediction", data)

    def test_none_value_counts_as_missing(self):
        data = {field: "x" for field in REPORT.REQUIRED_FIELDS["daily"]}
        data["sentiment_breakdown"] = None
        with self.assertRaisesRegex(ValueError, "缺少必要字段"):
            REPORT.validate_report_data("daily", data)


if __name__ == "__main__":
    unittest.main()
