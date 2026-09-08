#!/usr/bin/env python3
"""个股长期研究 Thesis Ledger：校验、原子写入、读取与触发器更新。"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


SCHEMA_VERSION = "1.0"
CODE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LOGIC_HEALTH = {"强化", "稳定", "弱化", "证伪", "暂不评级"}
TRIGGER_STATUSES = {"pending", "confirmed", "failed", "expired", "unverifiable"}
SENSITIVE_KEYS = {
    "position", "position_size", "current_position", "cost", "cost_basis",
    "account", "account_id", "仓位", "成本", "账户",
}


def state_root(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    override = os.environ.get("STOCK_PROMPT_THESIS_DIR")
    return Path(override).expanduser() if override else Path.home() / ".stock-prompt" / "theses"


def sensitive_paths(value, prefix=""):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in SENSITIVE_KEYS or str(key) in SENSITIVE_KEYS:
                found.append(path)
            found.extend(sensitive_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(sensitive_paths(child, f"{prefix}[{index}]"))
    return found


def validate_trigger(trigger, index):
    errors = []
    if not isinstance(trigger, dict):
        return [f"next_triggers[{index}] 必须是对象"]
    for field in ("id", "condition", "status"):
        if not isinstance(trigger.get(field), str) or not trigger[field].strip():
            errors.append(f"next_triggers[{index}].{field} 必须是非空字符串")
    if trigger.get("status") not in TRIGGER_STATUSES:
        errors.append(f"next_triggers[{index}].status 不在允许枚举内")
    return errors


def validate_thesis(payload, allow_sensitive=False):
    if not isinstance(payload, dict):
        return ["根节点必须是对象"]
    errors = []
    for field in ("stock_code", "stock_name", "as_of", "thesis", "logic_health", "catalysts", "risk_flags", "next_triggers"):
        if field not in payload:
            errors.append(f"缺少字段: {field}")
    if errors:
        return errors
    if not CODE_RE.fullmatch(str(payload["stock_code"])):
        errors.append("stock_code 只能包含字母、数字、点、下划线或连字符")
    if not isinstance(payload["stock_name"], str) or not payload["stock_name"].strip():
        errors.append("stock_name 必须是非空字符串")
    if not isinstance(payload["as_of"], str) or len(payload["as_of"]) < 10:
        errors.append("as_of 必须包含有效日期与时点口径")
    if not isinstance(payload["thesis"], str) or not payload["thesis"].strip():
        errors.append("thesis 必须是非空字符串")
    if payload["logic_health"] not in LOGIC_HEALTH:
        errors.append("logic_health 必须是 强化/稳定/弱化/证伪/暂不评级")
    for field in ("catalysts", "risk_flags", "next_triggers"):
        if not isinstance(payload[field], list):
            errors.append(f"{field} 必须是数组")
    if isinstance(payload.get("next_triggers"), list):
        for index, trigger in enumerate(payload["next_triggers"]):
            errors.extend(validate_trigger(trigger, index))
    sensitive = sensitive_paths(payload)
    if sensitive and not allow_sensitive:
        errors.append("默认禁止持久化仓位、成本或账户信息；删除字段或显式使用 --allow-sensitive: " + ", ".join(sensitive))
    return errors


def load_json(path=None, from_stdin=False):
    if from_stdin:
        return json.load(sys.stdin)
    if not path:
        raise ValueError("必须提供 --input 或 --stdin")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def thesis_path(root, stock_code):
    code = str(stock_code).strip()
    if not CODE_RE.fullmatch(code):
        raise ValueError("股票代码格式非法")
    return root / f"{code}.json"


def history_entry(payload):
    return {
        key: payload.get(key)
        for key in (
            "snapshot_id", "as_of", "updated_at", "logic_health", "thesis",
            "catalysts", "risk_flags", "next_triggers", "review_delta",
        )
        if key in payload
    }


def prepare_thesis(payload, previous=None, allow_sensitive=False):
    prepared = dict(payload)
    prepared.setdefault("schema_version", SCHEMA_VERSION)
    prepared.setdefault("updated_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    prepared.setdefault(
        "snapshot_id",
        f"{prepared.get('stock_code', 'unknown')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
    )
    history = list(previous.get("history", [])) if previous else list(prepared.get("history", []))
    if previous:
        history.append(history_entry(previous))
    prepared["history"] = history[-100:]
    errors = validate_thesis(prepared, allow_sensitive)
    if errors:
        raise ValueError("；".join(errors))
    return prepared


def atomic_write(payload, root):
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    destination = thesis_path(root, payload["stock_code"])
    if destination.exists():
        backup_root = root / ".backups"
        backup_root.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(destination, backup_root / f"{destination.stem}-{stamp}.json")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(root))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def load_existing(root, stock_code):
    path = thesis_path(root, stock_code)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="个股长期 Thesis Ledger")
    parser.add_argument("--state-dir", help="覆盖默认 ~/.stock-prompt/theses")
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="校验并写入个股 Thesis；旧版本进入 history")
    source = write.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--stdin", action="store_true")
    write.add_argument("--allow-sensitive", action="store_true", help="明确允许保存仓位/成本等敏感字段")

    get = sub.add_parser("get", help="读取指定个股 Thesis")
    get.add_argument("--stock-code", required=True)

    sub.add_parser("list", help="列出已有个股 Thesis 摘要")

    args = parser.parse_args()
    root = state_root(args.state_dir)
    if args.command == "write":
        incoming = load_json(args.input, args.stdin)
        previous = load_existing(root, incoming.get("stock_code", ""))
        prepared = prepare_thesis(incoming, previous, args.allow_sensitive)
        print(atomic_write(prepared, root))
        return 0
    if args.command == "get":
        payload = load_existing(root, args.stock_code)
        if payload is None:
            print("N/A")
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    summaries = []
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            summaries.append({key: payload.get(key) for key in ("stock_code", "stock_name", "as_of", "logic_health", "updated_at")})
        except (OSError, ValueError, TypeError):
            continue
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
