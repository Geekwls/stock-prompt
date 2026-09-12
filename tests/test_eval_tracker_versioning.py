import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "eval_tracker.py"
SPEC = importlib.util.spec_from_file_location("eval_tracker_versioned", MODULE)
TRACKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACKER)


class EvalTrackerVersioningTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
        os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = str(Path(self._tmp.name) / "artifacts")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("STOCK_PROMPT_ARTIFACT_DIR", None)
        else:
            os.environ["STOCK_PROMPT_ARTIFACT_DIR"] = self._prev
        self._tmp.cleanup()

    def test_record_writes_version_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = str(Path(temporary) / "predictions.jsonl")
            args = argparse.Namespace(
                date="2026-09-07", regime="S2", p_up=30, p_side=50, p_down=20,
                opportunity=50, top_sector="半导体", top_sectors="半导体,算力",
                r1=None, s1=None, ledger=ledger, model_version="7.0.0",
                formula_version="prediction-v2", source_snapshot="handoff-1",
            )
            with redirect_stdout(StringIO()):
                TRACKER.cmd_record(args)
            record = json.loads(Path(ledger).read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "1.0")
            self.assertEqual(record["model_version"], "7.0.0")
            self.assertEqual(record["source_snapshot"], "handoff-1")

    def test_load_filters_versions_without_mixing_same_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "predictions.jsonl"
            rows = [
                {"type": "prediction", "date": "2026-09-07", "model_version": "6.9.0", "probs": {}},
                {"type": "prediction", "date": "2026-09-07", "model_version": "7.0.0", "probs": {"up": 1}},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            preds, _ = TRACKER.load_ledger(str(path), "6.9.0")
            self.assertEqual(preds["2026-09-07"]["model_version"], "6.9.0")

    def test_migrate_marks_legacy_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "daily.jsonl"
            path.write_text(json.dumps({"type": "daily_review", "date": "2026-09-01"}) + "\n", encoding="utf-8")
            TRACKER.migrate_ledger.dry_run = False
            with redirect_stdout(StringIO()):
                changed = TRACKER.migrate_ledger(str(path))
            self.assertEqual(changed, 1)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["model_version"], "legacy")
            self.assertEqual(len(list(Path(temporary).glob("daily.jsonl.bak-*"))), 1)

