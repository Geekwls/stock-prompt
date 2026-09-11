"""验证五个 Skill 均声明统一 Agent 首屏输出协议。"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("market-prediction", "daily-review", "sector-rotation", "stock-analysis", "stock-research-router")


class AgentOutputContractTest(unittest.TestCase):
    def test_all_skills_declare_summary_card_and_quality_fields(self):
        required = ("首屏摘要卡", "置信度", "覆盖率", "数据状态", "next_actions")
        for skill in SKILLS:
            text = (ROOT / ".agents" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            for marker in required:
                self.assertIn(marker, text, f"{skill} 缺少输出协议字段 {marker}")

    def test_public_contract_contains_summary_card_rules(self):
        text = (ROOT / "contracts" / "common-research-contract.md").read_text(encoding="utf-8")
        self.assertIn("summary_card", text)
        self.assertIn("coverage < 70%", text)


if __name__ == "__main__":
    unittest.main()
