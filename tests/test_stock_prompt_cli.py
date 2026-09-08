import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "stock_prompt.py"
SPEC = importlib.util.spec_from_file_location("stock_prompt_cli", MODULE)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


class StockPromptCLITest(unittest.TestCase):
    def test_version_reports_project_version(self):
        version = json.loads((MODULE.parents[1] / "version.json").read_text(encoding="utf-8"))["latest"]
        self.assertEqual(CLI.main(["--version"]), 0)

    def test_help_and_no_args_exit_zero(self):
        self.assertEqual(CLI.main([]), 0)
        self.assertEqual(CLI.main(["-h"]), 0)

    def test_unknown_command_is_rejected(self):
        self.assertEqual(CLI.main(["not-a-command"]), 2)

    def test_passthrough_delegates_to_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = dict(ENV, STOCK_PROMPT_STATE_DIR=temporary)
            completed = subprocess.run(
                [sys.executable, str(MODULE), "handoff", "latest"],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("N/A", completed.stdout)

    def test_version_flag_output_content(self):
        completed = subprocess.run(
            [sys.executable, str(MODULE), "--version"],
            capture_output=True, text=True, env=ENV,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("stock-prompt", completed.stdout)


class HandoffCleanBackupRetentionTest(unittest.TestCase):
    def test_clean_prunes_old_backups_but_keeps_recent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backups = root / ".backups"
            backups.mkdir()
            old_backup = backups / "handoff-20260901-daily-20260901-000000-000000.json"
            recent_backup = backups / "handoff-20260908-daily-20260908-000000-000000.json"
            old_backup.write_text("{}", encoding="utf-8")
            recent_backup.write_text("{}", encoding="utf-8")
            stale_time = (datetime.now() - timedelta(days=40)).timestamp()
            os.utime(old_backup, (stale_time, stale_time))

            store = self.load_store()
            argv = sys.argv
            try:
                sys.argv = ["handoff_store.py", "--state-dir", str(root),
                            "clean", "--older-than-days", "30", "--apply"]
                store.main()
            finally:
                sys.argv = argv
            self.assertFalse(old_backup.exists(), "超过保留周期的备份应被清理")
            self.assertTrue(recent_backup.exists(), "保留周期内的备份不应被删除")

    def load_store(self):
        module_path = MODULE.parents[1] / "scripts" / "handoff_store.py"
        spec = importlib.util.spec_from_file_location("handoff_store_clean", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


if __name__ == "__main__":
    unittest.main()
