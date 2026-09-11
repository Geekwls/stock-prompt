import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "tools" / "artifacts" / "store.py"
SPEC = importlib.util.spec_from_file_location("artifact_store", MODULE)
STORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STORE)


def prediction(snapshot_id="prediction-20260911-preopen"):
    return {
        "artifact_type": "prediction",
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "trading_date": "2026-09-11",
        "as_of": "2026-09-11T09:10:00+08:00",
        "data_status": "partial",
        "coverage": "82.5%",
        "evidence_ids": ["F01", "F02"],
        "formula_version": "prediction-v1",
        "status": "partial",
        "stage": "PREOPEN_V1",
        "market_regime": "S2",
        "probabilities": {"up": 40, "side": 35, "down": 25},
        "opportunity_score": 68.5,
        "top_sectors": ["半导体", "通信设备"],
    }


class ArtifactStoreTest(unittest.TestCase):
    def test_all_committed_fixtures_are_valid(self):
        fixture_root = MODULE.parents[2] / "tests" / "fixtures" / "artifacts"
        fixtures = sorted(fixture_root.glob("*.json"))
        self.assertEqual(len(fixtures), 7)
        for fixture in fixtures:
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            self.assertEqual(STORE.validate_artifact(payload), [], fixture.name)

    def test_validates_and_round_trips_immutable_snapshot(self):
        payload = prediction()
        self.assertEqual(STORE.validate_artifact(payload), [])
        with tempfile.TemporaryDirectory() as temporary:
            path = STORE.save_artifact(payload, temporary)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            saved = STORE.load_artifact(payload["snapshot_id"], temporary)
            self.assertEqual(saved["probabilities"], payload["probabilities"])
            self.assertIn("created_at", saved)
            with self.assertRaisesRegex(FileExistsError, "不可覆盖"):
                STORE.save_artifact(payload, temporary)

    def test_rejects_invalid_probability_and_common_metadata(self):
        payload = prediction()
        payload["probabilities"] = {"up": 70, "side": 40, "down": 5}
        payload["coverage"] = "大部分"
        errors = STORE.validate_artifact(payload)
        self.assertTrue(any("合计" in error for error in errors))
        self.assertTrue(any("coverage" in error for error in errors))

    def test_auction_must_reference_distinct_preopen_snapshot(self):
        payload = prediction("auction-20260911")
        payload.update({
            "artifact_type": "auction",
            "stage": "AUCTION_V2",
            "parent_snapshot_id": "auction-20260911",
            "posterior_probabilities": payload.pop("probabilities"),
            "information_delta": [],
        })
        payload.pop("market_regime")
        payload.pop("opportunity_score")
        payload.pop("top_sectors")
        self.assertTrue(any("独立" in error for error in STORE.validate_artifact(payload)))

    def test_latest_filters_subject_and_skips_corrupt_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for code, stamp in (("300308", "1500"), ("600519", "1510")):
                payload = {
                    **prediction(f"stock-{code}-{stamp}"),
                    "artifact_type": "stock_diagnostic",
                    "subject": {"type": "stock", "id": code, "name": code},
                    "layers": {},
                    "logic_health": "稳定",
                    "structure_position": "区间中部",
                    "confidence": "中",
                    "confirmation_conditions": [],
                    "invalidation_conditions": [],
                }
                for key in ("stage", "market_regime", "probabilities", "opportunity_score", "top_sectors"):
                    payload.pop(key)
                STORE.save_artifact(payload, root)
            (root / "corrupt.json").write_text("not-json", encoding="utf-8")
            selected = STORE.select_artifacts(root, artifact_type="stock_diagnostic", subject="600519")
            self.assertEqual([item["subject"]["id"] for item in selected], ["600519"])

    def test_cli_validate_returns_nonzero_for_bad_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text(json.dumps({"artifact_type": "prediction"}), encoding="utf-8")
            self.assertEqual(STORE.main(["validate", "--input", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
