#!/usr/bin/env python3
"""基于 registry 中 JSON Schema 的零额外依赖 Artifact 校验与不可变存储。"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


TYPE_NAMES = {
    "string": str,
    "object": dict,
    "array": list,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


def project_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "registry.json").is_file():
            return parent
        runtime = parent / ".stock-prompt-runtime.json"
        if runtime.is_file():
            return parent
    raise RuntimeError("未找到 registry.json 或 .stock-prompt-runtime.json")


def load_registry():
    root = project_root()
    path = root / "registry.json"
    if not path.is_file():
        path = root / ".stock-prompt-runtime.json"
    return root, json.loads(path.read_text(encoding="utf-8"))


def schema_for(artifact_type):
    root, registry = load_registry()
    relative = registry.get("artifacts", {}).get(artifact_type)
    if not relative:
        raise ValueError(f"未知 artifact_type: {artifact_type}")
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _type_ok(value, expected):
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        python_type = TYPE_NAMES.get(name)
        if python_type is None:
            continue
        if name in {"number", "integer"} and isinstance(value, bool):
            continue
        if isinstance(value, python_type):
            return True
    return False


def _validate_node(value, rule, path, errors):
    if "type" in rule and not _type_ok(value, rule["type"]):
        errors.append(f"{path} 类型错误，期望 {rule['type']}")
        return
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path} 必须为 {rule['const']}")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path} 不在允许枚举内")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path} 长度不足")
        if rule.get("pattern") and not re.fullmatch(rule["pattern"], value):
            errors.append(f"{path} 格式不匹配")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{path} 小于最小值 {rule['minimum']}")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{path} 大于最大值 {rule['maximum']}")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{path} 数量不足")
        if "maxItems" in rule and len(value) > rule["maxItems"]:
            errors.append(f"{path} 数量超过上限")
        if rule.get("uniqueItems") and len({json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value}) != len(value):
            errors.append(f"{path} 存在重复项")
        if isinstance(rule.get("items"), dict):
            for index, item in enumerate(value):
                _validate_node(item, rule["items"], f"{path}[{index}]", errors)
    if isinstance(value, dict):
        for required in rule.get("required", []):
            if required not in value:
                errors.append(f"{path}.{required} 缺失")
        for key, child_rule in rule.get("properties", {}).items():
            if key in value:
                _validate_node(value[key], child_rule, f"{path}.{key}", errors)
        if rule.get("additionalProperties") is False:
            unexpected = set(value) - set(rule.get("properties", {}))
            for key in sorted(unexpected):
                errors.append(f"{path}.{key} 为未声明字段")


def validate_artifact(payload):
    if not isinstance(payload, dict):
        return ["Artifact 根节点必须是对象"]
    try:
        base_schema = schema_for("base")
        artifact_type = payload.get("artifact_type")
        if artifact_type in (None, "base"):
            raise ValueError(f"未知 artifact_type: {artifact_type}")
        schema = schema_for(artifact_type)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors = []
    _validate_node(payload, base_schema, "$", errors)
    _validate_node(payload, schema, "$", errors)
    probabilities = payload.get("probabilities") or payload.get("posterior_probabilities")
    if probabilities is not None:
        values = [probabilities.get(name) for name in ("up", "side", "down")]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in values):
            errors.append("概率必须是非负数")
        elif abs(sum(values) - 100.0) > 0.05:
            errors.append("up/side/down 概率合计必须为 100")
    if payload.get("artifact_type") == "auction" and payload.get("parent_snapshot_id") == payload.get("snapshot_id"):
        errors.append("Auction Artifact 必须引用独立的 PREOPEN 快照")
    return errors


def state_root(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    override = os.environ.get("STOCK_PROMPT_ARTIFACT_DIR")
    return Path(override).expanduser() if override else Path.home() / ".stock-prompt" / "artifacts"


def save_artifact(payload, root=None):
    errors = validate_artifact(payload)
    if errors:
        raise ValueError("；".join(errors))
    snapshot_id = str(payload["snapshot_id"])
    if not SAFE_ID.fullmatch(snapshot_id):
        raise ValueError("snapshot_id 只能包含字母、数字、点、下划线或连字符")
    root = state_root(root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    destination = root / f"{snapshot_id}.json"
    if destination.exists():
        raise FileExistsError(f"Artifact 不可覆盖: {snapshot_id}")
    enriched = dict(payload)
    enriched.setdefault("created_at", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{snapshot_id}.", dir=str(root))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(enriched, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise FileExistsError(f"Artifact 不可覆盖: {snapshot_id}") from None
        except (AttributeError, OSError):
            # 某些文件系统不支持硬链接；独占创建仍能保证不会覆盖既有快照。
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            output = os.open(destination, flags, 0o600)
            try:
                with os.fdopen(output, "wb") as stream, open(temporary, "rb") as source:
                    stream.write(source.read())
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                try:
                    destination.unlink()
                except OSError:
                    pass
                raise
        destination.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def load_artifact(snapshot_id, root=None):
    if not SAFE_ID.fullmatch(str(snapshot_id)):
        raise ValueError("snapshot_id 格式非法")
    path = state_root(root) / f"{snapshot_id}.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_artifact(payload)
    if errors:
        raise ValueError("Artifact 已损坏: " + "；".join(errors))
    return payload


def select_artifacts(root=None, artifact_type=None, trading_date=None, subject=None):
    root = state_root(root)
    selected = []
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if validate_artifact(payload):
                continue
        except (OSError, ValueError, TypeError):
            continue
        if artifact_type and payload.get("artifact_type") != artifact_type:
            continue
        if trading_date and payload.get("trading_date") != trading_date:
            continue
        if subject and str(payload.get("subject", {}).get("id", "")) != str(subject):
            continue
        selected.append(payload)
    return sorted(selected, key=lambda item: (item.get("as_of", ""), item.get("snapshot_id", "")))


def _recent_weekdays(reference, count):
    from datetime import timedelta

    result, cursor = [], reference
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return set(result)


def latest_within_trading_days(root=None, artifact_type=None, subject=None, within=3, reference=None):
    """最近 N 个交易日内的最新有效 Artifact（工作日近似 + 文件日期窗口 + 10 自然日上限）。

    返回 (payload, precision)；无有效样本返回 (None, precision)。
    """
    from datetime import date as date_type, timedelta

    reference = reference or date_type.today()
    candidates = select_artifacts(root, artifact_type=artifact_type, subject=subject)
    if not candidates:
        return None, "empty"
    weekdays = _recent_weekdays(reference, within)
    distinct = []
    for payload in reversed(candidates):
        trading_date = str(payload.get("trading_date", ""))
        if trading_date and trading_date not in distinct:
            distinct.append(trading_date)
    file_window = set(distinct[:within])
    try:
        reference_iso = reference.isoformat()
        file_window = {
            day for day in file_window
            if timedelta(0) <= date_type.fromisoformat(reference_iso) - date_type.fromisoformat(day) <= timedelta(days=10)
        }
    except ValueError:
        file_window = set()
    accepted = weekdays | file_window
    for payload in reversed(candidates):
        if str(payload.get("trading_date", "")) in accepted:
            return payload, "weekday_fallback"
    return None, "expired"


def _read_json(path=None, from_stdin=False):
    if from_stdin:
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="标准研究 Artifact 校验与不可变存储")
    parser.add_argument("--state-dir", help="覆盖默认 ~/.stock-prompt/artifacts")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--input", required=True)
    save = sub.add_parser("save")
    source = save.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--stdin", action="store_true")
    get = sub.add_parser("get")
    get.add_argument("--snapshot-id", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--type", dest="artifact_type")
    listing.add_argument("--date", dest="trading_date")
    listing.add_argument("--subject")
    latest = sub.add_parser("latest")
    latest.add_argument("--type", dest="artifact_type")
    latest.add_argument("--date", dest="trading_date")
    latest.add_argument("--subject")
    latest.add_argument("--within-trading-days", type=int, default=None,
                        help="最近 N 个交易日窗口（工作日近似+文件日期兜底，超窗视为过期）")

    args = parser.parse_args(argv)
    if args.command == "validate":
        errors = validate_artifact(_read_json(args.input))
        if errors:
            print("[FAIL] " + "；".join(errors))
            return 1
        print("[OK] Artifact Schema 校验通过")
        return 0
    if args.command == "save":
        try:
            print(save_artifact(_read_json(args.input, args.stdin), args.state_dir))
            return 0
        except (OSError, ValueError) as exc:
            print(f"[FAIL] {exc}")
            return 1
    if args.command == "get":
        payload = load_artifact(args.snapshot_id, args.state_dir)
        print("N/A" if payload is None else json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if payload is None else 0
    selected = select_artifacts(args.state_dir, args.artifact_type, args.trading_date, args.subject)
    if args.command == "latest":
        if getattr(args, "within_trading_days", None):
            payload, precision = latest_within_trading_days(
                args.state_dir, artifact_type=args.artifact_type, subject=args.subject,
                within=args.within_trading_days,
            )
            if payload is None:
                print("N/A" if precision == "empty" else f"N/A (expired: 无最近 {args.within_trading_days} 个交易日内的有效 Artifact)")
                return 1
            print(json.dumps({"calendar_precision": precision, "artifact": payload},
                             ensure_ascii=False, indent=2))
            return 0
        if not selected:
            print("N/A")
            return 1
        print(json.dumps(selected[-1], ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(selected, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
