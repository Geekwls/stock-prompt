import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_prompts.py"
SPEC = importlib.util.spec_from_file_location("sync_prompts", MODULE_PATH)
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


def make_skill(directory, reference_text="共享内容\n", extra_body=""):
    skill_dir = Path(directory) / "stock-analysis"
    references = skill_dir / "references"
    references.mkdir(parents=True)
    (references / "common-research-contract.md").write_text(reference_text, encoding="utf-8")
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: stock-analysis\ndescription: 测试\n---\n\n# 标题\n\n"
        "<!-- PROMPT_INCLUDE: references/common-research-contract.md -->\n" + extra_body,
        encoding="utf-8",
    )
    return skill_file


class PromptBodyTest(unittest.TestCase):
    def test_frontmatter_stripped_and_include_expanded(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill_file = make_skill(temporary, reference_text="契约正文\n")
            prompt = SYNC.prompt_body(skill_file.read_text(encoding="utf-8"), skill_file)
            self.assertNotIn("name: stock-analysis", prompt)
            self.assertIn("# 标题", prompt)
            self.assertIn("契约正文", prompt)
            self.assertIn("已从 references/common-research-contract.md 展开", prompt)

    def test_missing_include_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill_file = Path(temporary) / "SKILL.md"
            skill_file.write_text(
                "---\nname: x\n---\n\n# T\n\n<!-- PROMPT_INCLUDE: references/missing.md -->\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "引用文件不存在"):
                SYNC.prompt_body(skill_file.read_text(encoding="utf-8"), skill_file)

    def test_escaping_include_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill_file = Path(temporary) / "SKILL.md"
            skill_file.write_text(
                "---\nname: x\n---\n\n# T\n\n<!-- PROMPT_INCLUDE: ../outside.md -->\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "引用越出 Skill 目录"):
                SYNC.prompt_body(skill_file.read_text(encoding="utf-8"), skill_file)

    def test_missing_frontmatter_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill_file = Path(temporary) / "SKILL.md"
            skill_file.write_text("# 没有_frontmatter\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frontmatter"):
                SYNC.prompt_body(skill_file.read_text(encoding="utf-8"), skill_file)


if __name__ == "__main__":
    unittest.main()
