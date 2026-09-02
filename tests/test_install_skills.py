import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install_skills.py"
SPEC = importlib.util.spec_from_file_location("install_skills", MODULE_PATH)
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallSkillsTest(unittest.TestCase):
    def test_manifest_cleanup_preserves_user_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "target"
            source = base / "SKILL.md"
            source.write_text("v1\n", encoding="utf-8")
            files = {"daily-review/SKILL.md": source}

            INSTALLER.install_to("test", root, files)
            user_file = root / "daily-review" / "my-notes.md"
            user_file.write_text("keep\n", encoding="utf-8")
            INSTALLER.install_to("test", root, {})

            self.assertFalse((root / "daily-review" / "SKILL.md").exists())
            self.assertEqual(user_file.read_text(encoding="utf-8"), "keep\n")

    def test_user_modified_managed_file_is_backed_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "target"
            source = base / "SKILL.md"
            source.write_text("v1\n", encoding="utf-8")
            files = {"stock-analysis/SKILL.md": source}
            INSTALLER.install_to("test", root, files)

            destination = root / "stock-analysis" / "SKILL.md"
            destination.write_text("user edit\n", encoding="utf-8")
            source.write_text("v2\n", encoding="utf-8")
            INSTALLER.install_to("test", root, files)

            backups = list((root / ".stock-prompt-backups").glob("*/stock-analysis/SKILL.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "user edit\n")
            self.assertEqual(destination.read_text(encoding="utf-8"), "v2\n")
            manifest = json.loads((root / INSTALLER.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertIn("stock-analysis/SKILL.md", manifest["hashes"])


if __name__ == "__main__":
    unittest.main()
