#!/usr/bin/env python3
"""验证、原子写入和读取跨 Skill Handoff Snapshot。"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path


SCHEMA_VERSION = "1.0"
REPORT_TYPES = {"prediction", "daily", "rotation", "stock"}
CONFIDENCE_LEVELS = {"高", "中", "低", "数据不足"}
REQUIRED_FIELDS = (
    "report_type", "as_of", "source_count", "coverage", "scored_weight",
    "confidence", "market_regime", "primary_sectors", "watchlist",
    "risk_flags", "next_triggers",
)
PERCENT_RE = re.compile(r"^(?:N/A|[0-9]+(?:\.[0-9]+)?%)$")
DATE_RE = re.compile(r"^([0-9]{4})-?([0-9]{2})-?([0-9]{2})")


def state_root(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    override = os.environ.get("STOCK_PROMPT_STATE_DIR")
    return Path(override).expanduser() if override else Path.home() / ".stock-prompt" / "state"


def discover_model_version():
    candidates = []
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.extend((parent / "version.json", parent / "registry.json", parent / ".stock-prompt-runtime.json"))
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            version = data.get("latest") or data.get("project", {}).get("version")
            if version:
                return str(version)
        except (OSError, ValueError, TypeError):
            continue
    return os.environ.get("STOCK_PROMPT_MODEL_VERSION", "unknown")


def parse_trading_date(value):
    match = DATE_RE.match(str(value or ""))
    if not match:
        raise ValueError("as_of/trading_date 必须以 YYYY-MM-DD 或 YYYYMMDD 开头")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def validate_handoff(payload):
    errors = []
    if not isinstance(payload, dict):
        return ["根节点必须是对象"]
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"缺少字段: {field}")
    if errors:
        return errors
    if payload["report_type"] not in REPORT_TYPES:
        errors.append("report_type 必须是 prediction/daily/rotation/stock")
    try:
        parse_trading_date(payload.get("trading_date") or payload["as_of"])
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    if not isinstance(payload["source_count"], int) or isinstance(payload["source_count"], bool) or payload["source_count"] < 0:
        errors.append("source_count 必须是非负整数")
    for field in ("coverage", "scored_weight"):
        if not isinstance(payload[field], str) or not PERCENT_RE.fullmatch(payload[field]):
            errors.append(f"{field} 必须是百分比字符串或 N/A")
    if payload["confidence"] not in CONFIDENCE_LEVELS:
        errors.append("confidence 必须是 高/中/低/数据不足")
    if not isinstance(payload["market_regime"], str):
        errors.append("market_regime 必须是字符串")
    for field in ("primary_sectors", "watchlist", "risk_flags", "next_triggers"):
        if not isinstance(payload[field], list):
            errors.append(f"{field} 必须是数组")
    if "inherited_from" in payload and not isinstance(payload["inherited_from"], list):
        errors.append("inherited_from 必须是数组")
    return errors


def load_json(path=None, from_stdin=False):
    if from_stdin:
        return json.load(sys.stdin)
    if not path:
        raise ValueError("必须提供 --input 或 --stdin")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare_handoff(payload, model_version=None):
    prepared = dict(payload)
    trading_date = parse_trading_date(prepared.get("trading_date") or prepared.get("as_of"))
    prepared.setdefault("schema_version", SCHEMA_VERSION)
    prepared.setdefault("model_version", model_version or discover_model_version())
    prepared.setdefault("created_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    prepared["trading_date"] = trading_date.isoformat()
    errors = validate_handoff(prepared)
    if errors:
        raise ValueError("；".join(errors))
    return prepared


def atomic_write(payload, root):
    root.mkdir(parents=True, exist_ok=True)
    compact_date = payload["trading_date"].replace("-", "")
    destination = root / f"handoff-{compact_date}-{payload['report_type']}.json"
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
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def valid_records(root):
    records = []
    for path in sorted(root.glob("handoff-*.json")) if root.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_handoff(payload)
            if errors:
                continue
            records.append((parse_trading_date(payload.get("trading_date") or payload["as_of"]), path, payload))
        except (OSError, ValueError, TypeError):
            continue
    return records


def recent_weekdays(reference, count):
    result = []
    cursor = reference
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor -= timedelta(days=1)
    return set(result)


DEFAULT_CALENDAR_NAME = "a_share_trading_calendar.json"
FILE_WINDOW_MAX_CALENDAR_DAYS = 10


def find_calendar(explicit=None):
    """定位交易日历：--calendar > STOCK_PROMPT_TRADING_CALENDAR > 逐级向上查找 data/ 目录。"""
    if explicit:
        return Path(explicit)
    override = os.environ.get("STOCK_PROMPT_TRADING_CALENDAR")
    if override:
        return Path(override).expanduser()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / DEFAULT_CALENDAR_NAME
        if candidate.is_file():
            return candidate
    return None


def load_calendar(path):
    """返回 (trading_days, closed_days)；trading_days 为 None 表示日历未提供完整交易日序列。"""
    if not path:
        return None, set()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, set()

    def to_dates(values):
        result = set()
        for value in values or []:
            try:
                result.add(parse_trading_date(value))
            except ValueError:
                continue
        return result

    trading = to_dates(data.get("trading_days"))
    closed = to_dates(data.get("closed_dates"))
    return (trading or None), closed


def calendar_window(reference, count, trading_days):
    """日历完整覆盖参考日时，返回截至参考日最近 count 个交易日；否则 None。"""
    if not trading_days or reference not in trading_days:
        return None
    known = sorted(day for day in trading_days if day <= reference)
    if not known or known[-1] != reference:
        return None
    return set(known[-count:])


def file_date_window(records, reference, count):
    """评审补充策略：直接取交接文件中最近 count 个不同 trading_date，并施加自然日安全上限。"""
    distinct = sorted({item[0] for item in records}, reverse=True)[:count]
    return {
        day for day in distinct
        if timedelta(0) <= reference - day <= timedelta(days=FILE_WINDOW_MAX_CALENDAR_DAYS)
    }


def select_latest(root, within_trading_days=3, report_type=None, reference=None, calendar_path=None):
    reference = reference or date.today()
    records = valid_records(root)
    if report_type:
        records = [item for item in records if item[2]["report_type"] == report_type]

    trading_days, closed_days = load_calendar(find_calendar(calendar_path))
    window = calendar_window(reference, within_trading_days, trading_days)
    if window is not None:
        precision, accepted, warning = "calendar", set(window), None
    else:
        weekdays = {
            day for day in recent_weekdays(reference, within_trading_days)
            if day not in closed_days
        }
        accepted = weekdays | file_date_window(records, reference, within_trading_days)
        precision = "weekday_fallback"
        warning = "交易日历未覆盖目标日期，当前按工作日近似"
        if closed_days:
            warning += "（已剔除日历内置休市日）"
        warning += "；另按交接文件最近交易日期扩展，最多回看 %d 个自然日" % FILE_WINDOW_MAX_CALENDAR_DAYS

    selected = [item for item in records if item[0] in accepted]
    if not selected:
        return None
    trading_date, path, payload = max(selected, key=lambda item: (item[0], item[2].get("created_at", "")))
    return {
        "path": str(path),
        "calendar_precision": precision,
        "warning": warning,
        "handoff": payload,
    }


def main():
    parser = argparse.ArgumentParser(description="跨 Skill Handoff Snapshot 存储工具")
    parser.add_argument("--state-dir", help="覆盖默认 ~/.stock-prompt/state")
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="校验并原子写入 Handoff")
    source = write.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--stdin", action="store_true")
    write.add_argument("--model-version")

    latest = sub.add_parser("latest", help="读取最近有效 Handoff")
    latest.add_argument("--within-trading-days", type=int, default=3)
    latest.add_argument("--report-type", choices=sorted(REPORT_TYPES))
    latest.add_argument("--as-of", help="参考日期 YYYY-MM-DD，默认今天")
    latest.add_argument("--calendar", help="A 股交易日历 JSON（含 trading_days / closed_dates）")

    validate = sub.add_parser("validate", help="校验单个文件或状态目录")
    validate.add_argument("--input")

    clean = sub.add_parser("clean", help="列出或清理旧 Handoff")
    clean.add_argument("--older-than-days", type=int, default=30)
    clean.add_argument("--apply", action="store_true", help="确认执行删除；缺省仅预览")

    args = parser.parse_args()
    root = state_root(args.state_dir)
    if args.command == "write":
        payload = prepare_handoff(load_json(args.input, args.stdin), args.model_version)
        print(atomic_write(payload, root))
        return 0
    if args.command == "latest":
        if args.within_trading_days < 1:
            parser.error("--within-trading-days 必须大于 0")
        reference = parse_trading_date(args.as_of) if args.as_of else date.today()
        selected = select_latest(root, args.within_trading_days, args.report_type, reference, args.calendar)
        if not selected:
            print("N/A")
            return 1
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate":
        paths = [Path(args.input)] if args.input else sorted(root.glob("handoff-*.json"))
        failures = 0
        for path in paths:
            try:
                errors = validate_handoff(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                errors = [str(exc)]
            print(f"[{'OK' if not errors else 'FAIL'}] {path}" + (f": {'；'.join(errors)}" if errors else ""))
            failures += bool(errors)
        return 1 if failures else 0
    cutoff = date.today() - timedelta(days=args.older_than_days)
    targets = [item for item in valid_records(root) if item[0] < cutoff]
    for _, path, _ in targets:
        print(f"[{'DELETE' if args.apply else 'WOULD DELETE'}] {path}")
        if args.apply:
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
