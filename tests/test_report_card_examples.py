"""四个技能的战报长图 JSON 示例必须始终通过脚本校验。

示例文件被 SKILL.md 直接引用（“可直接复制修改后传入 --json”），
一旦校验失败会形成试错循环，因此在测试中强制把关。
"""

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_report_card.py"
SPEC = importlib.util.spec_from_file_location("generate_report_card", MODULE_PATH)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)

EXAMPLES = {
    "prediction": ROOT / ".agents" / "skills" / "market-prediction" / "references" / "report-card-example.json",
    "daily": ROOT / ".agents" / "skills" / "daily-review" / "references" / "report-card-example.json",
    "rotation": ROOT / ".agents" / "skills" / "sector-rotation" / "references" / "report-card-example.json",
    "stock": ROOT / ".agents" / "skills" / "stock-analysis" / "references" / "report-card-example.json",
}


class ReportCardExampleTest(unittest.TestCase):
    def test_all_examples_exist(self):
        for report_type, path in EXAMPLES.items():
            with self.subTest(report_type=report_type):
                self.assertTrue(path.is_file(), f"缺少示例文件: {path}")

    def test_all_examples_pass_validation(self):
        for report_type, path in EXAMPLES.items():
            with self.subTest(report_type=report_type):
                data = json.loads(path.read_text(encoding="utf-8"))
                REPORT.validate_report_data(report_type, data)


if __name__ == "__main__":
    unittest.main()
