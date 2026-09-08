#!/usr/bin/env python3
"""周度复盘摘要：聚合预测评估、每日评分、主线状态与触发器核验，输出一页 Markdown。

数据来源（全部只读）：
  - ~/.stock-prompt/eval/predictions.jsonl   盘前预测与收盘结果（eval_tracker）
  - ~/.stock-prompt/eval/daily_scores.jsonl  每日评分与主线状态（eval_tracker）
  - ~/.stock-prompt/state/handoff-*.json     交接摘要中的结构化触发器状态（handoff_store）
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_tracker as EVAL  # noqa: E402
import handoff_store as HANDOFF  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_day(value):
    return date.fromisoformat(str(value)[:10])


def collect_trigger_status(state_dir, start, end):
    counts = {}
    pending_items = []
    root = HANDOFF.state_root(state_dir)
    if not root.exists():
        return counts, pending_items
    for path in sorted(root.glob("handoff-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        day = parse_trading_day_from_name(path.name)
        if day is None or not (start <= day <= end):
            continue
        for trigger in payload.get("next_triggers", []):
            if isinstance(trigger, dict):
                status = str(trigger.get("status", "pending"))
                counts[status] = counts.get(status, 0) + 1
                if status == "pending":
                    pending_items.append((day, trigger.get("id"), trigger.get("condition")))
            elif isinstance(trigger, str):
                counts["string(未结构化)"] = counts.get("string(未结构化)", 0) + 1
    return counts, pending_items


def parse_trading_day_from_name(name):
    digits = "".join(ch for ch in name if ch.isdigit())[:8]
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None


def build_digest(args):
    end = parse_day(args.as_of) if args.as_of else date.today()
    start = end - timedelta(days=args.days - 1)
    lines = []
    lines.append(f"# stock-prompt 周度复盘摘要（{start.isoformat()} ~ {end.isoformat()}）")
    lines.append("")

    # 1. 盘前预测评估
    preds, results = EVAL.load_ledger(args.ledger, None, "preopen")
    pairs = [(d, preds[d], results[d]) for d in sorted(set(preds) & set(results))
             if start <= parse_day(d) <= end]
    lines.append("## 一、盘前预测质量")
    if not pairs:
        lines.append("- 本区间无配对完成的预测与结果。")
    else:
        briers = [EVAL.brier_multiclass(p["probs"], r["actual_state"]) for _, p, r in pairs]
        hits = sum(1 for _, p, r in pairs
                   if max(EVAL.STATES, key=lambda s: p["probs"][s]) == r["actual_state"])
        top1 = sum(1 for _, p, r in pairs
                   if p.get("top_sector") and EVAL.sector_match(str(p["top_sector"]), r.get("top_sectors", [])))
        pendings = [d for d in preds if start <= parse_day(d) <= end and d not in results]
        lines.append(f"- 配对 {len(pairs)} 日：方向命中 {hits}/{len(pairs)}"
                     f"（{(hits / len(pairs) * 100):.0f}%），平均 Brier {sum(briers) / len(briers):.3f}。")
        lines.append(f"- 主线 Top1 命中 {top1}/{len(pairs)}。")
        if pendings:
            lines.append(f"- 待收盘回测：{', '.join(pendings)}。")

    # 2. 每日评分与主线状态
    daily = EVAL.load_daily_ledger(args.daily_ledger, None)
    window = [r for r in daily if start <= parse_day(r["date"]) <= end]
    lines.append("")
    lines.append("## 二、每日评分与主线状态")
    if not window:
        lines.append("- 本区间无每日评分记录。")
    else:
        sentiments = [r["sentiment_total"] for r in window if r.get("sentiment_total") is not None]
        opportunities = [r["opportunity"] for r in window if r.get("opportunity") is not None]
        continuities = [r["capital_continuity"] for r in window if r.get("capital_continuity") is not None]
        if sentiments:
            lines.append(f"- 情绪总分：均值 {sum(sentiments) / len(sentiments):.0f}，"
                         f"区间 {min(sentiments):.0f}~{max(sentiments):.0f}（{len(sentiments)} 日）。")
        if opportunities:
            lines.append(f"- 机会评分均值 {sum(opportunities) / len(opportunities):.0f}（{len(opportunities)} 日）。")
        if continuities:
            lines.append(f"- 资金延续均值 {sum(continuities) / len(continuities):.0f}（{len(continuities)} 日）。")
        mainline = [(r["date"], r.get("mainline_sector"), r.get("mainline_state"), r.get("sei"))
                    for r in window if r.get("mainline_state")]
        if mainline:
            lines.append("- 主线状态序列：")
            for day, sector, state, sei in mainline:
                sei_part = f"，SEI {sei:.0f}" if sei is not None else ""
                lines.append(f"  - {day} {sector}【{state}】{sei_part}")
        else:
            lines.append("- 主线状态：本区间未落盘（record-daily --mainline-sector/--mainline-state）。")

    # 3. 触发器核验汇总
    counts, pending_items = collect_trigger_status(args.state_dir, start, end)
    lines.append("")
    lines.append("## 三、触发器核验")
    if not counts:
        lines.append("- 本区间交接摘要中无结构化触发器。")
    else:
        summary = " | ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        lines.append(f"- 状态分布：{summary}")
        if pending_items:
            lines.append("- 待核验（pending）：")
            for day, trigger_id, condition in pending_items[-8:]:
                lines.append(f"  - {day} `{trigger_id}` {condition}")

    lines.append("")
    lines.append("> 生成命令：python scripts/weekly_digest.py；详细指标见 eval report / report-daily / report-mainline / replay。")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="周度复盘摘要（聚合预测评估 / 每日评分 / 主线状态 / 触发器核验）")
    parser.add_argument("--as-of", help="截止日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--days", type=int, default=7, help="汇总自然日窗口 (默认 7)")
    parser.add_argument("--output", help="另存为 Markdown 文件（缺省仅打印）")
    parser.add_argument("--ledger", default=None, help="预测台账路径 (默认固定锚点)")
    parser.add_argument("--daily-ledger", default=None, help="每日评分台账路径 (默认与预测台账同目录)")
    parser.add_argument("--state-dir", default=None, help="Handoff 状态目录 (默认 ~/.stock-prompt/state)")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days 必须 >= 1")
    args.ledger = EVAL.resolve_ledger(args.ledger)
    args.daily_ledger = (args.daily_ledger or os.environ.get("STOCK_PROMPT_DAILY_LEDGER")
                         or os.path.join(os.path.dirname(args.ledger), "daily_scores.jsonl"))
    digest = build_digest(args)
    print(digest)
    if args.output:
        destination = Path(args.output)
        destination.write_text(digest + "\n", encoding="utf-8")
        print(f"\n[OK] 已写入 {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
