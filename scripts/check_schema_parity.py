#!/usr/bin/env python3
"""检查 Schema 资产、运行时必填字段和正式示例的一致性。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from project_registry import load_registry, resolve_path
from report_card.validation import REQUIRED_FIELDS, validate_report_data
from handoff_store import REQUIRED_FIELDS as HANDOFF_REQUIRED_FIELDS
from tools.artifacts.store import validate_artifact


TYPE_TO_SCHEMA = {
    "prediction": "report_card_prediction",
    "daily": "report_card_daily",
    "rotation": "report_card_rotation",
    "stock": "report_card_stock",
}


def collect_errors():
    registry = load_registry()
    errors = []
    for name, relative in registry.get("schemas", {}).items():
        path = resolve_path(relative)
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: Schema 无法读取: {exc}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{name}: 不是 Draft 2020-12 Schema")

    for name, relative in registry.get("artifacts", {}).items():
        path = resolve_path(relative)
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"artifact/{name}: Schema 无法读取: {exc}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"artifact/{name}: 不是 Draft 2020-12 Schema")

    skills = {item["id"]: item for item in registry["skills"]}
    for report_type, schema_name in TYPE_TO_SCHEMA.items():
        schema = json.loads(resolve_path(registry["schemas"][schema_name]).read_text(encoding="utf-8"))
        schema_required = set(schema.get("required", []))
        runtime_required = set(REQUIRED_FIELDS[report_type])
        if schema_required != runtime_required:
            errors.append(
                f"{report_type}: Schema/运行时必填字段漂移 "
                f"schema_only={sorted(schema_required - runtime_required)} "
                f"runtime_only={sorted(runtime_required - schema_required)}"
            )
        skill = skills["stock-analysis" if report_type == "stock" else (
            "market-prediction" if report_type == "prediction" else
            "daily-review" if report_type == "daily" else "sector-rotation"
        )]
        example = resolve_path(skill["source"]) / "references" / "report-card-example.json"
        try:
            data = json.loads(example.read_text(encoding="utf-8"))
            validate_report_data(report_type, data)
        except (OSError, ValueError) as exc:
            errors.append(f"{report_type}: 正式示例不合规: {exc}")
    handoff = json.loads(resolve_path(registry["schemas"]["handoff"]).read_text(encoding="utf-8"))
    if set(handoff.get("required", [])) != set(HANDOFF_REQUIRED_FIELDS):
        errors.append("handoff: Schema/运行时必填字段漂移")
    fixture_root = ROOT / "tests" / "fixtures" / "artifacts"
    fixtures = sorted(fixture_root.glob("*.json"))
    expected_fixture_count = len(registry.get("artifacts", {})) - 1  # base 仅是公共元数据约束
    if len(fixtures) != expected_fixture_count:
        errors.append(f"artifact fixtures: 期望 {expected_fixture_count} 份，实际 {len(fixtures)} 份")
    for fixture in fixtures:
        try:
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            fixture_errors = validate_artifact(payload)
        except (OSError, ValueError) as exc:
            errors.append(f"artifact fixture/{fixture.name}: 无法读取: {exc}")
            continue
        if fixture_errors:
            errors.append(f"artifact fixture/{fixture.name}: {'；'.join(fixture_errors)}")
    return errors


def main():
    errors = collect_errors()
    for error in errors:
        print(f"[FAIL] {error}")
    if errors:
        return 1
    print("[SUCCESS] Schema、运行时字段与正式示例一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
