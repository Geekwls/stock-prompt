#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market-prediction / daily-review 评估台账工具 (Evaluation Ledger Tracker)

闭环流程：
  1. 盘前 8:30-9:15  →  record         记录当日三态概率 / Opportunity / 主线 Top3
  2. 收盘 15:00 后   →  result         记录实际 Z_ATR / 最强主线 Top3 / 点位触碰
  3. 任意时点        →  report         滚动计算 Brier / 方向命中 / 校准 / 锐度 / 主线 Top1与Top3命中率 / 点位有效率
  4. 收盘复盘后      →  record-daily   记录当日情绪五项分 / 资金延续 / 机会评分 (daily_scores.jsonl)
  5. 任意时点        →  report-daily   输出各评分分布与固定阈值的历史分位落位 (阈值校准依据)

台账默认固定写入 ~/.stock-prompt/eval/predictions.jsonl（不随工作目录漂移），
market-prediction 记录与 daily-review 回测共用同一份；每日评分台账为同目录
daily_scores.jsonl。首次运行若检测到旧版相对路径台账 ./eval/predictions.jsonl，
会自动复制迁移到新位置（原文件保留）。
优先级：--ledger 参数 > STOCK_PROMPT_LEDGER 环境变量 > 默认固定路径；
每日台账同理（--daily-ledger > STOCK_PROMPT_DAILY_LEDGER > 预测台账同目录）。
同一日期重复写入视为更新（后写覆盖）。
"""

import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

STATES = ["up", "side", "down"]
STATE_CN = {"up": "涨", "side": "震", "down": "跌"}
LEGACY_LEDGER = os.path.join("eval", "predictions.jsonl")
LEDGER_SCHEMA_VERSION = "1.0"
PREDICTION_FORMULA_VERSION = "prediction-v2"
DAILY_FORMULA_VERSION = "daily-v2"


def discover_model_version():
    here = Path(__file__).resolve()
    for parent in here.parents:
        for name in ("version.json", "registry.json", ".stock-prompt-runtime.json"):
            try:
                data = json.loads((parent / name).read_text(encoding="utf-8"))
                version = data.get("latest") or data.get("project", {}).get("version")
                if version:
                    return str(version)
            except (OSError, ValueError, TypeError):
                continue
    return os.environ.get("STOCK_PROMPT_MODEL_VERSION", "unknown")


def record_metadata(args, formula_default):
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "model_version": getattr(args, "model_version", None) or discover_model_version(),
        "formula_version": getattr(args, "formula_version", None) or formula_default,
        **({"source_snapshot": args.source_snapshot} if getattr(args, "source_snapshot", None) else {}),
    }


def record_version(rec):
    return str(rec.get("model_version") or "legacy")


def default_ledger():
    """固定锚点台账路径；测试与自定义环境可用 STOCK_PROMPT_EVAL_DIR 重定向根目录。"""
    base = os.environ.get("STOCK_PROMPT_EVAL_DIR") or os.path.expanduser("~")
    return os.path.join(base, ".stock-prompt", "eval", "predictions.jsonl")


def resolve_ledger(explicit=None):
    """解析台账路径：--ledger > STOCK_PROMPT_LEDGER > 固定锚点（含旧台账自动迁移）。"""
    ledger = explicit or os.environ.get("STOCK_PROMPT_LEDGER")
    if ledger:
        return ledger
    anchor = default_ledger()
    if not os.path.exists(anchor) and os.path.exists(LEGACY_LEDGER):
        os.makedirs(os.path.dirname(os.path.abspath(anchor)), exist_ok=True)
        shutil.copy2(LEGACY_LEDGER, anchor)
        print(f"[MIGRATE] 检测到旧台账 ./{LEGACY_LEDGER}，已复制迁移至 {anchor}（原文件保留）")
    return anchor


def zatr_to_state(z):
    """Z_ATR 五档 -> 三态归并（与 SKILL.md 评估口径一致）"""
    if z >= 0.3:
        return "up"
    if z <= -0.3:
        return "down"
    return "side"


def load_ledger(path, model_version=None):
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
                if model_version and record_version(rec) != model_version:
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


def sector_match(predicted, actual_list):
    """板块名按包含关系模糊匹配，兼容“半导体”与“半导体/算力”等口径差异"""
    return any(predicted in s or s in predicted for s in actual_list)


def parse_probs(args):
    probs = {"up": args.p_up, "side": args.p_side, "down": args.p_down}
    if None in probs.values():
        sys.exit("[ERR] --p-up / --p-side / --p-down 三项必填")
    if any(p < 0 or p > 100 for p in probs.values()):
        sys.exit("[ERR] 三态概率必须分别位于 0-100")
    total = sum(probs.values())
    if total <= 0:
        sys.exit("[ERR] 三态概率合计必须大于 0")
    if abs(total - 100) > 1.5:
        print(f"[WARN] 三态概率合计 {total}% != 100%，已自动归一化")
        probs = {k: v * 100.0 / total for k, v in probs.items()}
    if max(probs.values()) > 90:
        print("[WARN] 单项后验概率 > 90%，违反 SKILL.md 极端概率约束（默认上限 80%~85%）")
    return {k: round(v, 2) for k, v in probs.items()}


def cmd_record(args):
    if args.opportunity is not None and not 0 <= args.opportunity <= 100:
        sys.exit("[ERR] --opportunity 必须位于 0-100")
    regime_token = args.regime.strip().split(" ")[0] if args.regime.strip() else ""
    if not re.fullmatch(r"S[0-6]", regime_token):
        print(f"[WARN] regime '{args.regime}' 不符合 S0-S6 约定，仍按原样记录")
    rec = {
        "type": "prediction",
        "date": args.date,
        "regime": args.regime,
        "probs": parse_probs(args),
        "opportunity": args.opportunity,
        "top_sector": args.top_sector,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    rec.update(record_metadata(args, PREDICTION_FORMULA_VERSION))
    top_sectors = [s.strip() for s in (args.top_sectors or "").split(",") if s.strip()]
    if top_sectors:
        rec["top_sectors"] = top_sectors
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
    rec.update(record_metadata(args, PREDICTION_FORMULA_VERSION))
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


DAILY_METRICS = [
    ("up_ratio", "涨跌家数比%", [30.0, 50.0, 70.0]),
    ("premium", "昨日涨停溢价(超额)%", [0.0, 1.0, 3.0]),
    ("promotion", "连板晋级率%", [20.0, 40.0, 60.0]),
    ("break_rate", "全市场炸板率%", [20.0, 30.0, 40.0]),
    ("volume_dev", "量能偏离5日均量%", [-15.0, 15.0]),
    ("sentiment_total", "情绪总分", [50.0, 80.0]),
]
DAILY_EXTRA_METRICS = [("capital_continuity", "资金延续评分"), ("opportunity", "机会评分")]


def load_daily_ledger(path, model_version=None):
    """每日评分台账：同日期后写覆盖，按日期排序返回"""
    daily = {}
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
                if rec.get("type") == "daily_review" and rec.get("date"):
                    if model_version and record_version(rec) != model_version:
                        continue
                    daily[rec["date"]] = rec
    return [daily[d] for d in sorted(daily)]


def percentile_of(sorted_vals, p):
    """线性插值分位数；sorted_vals 需已升序"""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def threshold_percentile(vals, t):
    """阈值在历史样本中的落位：样本中 <= 阈值的比例 (%)"""
    if not vals:
        return None
    return sum(1 for v in vals if v <= t) / len(vals) * 100.0


def cmd_record_daily(args):
    metrics = {
        "up_ratio": args.up_ratio,
        "premium": args.premium,
        "promotion": args.promotion,
        "break_rate": args.break_rate,
        "volume_dev": args.volume_dev,
        "sentiment_total": args.sentiment_total,
        "capital_continuity": args.capital_continuity,
        "opportunity": args.opportunity,
    }
    if all(v is None for v in metrics.values()):
        sys.exit("[ERR] 至少提供一项评分指标 (--up-ratio / --premium / --promotion / --break-rate / --volume-dev / --sentiment-total / --capital-continuity / --opportunity)")
    for key in ("up_ratio", "promotion", "break_rate", "sentiment_total", "capital_continuity", "opportunity"):
        if metrics[key] is not None and not 0 <= metrics[key] <= 100:
            sys.exit(f"[ERR] --{key.replace('_', '-')} 必须位于 0-100")
    rec = {"type": "daily_review", "date": args.date, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    rec.update(record_metadata(args, DAILY_FORMULA_VERSION))
    rec.update({k: round(v, 2) for k, v in metrics.items() if v is not None})
    if args.top_sector:
        rec["top_sector"] = args.top_sector
    append_record(args.daily_ledger, rec)
    print(f"[OK] 已记录 {args.date} 每日评分 -> {args.daily_ledger}")


def cmd_report_daily(args):
    if getattr(args, "all_versions", False):
        versions = ledger_versions(args.daily_ledger, {"daily_review"})
        for version in versions:
            print(f"\n--- model_version={version} ---")
            child = argparse.Namespace(**vars(args))
            child.all_versions = False
            child.filter_version = version
            cmd_report_daily(child)
        return
    selected_version = getattr(args, "filter_version", None) or getattr(args, "model_version", None)
    records = load_daily_ledger(args.daily_ledger, selected_version)
    recent = records[-args.window:] if args.window and args.window > 0 else records
    print(f"=== daily-review 每日评分台账（最近 {len(recent)} 个交易日，累计 {len(records)} 日） ===")
    if not recent:
        print("台账为空。每日收盘复盘后执行 record-daily 落盘，累计 ≥60 日后用于阈值分位校准。")
        return
    for key, label, thresholds in DAILY_METRICS:
        vals = sorted(r[key] for r in recent if r.get(key) is not None)
        if not vals:
            print(f"• {label}: 无样本")
            continue
        dist = " | ".join(f"P{p} {percentile_of(vals, p):.2f}" for p in (10, 25, 50, 75, 90))
        print(f"• {label}: n={len(vals)} | {dist}")
        if thresholds and len(vals) >= 5:
            positions = " | ".join(f"{t:g} -> P{threshold_percentile(vals, t):.0f}" for t in thresholds)
            print(f"    固定阈值历史落位: {positions}")
    for key, label in DAILY_EXTRA_METRICS:
        vals = sorted(r[key] for r in recent if r.get(key) is not None)
        if vals:
            dist = " | ".join(f"P{p} {percentile_of(vals, p):.2f}" for p in (25, 50, 75))
            print(f"• {label}: n={len(vals)} | {dist}")
    if len(recent) < 60:
        print(f"[NOTE] 样本 {len(recent)} 日 < 60 日：继续使用固定回退阈值，并每日 record-daily 落盘；满 60 日后以本报告的分位落位校准阈值并披露样本期。")
    else:
        print("[NOTE] 样本 ≥ 60 日：与设计意图偏差显著的固定阈值档位（如落位 P90+ 或 P10 以下）应改用台账分位校准，并披露样本期。")


def brier_multiclass(probs, actual_state):
    return sum((probs[s] / 100.0 - (1.0 if s == actual_state else 0.0)) ** 2 for s in STATES)


def cmd_report(args):
    if getattr(args, "all_versions", False):
        versions = ledger_versions(args.ledger, {"prediction", "result"})
        for version in versions:
            print(f"\n--- model_version={version} ---")
            child = argparse.Namespace(**vars(args))
            child.all_versions = False
            child.filter_version = version
            cmd_report(child)
        return
    selected_version = getattr(args, "filter_version", None) or getattr(args, "model_version", None)
    preds, results = load_ledger(args.ledger, selected_version)
    pairs = merge_pairs(preds, results)[-args.window:]
    pending = len(set(preds) - set(results))

    print(f"=== market-prediction 滚动评估（最近 {len(pairs)} 个已完成日，窗口 {args.window}，待收盘 {pending} 日） ===")
    if not pairs:
        print("台账中暂无配对完成的记录。先 record 盘前预测，再 result 收盘实际。")
        return

    briers, dir_hits, sector_hits, max_probs = [], 0, 0, []
    cal_buckets = {}  # argmax 概率档位 -> [预测均值, 实际命中列表]
    point_total = point_valid = 0
    top3_any_total = top3_any_hits = top3_ge2_total = top3_ge2_hits = 0

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
        if top1 and sector_match(top1, res.get("top_sectors", [])):
            sector_hits += 1
        pred_top3 = [str(s) for s in pred.get("top_sectors", []) if str(s).strip()]
        actual_top3 = [str(s) for s in res.get("top_sectors", []) if str(s).strip()]
        if pred_top3 and actual_top3:
            hits3 = sum(1 for p in pred_top3 if sector_match(p, actual_top3))
            top3_any_total += 1
            top3_ge2_total += 1
            if hits3 >= 1:
                top3_any_hits += 1
            if hits3 >= 2:
                top3_ge2_hits += 1
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
    if top3_any_total:
        print(f"• 主线 Top3>=1 命中率: {top3_any_hits}/{top3_any_total} = {top3_any_hits / top3_any_total * 100:.1f}%  (仅统计已记录 --top-sectors 的交易日)")
        print(f"• 主线 Top3>=2 命中率: {top3_ge2_hits}/{top3_ge2_total} = {top3_ge2_hits / top3_ge2_total * 100:.1f}%")
    if point_total:
        print(f"• 点位有效率 (S1未破且R1未破): {point_valid}/{point_total} = {point_valid / point_total * 100:.1f}%")

    print("• 概率校准度（按 max 概率分档：档内预测均值 vs 实际命中频率）:")
    for bucket in sorted(cal_buckets):
        p_sum, hits = cal_buckets[bucket]
        n = len(hits)
        print(f"    {bucket:>7}: 预测均值 {p_sum / n:5.1f}% | 实际命中 {sum(hits) / n * 100:5.1f}% | 样本 {n} 日")


def ledger_versions(path, allowed_types):
    versions = set()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") in allowed_types:
                versions.add(record_version(rec))
    return sorted(versions)


def migrate_ledger(path):
    if not os.path.exists(path):
        print(f"[SKIP] 台账不存在: {path}")
        return 0
    changed = 0
    output = []
    with open(path, "r", encoding="utf-8") as stream:
        for raw in stream:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                output.append(raw)
                continue
            if "schema_version" not in rec:
                rec["schema_version"] = "legacy"
                changed += 1
            if "model_version" not in rec:
                rec["model_version"] = "legacy"
            if "formula_version" not in rec:
                rec["formula_version"] = "legacy"
            output.append(json.dumps(rec, ensure_ascii=False) + "\n")
    if not changed:
        print(f"[OK] 无需迁移: {path}")
        return 0
    backup = f"{path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"[MIGRATE] {path}: {changed} 条遗留记录；备份 {backup}")
    if getattr(migrate_ledger, "dry_run", False):
        return changed
    shutil.copy2(path, backup)
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".ledger-migrate-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.writelines(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return changed


def cmd_migrate(args):
    migrate_ledger.dry_run = not args.apply
    targets = []
    if args.target in ("all", "prediction"):
        targets.append(args.ledger)
    if args.target in ("all", "daily"):
        targets.append(args.daily_ledger)
    return sum(migrate_ledger(path) for path in targets)


def main():
    parser = argparse.ArgumentParser(description="评估台账：record / result / report / record-daily / report-daily")
    parser.add_argument("--ledger", default=None, help=f"台账文件路径 (默认 {default_ledger()}，固定不随目录漂移)")
    parser.add_argument("--daily-ledger", default=None, help="每日评分台账路径 (默认为预测台账同目录 daily_scores.jsonl)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="盘前记录当日预测")
    p_rec.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_rec.add_argument("--regime", required=True, help="当前 Market Regime，如 S3")
    p_rec.add_argument("--p-up", type=float, dest="p_up", help="P(Up)%%")
    p_rec.add_argument("--p-side", type=float, dest="p_side", help="P(Side)%%")
    p_rec.add_argument("--p-down", type=float, dest="p_down", help="P(Down)%%")
    p_rec.add_argument("--opportunity", type=float, default=None, help="Opportunity Score 0-100")
    p_rec.add_argument("--top-sector", default="", help="第一主线板块名称")
    p_rec.add_argument("--top-sectors", default="", help="盘前推演主线 Top3，逗号分隔（用于 Top3 命中率评估）")
    p_rec.add_argument("--r1", type=float, default=None, help="上证 R1 压力位（用于点位有效率）")
    p_rec.add_argument("--s1", type=float, default=None, help="上证 S1 支撑位（用于点位有效率）")
    p_rec.add_argument("--model-version", default=discover_model_version(), help="模型版本，默认读取当前项目版本")
    p_rec.add_argument("--formula-version", default=PREDICTION_FORMULA_VERSION, help="预测公式版本")
    p_rec.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_rec.set_defaults(func=cmd_record)

    p_res = sub.add_parser("result", help="收盘后记录当日实际")
    p_res.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_res.add_argument(
        "--z-atr", type=float, required=True,
        help="(当日收盘点位-昨日收盘点位)/ATR14；或等价的收益率/ATR百分比",
    )
    p_res.add_argument("--top-sectors", default="", help="实际最强主线 Top3，逗号分隔")
    p_res.add_argument("--close", type=float, default=None, help="上证收盘点位")
    p_res.add_argument("--high", type=float, default=None, help="上证最高点位（缺省用 close）")
    p_res.add_argument("--low", type=float, default=None, help="上证最低点位（缺省用 close）")
    p_res.add_argument("--model-version", default=discover_model_version(), help="模型版本，须与对应预测一致")
    p_res.add_argument("--formula-version", default=PREDICTION_FORMULA_VERSION, help="结果归并公式版本")
    p_res.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_res.set_defaults(func=cmd_result)

    p_rpt = sub.add_parser("report", help="输出滚动评估指标")
    p_rpt.add_argument("--window", type=int, default=20, help="滚动窗口天数 (默认 20)")
    p_rpt.add_argument("--model-version", default=discover_model_version(), help="默认统计的当前模型版本")
    p_rpt.add_argument("--filter-version", help="指定统计某个模型版本")
    p_rpt.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_rpt.set_defaults(func=cmd_report)

    p_drec = sub.add_parser("record-daily", help="收盘复盘后记录当日情绪/延续/机会评分")
    p_drec.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_drec.add_argument("--up-ratio", type=float, help="涨跌家数比 (红盘率%%)")
    p_drec.add_argument("--premium", type=float, help="昨日涨停股今日平均涨幅相对全市场的超额%%")
    p_drec.add_argument("--promotion", type=float, help="连板晋级率%%")
    p_drec.add_argument("--break-rate", type=float, help="全市场炸板率%%")
    p_drec.add_argument("--volume-dev", type=float, help="两市成交额较5日均量偏离%%")
    p_drec.add_argument("--sentiment-total", type=float, help="情绪总分 0-100")
    p_drec.add_argument("--capital-continuity", type=float, help="资金延续评分 0-100")
    p_drec.add_argument("--opportunity", type=float, help="机会评分 0-100")
    p_drec.add_argument("--top-sector", default="", help="第一主线板块名称")
    p_drec.add_argument("--model-version", default=discover_model_version(), help="模型版本，默认读取当前项目版本")
    p_drec.add_argument("--formula-version", default=DAILY_FORMULA_VERSION, help="每日评分公式版本")
    p_drec.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_drec.set_defaults(func=cmd_record_daily)

    p_drpt = sub.add_parser("report-daily", help="输出每日评分分布与固定阈值历史落位")
    p_drpt.add_argument("--window", type=int, default=60, help="滚动窗口交易日 (默认 60)")
    p_drpt.add_argument("--model-version", default=discover_model_version(), help="默认统计的当前模型版本")
    p_drpt.add_argument("--filter-version", help="指定统计某个模型版本")
    p_drpt.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_drpt.set_defaults(func=cmd_report_daily)

    p_migrate = sub.add_parser("migrate", help="为遗留台账补充 legacy 版本元数据；默认只预览")
    p_migrate.add_argument("--target", choices=("all", "prediction", "daily"), default="all")
    p_migrate.add_argument("--apply", action="store_true", help="备份后执行迁移")
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    args.ledger = resolve_ledger(args.ledger)
    args.daily_ledger = (args.daily_ledger or os.environ.get("STOCK_PROMPT_DAILY_LEDGER")
                         or os.path.join(os.path.dirname(args.ledger), "daily_scores.jsonl"))
    args.func(args)


if __name__ == "__main__":
    main()
