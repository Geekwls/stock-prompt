#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market-prediction 评估台账工具 (Evaluation Ledger Tracker)

闭环流程：
  1. 盘前 8:30-9:15  →  record  记录当日三态概率 / Opportunity / 第一主线
  2. 收盘 15:00 后   →  result  记录实际 Z_ATR / 最强主线 Top3 / 点位触碰
  3. 任意时点        →  report  滚动计算 Brier / 方向命中 / 校准 / 锐度 / 主线命中率 / 点位有效率

台账文件默认为当前工作目录下 eval/predictions.jsonl，同一日期重复写入视为更新（后写覆盖）。
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

STATES = ["up", "side", "down"]
STATE_CN = {"up": "涨", "side": "震", "down": "跌"}


def zatr_to_state(z):
    """Z_ATR 五档 -> 三态归并（与 SKILL.md 评估口径一致）"""
    if z >= 0.3:
        return "up"
    if z <= -0.3:
        return "down"
    return "side"


def load_ledger(path):
    """返回 (预测, 实际) 两个字典，同日期同类型后写覆盖（等价于更新）"""
    preds, results = {}, {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec["type"] == "prediction":
                    preds[rec["date"]] = rec
                else:
                    results[rec["date"]] = rec
    return preds, results


def append_record(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def parse_probs(args):
    probs = {"up": args.p_up, "side": args.p_side, "down": args.p_down}
    if None in probs.values():
        sys.exit("[ERR] --p-up / --p-side / --p-down 三项必填")
    total = sum(probs.values())
    if abs(total - 100) > 1.5:
        print(f"[WARN] 三态概率合计 {total}% != 100%，已自动归一化")
        probs = {k: v * 100.0 / total for k, v in probs.items()}
    if max(probs.values()) > 90:
        print("[WARN] 单项后验概率 > 90%，违反 SKILL.md 极端概率约束（默认上限 80%~85%）")
    return {k: round(v, 2) for k, v in probs.items()}


def cmd_record(args):
    rec = {
        "type": "prediction",
        "date": args.date,
        "regime": args.regime,
        "probs": parse_probs(args),
        "opportunity": args.opportunity,
        "top_sector": args.top_sector,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if args.r1 is not None:
        rec["r1"] = args.r1
    if args.s1 is not None:
        rec["s1"] = args.s1
    append_record(args.ledger, rec)
    print(f"[OK] 已记录 {args.date} 盘前预测 -> {args.ledger}")


def cmd_result(args):
    rec = {
        "type": "result",
        "date": args.date,
        "z_atr": args.z_atr,
        "actual_state": zatr_to_state(args.z_atr),
        "top_sectors": [s.strip() for s in args.top_sectors.split(",") if s.strip()],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if args.close is not None:
        rec["close"] = args.close
    if args.high is not None:
        rec["high"] = args.high
    if args.low is not None:
        rec["low"] = args.low
    append_record(args.ledger, rec)
    print(f"[OK] 已记录 {args.date} 收盘实际 (Z_ATR={args.z_atr} -> {STATE_CN[rec['actual_state']]}) -> {args.ledger}")


def merge_pairs(preds, results):
    """按日期配对预测与实际"""
    return [(d, preds[d], results[d]) for d in sorted(set(preds) & set(results))]


def brier_multiclass(probs, actual_state):
    return sum((probs[s] / 100.0 - (1.0 if s == actual_state else 0.0)) ** 2 for s in STATES)


def cmd_report(args):
    preds, results = load_ledger(args.ledger)
    pairs = merge_pairs(preds, results)[-args.window:]
    pending = len(set(preds) - set(results))

    print(f"=== market-prediction 滚动评估（最近 {len(pairs)} 个已完成日，窗口 {args.window}，待收盘 {pending} 日） ===")
    if not pairs:
        print("台账中暂无配对完成的记录。先 record 盘前预测，再 result 收盘实际。")
        return

    briers, dir_hits, sector_hits, max_probs = [], 0, 0, []
    cal_buckets = {}  # argmax 概率档位 -> [预测均值, 实际命中列表]
    point_total = point_valid = 0

    for date, pred, res in pairs:
        probs = pred["probs"]
        state = res["actual_state"]
        briers.append(brier_multiclass(probs, state))
        argmax_state = max(STATES, key=lambda s: probs[s])
        max_p = probs[argmax_state]
        max_probs.append(max_p)
        if argmax_state == state:
            dir_hits += 1
        bucket = f"{int(max_p // 10) * 10}-{int(max_p // 10) * 10 + 10}%"
        cal_buckets.setdefault(bucket, [0.0, []])
        cal_buckets[bucket][0] += max_p
        cal_buckets[bucket][1].append(1.0 if argmax_state == state else 0.0)
        top1 = str(pred.get("top_sector", ""))
        if top1 and any(top1 in s or s in top1 for s in res.get("top_sectors", [])):
            sector_hits += 1
        if "r1" in pred and "s1" in pred and "close" in res:
            point_total += 1
            high = res.get("high", res["close"])
            low = res.get("low", res["close"])
            if low >= pred["s1"] and high <= pred["r1"]:
                point_valid += 1

    mean_brier = sum(briers) / len(briers)
    print(f"• 多分类 Brier Score : {mean_brier:.3f}  ({'优' if mean_brier < 0.15 else '良' if mean_brier < 0.25 else '差'}, 越低越好)")
    print(f"• 三态方向命中率     : {dir_hits}/{len(pairs)} = {dir_hits / len(pairs) * 100:.1f}%")
    print(f"• 预测锐度 (均值max P): {sum(max_probs) / len(max_probs):.1f}%  ({'敢于区分' if sum(max_probs) / len(max_probs) >= 50 else '过于保守'})")
    print(f"• 主线 Top1 命中率   : {sector_hits}/{len(pairs)} = {sector_hits / len(pairs) * 100:.1f}%")
    if point_total:
        print(f"• 点位有效率 (S1未破且R1未破): {point_valid}/{point_total} = {point_valid / point_total * 100:.1f}%")

    print("• 概率校准度（按 max 概率分档：档内预测均值 vs 实际命中频率）:")
    for bucket in sorted(cal_buckets):
        p_sum, hits = cal_buckets[bucket]
        n = len(hits)
        print(f"    {bucket:>7}: 预测均值 {p_sum / n:5.1f}% | 实际命中 {sum(hits) / n * 100:5.1f}% | 样本 {n} 日")


def main():
    parser = argparse.ArgumentParser(description="market-prediction 评估台账：record / result / report")
    parser.add_argument("--ledger", default=os.path.join("eval", "predictions.jsonl"), help="台账文件路径 (默认 ./eval/predictions.jsonl)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="盘前记录当日预测")
    p_rec.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_rec.add_argument("--regime", required=True, help="当前 Market Regime，如 S3")
    p_rec.add_argument("--p-up", type=float, dest="p_up", help="P(Up)%%")
    p_rec.add_argument("--p-side", type=float, dest="p_side", help="P(Side)%%")
    p_rec.add_argument("--p-down", type=float, dest="p_down", help="P(Down)%%")
    p_rec.add_argument("--opportunity", type=float, default=None, help="Opportunity Score 0-100")
    p_rec.add_argument("--top-sector", default="", help="第一主线板块名称")
    p_rec.add_argument("--r1", type=float, default=None, help="上证 R1 压力位（用于点位有效率）")
    p_rec.add_argument("--s1", type=float, default=None, help="上证 S1 支撑位（用于点位有效率）")
    p_rec.set_defaults(func=cmd_record)

    p_res = sub.add_parser("result", help="收盘后记录当日实际")
    p_res.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_res.add_argument("--z-atr", type=float, required=True, help="上证当日收益 / ATR14")
    p_res.add_argument("--top-sectors", default="", help="实际最强主线 Top3，逗号分隔")
    p_res.add_argument("--close", type=float, default=None, help="上证收盘点位")
    p_res.add_argument("--high", type=float, default=None, help="上证最高点位（缺省用 close）")
    p_res.add_argument("--low", type=float, default=None, help="上证最低点位（缺省用 close）")
    p_res.set_defaults(func=cmd_result)

    p_rpt = sub.add_parser("report", help="输出滚动评估指标")
    p_rpt.add_argument("--window", type=int, default=20, help="滚动窗口天数 (默认 20)")
    p_rpt.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
