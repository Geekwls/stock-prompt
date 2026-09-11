import importlib.util
import json
import subprocess
import sys
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


class SourceFilesTest(unittest.TestCase):
    def test_bundled_scripts_map_to_masters(self):
        files = INSTALLER.source_files()
        for name, (source, skills) in INSTALLER.BUNDLED_SCRIPTS.items():
            for skill in skills:
                self.assertEqual(files[f"{skill}/scripts/{name}"], source)
        self.assertNotIn("sector-rotation/scripts/eval_tracker.py", files)
        self.assertNotIn("stock-analysis/scripts/eval_tracker.py", files)
        self.assertIn("stock-analysis/scripts/artifact_store.py", files)
        self.assertIn("tools/artifacts/store.py", files)
        self.assertIn("contracts/artifacts/base.schema.json", files)

    def test_workspace_sync_copies_bundled_scripts(self):
        with tempfile.TemporaryDirectory() as temporary:
            original_root = INSTALLER.SOURCE_ROOT
            original_repo = INSTALLER.ROOT
            try:
                INSTALLER.SOURCE_ROOT = Path(temporary)
                INSTALLER.ROOT = Path(temporary)
                changed = INSTALLER.sync_workspace_scripts(dry_run=False)
                self.assertGreaterEqual(changed, 1)
                for name, (_, skills) in INSTALLER.BUNDLED_SCRIPTS.items():
                    for skill in skills:
                        bundled = Path(temporary) / skill / "scripts" / name
                        self.assertTrue(bundled.is_file(), f"缺少捆绑副本: {bundled}")
            finally:
                INSTALLER.SOURCE_ROOT = original_root
                INSTALLER.ROOT = original_repo

    def test_installed_calculation_and_artifact_cli_are_self_contained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            INSTALLER.install_to("test-runtime", root, INSTALLER.source_files())
            calculation = subprocess.run(
                [
                    sys.executable, str(root / "daily-review" / "scripts" / "calculate.py"),
                    "calculate_atr_state", "--json",
                    '{"close":101,"previous_close":100,"atr14":2}',
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(calculation.returncode, 0, calculation.stderr)
            self.assertEqual(json.loads(calculation.stdout)["value"], "up")
            fixture = INSTALLER.ROOT / "tests" / "fixtures" / "artifacts" / "prediction.json"
            validation = subprocess.run(
                [
                    sys.executable, str(root / "daily-review" / "scripts" / "artifact_store.py"),
                    "validate", "--input", str(fixture),
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)


if __name__ == "__main__":
    unittest.main()
