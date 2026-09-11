import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "build_release_assets.py"
SPEC = importlib.util.spec_from_file_location("build_release_assets", MODULE)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ReleaseAssetsTest(unittest.TestCase):
    def test_skill_bundle_contains_updater_and_release_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries, manifest = BUILDER.skill_files("7.5.0", root)
            entries[BUILDER.RELEASE_MANIFEST] = entries.pop(manifest.name)
            archive = root / "skills.zip"
            BUILDER.write_zip(archive, entries, "stock-prompt-skills-v7.5.0")
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                prefix = "stock-prompt-skills-v7.5.0/"
                self.assertIn(prefix + BUILDER.RELEASE_MANIFEST, names)
                for skill in BUILDER.install_skills.SKILL_NAMES:
                    self.assertIn(prefix + f"{skill}/scripts/update_manager.py", names)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["project_version"], "7.5.0")
            self.assertIn("stock-analysis/scripts/update_manager.py", payload["hashes"])


if __name__ == "__main__":
    unittest.main()
