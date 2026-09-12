import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "update_manager.py"
SPEC = importlib.util.spec_from_file_location("update_manager", MODULE)
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


class UpdateManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "update.json"
        self.env = patch.dict(os.environ, {"STOCK_PROMPT_UPDATE_CACHE": str(self.cache)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_semantic_version_comparison(self):
        self.assertGreater(UPDATER.version_key("v7.5.0"), UPDATER.version_key("7.4.9"))
        self.assertEqual(UPDATER.version_key("7.4"), UPDATER.version_key("7.4.0"))
        self.assertEqual(UPDATER.version_key("invalid"), ())

    def test_check_uses_daily_cache(self):
        current_major = UPDATER.version_key(UPDATER.runtime_metadata()["version"])[0]
        remote = json.dumps({"latest": f"{current_major + 1}.0.0", "channel": "stable"}).encode()
        with patch.object(UPDATER, "fetch_bytes", return_value=remote) as fetch:
            first = UPDATER.check_update(force=False, max_age_hours=24)
            second = UPDATER.check_update(force=False, max_age_hours=24)
        self.assertTrue(first["update_available"])
        self.assertTrue(second["cached"])
        self.assertEqual(fetch.call_count, 1)

    def test_apply_requires_explicit_yes(self):
        info = {"status": "ok", "local_version": "7.5.0", "latest_version": "7.6.0",
                "update_available": True}
        with patch.object(UPDATER, "check_update", return_value=info):
            args = UPDATER.parser().parse_args(["apply"])
            self.assertEqual(args.func(args), 2)

    def test_checksum_verification(self):
        path = Path(self.tmp.name) / "asset.zip"
        path.write_bytes(b"release")
        sums = f"{UPDATER.sha256(path)}  asset.zip\n".encode()
        UPDATER.verify_checksum(path, sums, "asset.zip")
        with self.assertRaises(ValueError):
            UPDATER.verify_checksum(path, b"0  asset.zip\n", "asset.zip")

    def test_zip_install_checks_latest_published_release(self):
        with patch.object(UPDATER, "ROOT", Path(self.tmp.name)):
            self.assertIn("api.github.com/repos/", UPDATER.remote_version_url("owner/repo"))

    def test_safe_extract_rejects_path_traversal(self):
        archive = Path(self.tmp.name) / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../outside.txt", "bad")
        with self.assertRaises(ValueError):
            UPDATER.safe_extract(archive, Path(self.tmp.name) / "extract")


if __name__ == "__main__":
    unittest.main()
