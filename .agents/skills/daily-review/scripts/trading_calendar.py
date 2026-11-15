#!/usr/bin/env python3
"""A 股交易日历确定性工具：日期、星期与交易日推算的唯一事实源。

模型禁止心算日期与星期；所有涉及日期的字段（as_of、trading_date、目标交易日、
相对时间词）必须以本工具输出为准。复用 handoff_store 的日历数据
（data/a_share_trading_calendar.json：周末规则 + closed_dates 节假日表）。

环境变量 STOCK_PROMPT_FAKE_TODAY 可覆盖系统时钟（YYYY-MM-DD），
仅供测试与推演回放使用，生产环境不得设置。
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handoff_store import find_calendar, load_calendar

WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def parse_day(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def fake_today():
    """系统时钟唯一入口；STOCK_PROMPT_FAKE_TODAY 仅限测试/回放覆盖。"""
    raw = os.environ.get("STOCK_PROMPT_FAKE_TODAY")
    if raw:
        return parse_day(raw)
    return date.today()


def _closed_days(closed_days=None):
    if closed_days is not None:
        return closed_days
    _, closed, _ = load_calendar(find_calendar())
    return closed


def weekday_cn(day):
    return WEEKDAY_CN[day.weekday()]


def is_trading_day(day, closed_days=None):
    closed = _closed_days(closed_days)
    return day.weekday() < 5 and day not in closed


def next_trading_day(day, closed_days=None):
    closed = _closed_days(closed_days)
    cursor = day + timedelta(days=1)
    while not is_trading_day(cursor, closed):
        cursor += timedelta(days=1)
    return cursor


def prev_trading_day(day, closed_days=None):
    closed = _closed_days(closed_days)
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor, closed):
        cursor -= timedelta(days=1)
    return cursor


def resolve_target_trading_day(as_of_day, closed_days=None):
    """as_of 当日为交易日则取当日；周末/节假日提前推演时顺延至下一交易日。"""
    if is_trading_day(as_of_day, closed_days):
        return as_of_day
    return next_trading_day(as_of_day, closed_days)


def validate_record_date(date_str, phase, closed_days=None, today=None):
    """台账/落盘交易日一致性门禁。返回 (ok, message)。

    规则：目标日期必须是有效交易日；preopen/auction 的"未来日期"
    必须等于系统时钟推算的下一交易日（拦住心算日历导致的错期）。
    """
    try:
        day = parse_day(date_str)
    except (ValueError, TypeError):
        return False, f"日期无法解析: {date_str}（需 YYYY-MM-DD），请以 trading_calendar.py 输出为准"
    now = today or fake_today()
    if not is_trading_day(day, closed_days):
        return False, (
            f"{day} 不是 A 股交易日（{weekday_cn(day)} 或休市日）。"
            f"目标交易日必须由交易日历推算（今日 {now} {weekday_cn(now)}，"
            f"下一交易日 {next_trading_day(now, closed_days)}）"
        )
    if str(phase).lower() in ("preopen", "auction") and day > now:
        expected = next_trading_day(now, closed_days)
        if day != expected:
            return False, (
                f"预测目标交易日 {day} 与日历推算不符：今日 {now} {weekday_cn(now)} "
                f"的下一交易日应为 {expected}。禁止心算日历，请以 scripts/trading_calendar.py 输出为准"
            )
    return True, ""


def _emit(value):
    print(json.dumps(value, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="A 股交易日历确定性工具（日期/星期/交易日唯一事实源）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_today = sub.add_parser("today", help="系统时钟 today（可被 STOCK_PROMPT_FAKE_TODAY 覆盖）")
    p_next = sub.add_parser("next", help="指定日期的下一交易日")
    p_next.add_argument("--date", required=True)
    p_prev = sub.add_parser("prev", help="指定日期的上一交易日")
    p_prev.add_argument("--date", required=True)
    p_is = sub.add_parser("is-trading", help="判断是否交易日")
    p_is.add_argument("--date", required=True)
    p_resolve = sub.add_parser("resolve-target", help="周末/节假日提前推演的目标交易日顺延")
    p_resolve.add_argument("--date", required=True, help="as_of 日期")
    p_check = sub.add_parser("validate-record", help="台账/落盘交易日一致性门禁预检")
    p_check.add_argument("--date", required=True)
    p_check.add_argument("--phase", default="preopen")

    args = parser.parse_args()
    if args.command == "today":
        now = fake_today()
        value = {
            "date": now.isoformat(),
            "weekday": weekday_cn(now),
            "is_trading_day": is_trading_day(now),
            "next_trading_day": next_trading_day(now).isoformat(),
            "prev_trading_day": prev_trading_day(now).isoformat(),
        }
    elif args.command == "next":
        value = next_trading_day(parse_day(args.date)).isoformat()
    elif args.command == "prev":
        value = prev_trading_day(parse_day(args.date)).isoformat()
    elif args.command == "is-trading":
        value = is_trading_day(parse_day(args.date))
    elif args.command == "resolve-target":
        day = parse_day(args.date)
        target = resolve_target_trading_day(day)
        value = {
            "as_of_date": day.isoformat(),
            "as_of_weekday": weekday_cn(day),
            "target_trading_date": target.isoformat(),
            "derived": target != day,
        }
    else:
        ok, message = validate_record_date(args.date, args.phase)
        value = {"ok": ok, "message": message}

    _emit(value)


if __name__ == "__main__":
    main()
