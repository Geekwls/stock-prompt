import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "stock-research-router" / "SKILL.md"


class RouterSkillTest(unittest.TestCase):
    def test_router_is_narrow_and_points_to_all_specialists(self):
        text = SKILL.read_text(encoding="utf-8")
        for name in ("market-prediction", "daily-review", "sector-rotation", "stock-analysis"):
            self.assertIn(name, text)
        self.assertIn("不自行替代专业分析", text)
        self.assertIn("用户明确指定的任务优先于时间规则", text)

    def test_router_uses_programmatic_handoff(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("handoff_store.py latest", text)
        self.assertIn("handoff_store.py write --stdin", text)

