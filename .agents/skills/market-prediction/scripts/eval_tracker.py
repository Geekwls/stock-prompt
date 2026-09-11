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
预测与结果均采用追加式不可变修订：同一日期/阶段重复写入必须显式传入
--revise，并保留 revision / supersedes；已有收盘结果后禁止补写或修改盘前预测。
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

script_path = Path(__file__).resolve()
for parent in script_path.parents:
    if (parent / "registry.json").is_file() or (parent / ".stock-prompt-runtime.json").is_file():
        sys.path.insert(0, str(parent))
        break
from tools.calculations.market import calculate_atr_state
from tools.calculations.metrics import calculate_multiclass_brier

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

STATES = ["up", "side", "down"]
STATE_CN = {"up": "涨", "side": "震", "down": "跌"}
LEGACY_LEDGER = os.path.join("eval", "predictions.jsonl")
LEDGER_SCHEMA_VERSION = "1.0"
PREDICTION_FORMULA_VERSION = "prediction-v2"
DAILY_FORMULA_VERSION = "daily-v2"
ERROR_REASONS = {
    "data_missing", "source_delay", "event_shock", "regime_misread",
    "sector_mapping", "threshold_issue", "evidence_conflict", "overconfidence",
}
EVIDENCE_STANCES = ("强偏多", "偏多", "中性", "偏空", "强偏空")
EVIDENCE_CLUSTERS = ("e1", "e2", "e3", "e4")
MAINLINE_STATES = ("启动", "强化", "加速", "分歧", "弱化", "退潮")


def opportunity_bucket(score):
    """与 SKILL.md 机会分阈值一致：>=75 高 / 45-74 中 / <45 低"""
    if score >= 75:
        return "高(>=75)"
    if score >= 45:
        return "中(45-74)"
    return "低(<45)"


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


def read_records(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            try:
                records.append(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
    return records


def matching_records(path, record_type, date, phase=None):
    matches = []
    for record in read_records(path):
        if record.get("type") != record_type or record.get("date") != date:
            continue
        if phase is not None and record.get("market_phase", "preopen") != phase:
            continue
        matches.append(record)
    return matches


def revision_metadata(previous, prefix):
    latest = max(previous, key=lambda item: int(item.get("revision", 1))) if previous else None
    revision = int(latest.get("revision", 1)) + 1 if latest else 1
    return {
        "revision": revision,
        **({"supersedes": latest.get("snapshot_id")} if latest else {}),
        "snapshot_id": f"{prefix}-r{revision}-{datetime.now().strftime('%H%M%S%f')}",
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
    # 令 previous_close=0、atr14=1，可直接复用统一 Z_ATR 三态边界。
    return calculate_atr_state(z, 0, 1)["value"]


def load_ledger(path, model_version=None, market_phase="preopen"):
    """返回指定市场阶段的预测与实际；显式修订按 revision 选择，原记录始终保留。"""
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
                    if rec.get("market_phase", "preopen") != market_phase:
                        continue
                    current = preds.get(rec["date"])
                    if current is None or int(rec.get("revision", 1)) >= int(current.get("revision", 1)):
                        preds[rec["date"]] = rec
                elif rec["type"] == "result":
                    current = results.get(rec["date"])
                    if current is None or int(rec.get("revision", 1)) >= int(current.get("revision", 1)):
                        results[rec["date"]] = rec
    return preds, results


def append_record(path, rec):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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
    phase = getattr(args, "market_phase", "preopen")
    previous = matching_records(args.ledger, "prediction", args.date, phase)
    if matching_records(args.ledger, "result", args.date):
        sys.exit("[ERR] 当日收盘结果已存在，禁止事后补写或修改盘前预测")
    if previous and not getattr(args, "revise", False):
        sys.exit("[ERR] 同日同阶段预测已存在；如确需修订，请使用 --revise 并填写 --revision-reason")
    if previous and not str(getattr(args, "revision_reason", "") or "").strip():
        sys.exit("[ERR] --revise 必须同时填写 --revision-reason")
    rec = {
        "type": "prediction",
        "date": args.date,
        "market_phase": phase,
        "regime": args.regime,
        "probs": parse_probs(args),
        "opportunity": args.opportunity,
        "top_sector": args.top_sector,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "coverage_band": getattr(args, "coverage_band", None),
        "data_status": getattr(args, "data_status", None),
        "volatility_band": getattr(args, "volatility_band", None),
    }
    rec.update(revision_metadata(previous, f"{args.date}-{phase}-prediction"))
    if previous:
        rec["revision_reason"] = args.revision_reason
    rec.update(record_metadata(args, PREDICTION_FORMULA_VERSION))
    evidence = {}
    for cluster in EVIDENCE_CLUSTERS:
        stance = getattr(args, cluster, None)
        if stance is not None:
            evidence[cluster.upper()] = stance
    if evidence:
        rec["evidence_clusters"] = evidence
    top_sectors = [s.strip() for s in (args.top_sectors or "").split(",") if s.strip()]
    if top_sectors:
        rec["top_sectors"] = top_sectors
    if args.r1 is not None:
        rec["r1"] = args.r1
    if args.s1 is not None:
        rec["s1"] = args.s1
    append_record(args.ledger, rec)
    print(f"[OK] 已记录 {args.date} 盘前预测 -> {args.ledger}")
    if evidence:
        print("[HINT] 已存证据簇判档 " + ", ".join(f"{k}={v}" for k, v in evidence.items())
              + "；积累后 report 将输出各簇判读力统计")


def cmd_result(args):
    previous = matching_records(args.ledger, "result", args.date)
    if previous and not getattr(args, "revise", False):
        sys.exit("[ERR] 同日收盘结果已存在；如需纠错，请使用 --revise 并填写 --revision-reason")
    if previous and not str(getattr(args, "revision_reason", "") or "").strip():
        sys.exit("[ERR] --revise 必须同时填写 --revision-reason")
    rec = {
        "type": "result",
        "date": args.date,
        "z_atr": args.z_atr,
        "actual_state": zatr_to_state(args.z_atr),
        "top_sectors": [s.strip() for s in args.top_sectors.split(",") if s.strip()],
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    rec.update(revision_metadata(previous, f"{args.date}-result"))
    if previous:
        rec["revision_reason"] = args.revision_reason
    rec.update(record_metadata(args, PREDICTION_FORMULA_VERSION))
    if args.close is not None:
        rec["close"] = args.close
    if args.high is not None:
        rec["high"] = args.high
    if args.low is not None:
        rec["low"] = args.low
    if getattr(args, "top1_sector_change", None) is not None:
        rec["top1_sector_change"] = args.top1_sector_change
    reasons = [item.strip() for item in str(getattr(args, "error_reasons", "") or "").split(",") if item.strip()]
    invalid_reasons = sorted(set(reasons) - ERROR_REASONS)
    if invalid_reasons:
        sys.exit("[ERR] 未知错误归因: " + ", ".join(invalid_reasons))
    if reasons:
        rec["error_reasons"] = reasons
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
    mainline_state = getattr(args, "mainline_state", None)
    mainline_sector = getattr(args, "mainline_sector", "") or ""
    sei = getattr(args, "sei", None)
    if mainline_state and not mainline_sector:
        sys.exit("[ERR] --mainline-state 必须同时提供 --mainline-sector")
    if sei is not None and not mainline_sector:
        sys.exit("[ERR] --sei 必须同时提供 --mainline-sector")
    if sei is not None and not 0 <= sei <= 100:
        sys.exit("[ERR] --sei 必须位于 0-100")
    if all(v is None for v in metrics.values()) and not mainline_sector:
        sys.exit("[ERR] 至少提供一项评分指标 (--up-ratio / --premium / --promotion / --break-rate / --volume-dev / --sentiment-total / --capital-continuity / --opportunity / --mainline-sector)")
    for key in ("up_ratio", "promotion", "break_rate", "sentiment_total", "capital_continuity", "opportunity"):
        if metrics[key] is not None and not 0 <= metrics[key] <= 100:
            sys.exit(f"[ERR] --{key.replace('_', '-')} 必须位于 0-100")
    rec = {"type": "daily_review", "date": args.date, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    rec.update(record_metadata(args, DAILY_FORMULA_VERSION))
    rec.update({k: round(v, 2) for k, v in metrics.items() if v is not None})
    if mainline_sector:
        rec["mainline_sector"] = mainline_sector
        if mainline_state:
            rec["mainline_state"] = mainline_state
        if sei is not None:
            rec["sei"] = round(sei, 2)
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
    if getattr(args, "extremes", False):
        sentiment = [(r["date"], r["sentiment_total"]) for r in recent if r.get("sentiment_total") is not None]
        print("• 情绪极值与后续表现 (极值日之后 ≤3 个交易日的平均 Z_ATR):")
        if not sentiment:
            print("    无情绪总分样本")
        else:
            _, z_results = load_ledger(args.ledger, None, "preopen")
            z_by_date = {d: r.get("z_atr") for d, r in z_results.items() if r.get("z_atr") is not None}
            ordered = sorted(z_by_date)

            def forward_mean(day, count=3):
                import bisect

                index = bisect.bisect_right(ordered, day)
                window = [z_by_date[ordered[i]] for i in range(index, min(index + count, len(ordered)))]
                return sum(window) / len(window) if window else None

            for label, group in (("冰点(<=30)", [x for x in sentiment if x[1] <= 30]),
                                 ("过热(>=80)", [x for x in sentiment if x[1] >= 80])):
                if not group:
                    print(f"    {label}: 无样本")
                    continue
                forwards = [forward_mean(day) for day, _ in group]
                forwards = [value for value in forwards if value is not None]
                tail = f"，最近 {group[-1][0]}（{group[-1][1]:.0f}分）"
                if forwards:
                    tail += f"，后续均值Z_ATR {sum(forwards) / len(forwards):+.2f}（n={len(forwards)}）"
                else:
                    tail += "，暂无后续收盘结果可对照"
                print(f"    {label}: {len(group)} 次{tail}")
    if len(recent) < 60:
        print(f"[NOTE] 样本 {len(recent)} 日 < 60 日：继续使用固定回退阈值，并每日 record-daily 落盘；满 60 日后以本报告的分位落位校准阈值并披露样本期。")
    else:
        print("[NOTE] 样本 ≥ 60 日：与设计意图偏差显著的固定阈值档位（如落位 P90+ 或 P10 以下）应改用台账分位校准，并披露样本期。")


def brier_multiclass(probs, actual_state):
    return calculate_multiclass_brier(probs, actual_state)["value"]


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
    phase = getattr(args, "market_phase", "preopen")
    preds, results = load_ledger(args.ledger, selected_version, phase)
    pairs = merge_pairs(preds, results)[-args.window:]
    pending = len(set(preds) - set(results))

    print(f"=== market-prediction 滚动评估（阶段 {phase}，最近 {len(pairs)} 个已完成日，窗口 {args.window}，待收盘 {pending} 日） ===")
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

    print("• 分环境方向命中率:")
    for field, label in (("regime", "Regime"), ("coverage_band", "覆盖率"), ("volatility_band", "波动率"), ("data_status", "数据状态")):
        groups = {}
        for _, pred, result in pairs:
            value = pred.get(field)
            if not value:
                continue
            predicted = max(STATES, key=lambda state: pred["probs"][state])
            groups.setdefault(str(value), []).append(predicted == result["actual_state"])
        for value, hits in sorted(groups.items()):
            print(f"    {label}={value}: {sum(hits)}/{len(hits)} = {sum(hits) / len(hits) * 100:.1f}%")
    reason_counts = {}
    for _, pred, result in pairs:
        predicted = max(STATES, key=lambda state: pred["probs"][state])
        if predicted == result["actual_state"]:
            continue
        for reason in result.get("error_reasons", ["unclassified"]):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    if reason_counts:
        print("• 未命中归因: " + " | ".join(f"{key}={value}" for key, value in sorted(reason_counts.items())))

    # 证据簇判读力：判多时实际涨的比例 / 判空时实际跌的比例（数据存在时输出）
    cluster_stats = {}
    for _, pred, result in pairs:
        clusters = pred.get("evidence_clusters")
        if not isinstance(clusters, dict):
            continue
        for name, stance in clusters.items():
            if stance in ("偏多", "强偏多"):
                bucket = "看多"
            elif stance in ("偏空", "强偏空"):
                bucket = "看空"
            else:
                continue
            stat = cluster_stats.setdefault((str(name), bucket), [0, 0])
            stat[0] += 1
            if (bucket == "看多" and result["actual_state"] == "up") or \
               (bucket == "看空" and result["actual_state"] == "down"):
                stat[1] += 1
    if cluster_stats:
        print("• 证据簇判读力 (判多→实际涨 / 判空→实际跌):")
        for (name, bucket), (total, correct) in sorted(cluster_stats.items()):
            print(f"    {name} {bucket}: {correct}/{total} = {correct / total * 100:.0f}%")

    if getattr(args, "validate_opportunity", False):
        buckets = {}
        for _, pred, result in pairs:
            if pred.get("opportunity") is None:
                continue
            key = opportunity_bucket(pred["opportunity"])
            predicted = max(STATES, key=lambda state: pred["probs"][state])
            entry = {"hit": predicted == result["actual_state"]}
            top1 = str(pred.get("top_sector", ""))
            entry["top1_hit"] = bool(top1) and sector_match(top1, result.get("top_sectors", []))
            if result.get("top1_sector_change") is not None:
                entry["top1_change"] = result["top1_sector_change"]
            buckets.setdefault(key, []).append(entry)
        print("• 机会分有效性验证 (Opportunity 分层):")
        for key in ("高(>=75)", "中(45-74)", "低(<45)"):
            items = buckets.get(key, [])
            if not items:
                print(f"    {key}: 无样本")
                continue
            n = len(items)
            hits = sum(item["hit"] for item in items)
            top1_hits = sum(item["top1_hit"] for item in items)
            parts = [f"n={n}", f"方向命中 {hits}/{n} = {hits / n * 100:.0f}%", f"Top1命中 {top1_hits}/{n}"]
            changes = [item["top1_change"] for item in items if "top1_change" in item]
            if changes:
                parts.append(f"第一主线均涨幅 {sum(changes) / len(changes):+.2f}%")
            print(f"    {key}: " + " | ".join(parts))
        if not any(result.get("top1_sector_change") is not None for _, _, result in pairs):
            print("    [NOTE] 尚无 --top1-sector-change 数据；result 时记录当日第一主线实际涨幅%后可输出涨幅对照")


def cmd_replay(args):
    """当日推演化回放：盘前 → 竞价后验 → 收盘实际 → 修订对错评价"""
    records = read_records(args.ledger)
    preds = [r for r in records if r.get("type") == "prediction" and r.get("date") == args.date]
    results = [r for r in records if r.get("type") == "result" and r.get("date") == args.date]
    if not preds and not results:
        print(f"[N/A] {args.date} 无任何台账记录")
        return 0
    print(f"=== {args.date} 推演化回放 ===")
    chosen = {}
    for phase in ("preopen", "auction"):
        phase_records = sorted(
            (r for r in preds if r.get("market_phase", "preopen") == phase),
            key=lambda r: int(r.get("revision", 1)),
        )
        for index, rec in enumerate(phase_records):
            time_part = (rec.get("recorded_at", "") or "T")[11:16] or "--:--"
            probs = rec.get("probs", {})
            prob_str = "Up {:.0f}% / Side {:.0f}% / Down {:.0f}%".format(
                probs.get("up", 0) or 0, probs.get("side", 0) or 0, probs.get("down", 0) or 0)
            extras = []
            if rec.get("opportunity") is not None:
                extras.append(f"机会分 {rec['opportunity']:.0f}")
            if rec.get("top_sector"):
                extras.append(f"主线 {rec['top_sector']}")
            if rec.get("regime"):
                extras.append(f"Regime {rec['regime']}")
            if rec.get("revision_reason"):
                extras.append(f"修订原因: {rec['revision_reason']}")
            marker = "（最新）" if index == len(phase_records) - 1 else ""
            print(f"[{time_part} {phase} r{rec.get('revision', 1)}]{marker} {prob_str}"
                  + ((" | " + " | ".join(extras)) if extras else ""))
        if phase_records:
            chosen[phase] = phase_records[-1]
    phase_label = {"preopen": "盘前", "auction": "竞价"}
    if not chosen:
        print("[预测] 无")
    if results:
        result = max(results, key=lambda r: int(r.get("revision", 1)))
        extras = [f"实际Top3: {', '.join(result.get('top_sectors', []))}"]
        if result.get("error_reasons"):
            extras.append("归因: " + ",".join(result["error_reasons"]))
        print(f"[收盘 实际] {STATE_CN[result['actual_state']]} Z_ATR={result['z_atr']} | " + " | ".join(extras))
    else:
        print("[收盘 实际] 尚未落盘")
        return 0
    if "preopen" in chosen and "auction" in chosen:
        b_pre = brier_multiclass(chosen["preopen"]["probs"], result["actual_state"])
        b_auc = brier_multiclass(chosen["auction"]["probs"], result["actual_state"])
        if b_auc < b_pre - 1e-9:
            verdict = "改对了"
        elif b_auc > b_pre + 1e-9:
            verdict = "改错了"
        else:
            verdict = "无实质变化"
        print(f"[竞价修订评价] {phase_label['preopen']} Brier={b_pre:.3f} -> {phase_label['auction']} Brier={b_auc:.3f} ：{verdict}")
    elif "preopen" in chosen:
        print("[竞价修订评价] 当日无竞价后验快照")
    return 0


def cmd_misses(args):
    """输出历史推演错案复盘卡（按单日 Brier 最差排序 Top N）"""
    records = read_records(args.ledger)
    selected_version = getattr(args, "filter_version", None) or getattr(args, "model_version", None)
    if not getattr(args, "all_versions", False) and selected_version:
        records = [r for r in records if r.get("model_version") == selected_version]

    phase = getattr(args, "market_phase", "preopen") or "preopen"
    preds_by_date = {}
    auctions_by_date = {}
    results_by_date = {}

    for r in records:
        rtype = r.get("type")
        d = r.get("date")
        if not d:
            continue
        if rtype == "prediction":
            r_phase = r.get("market_phase", "preopen")
            if r_phase == phase:
                if d not in preds_by_date or int(r.get("revision", 1)) > int(preds_by_date[d].get("revision", 1)):
                    preds_by_date[d] = r
            elif r_phase == "auction":
                if d not in auctions_by_date or int(r.get("revision", 1)) > int(auctions_by_date[d].get("revision", 1)):
                    auctions_by_date[d] = r
        elif rtype == "result":
            if d not in results_by_date or int(r.get("revision", 1)) > int(results_by_date[d].get("revision", 1)):
                results_by_date[d] = r

    common_dates = sorted(set(preds_by_date) & set(results_by_date))
    if not common_dates:
        print("[N/A] 台账中无成对的预测与收盘实际记录")
        return 0

    scored = []
    min_brier = getattr(args, "min_brier", 0.0) or 0.0
    for d in common_dates:
        pred = preds_by_date[d]
        res = results_by_date[d]
        brier = brier_multiclass(pred["probs"], res["actual_state"])
        if brier >= min_brier:
            scored.append((brier, d, pred, res, auctions_by_date.get(d)))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_n = getattr(args, "top", 5) or 5
    selected = scored[:top_n]

    print(f"=== 错案复盘集（按 {phase} Brier 降序 Top {len(selected)} / 共 {len(scored)} 起候选）===")
    if not selected:
        print(f"无 Brier >= {min_brier:.2f} 的错案记录")
        return 0

    for rank, (brier, d, pred, res, auc) in enumerate(selected, 1):
        probs = pred.get("probs", {})
        max_state = max(probs, key=probs.get) if probs else "N/A"
        pred_prob_str = f"Up {probs.get('up', 0):.0f}% / Side {probs.get('side', 0):.0f}% / Down {probs.get('down', 0):.0f}%"
        actual_state_cn = STATE_CN.get(res.get("actual_state"), res.get("actual_state", "N/A"))

        env_slices = []
        if pred.get("regime"):
            env_slices.append(f"Regime {pred['regime']}")
        if pred.get("coverage_band"):
            env_slices.append(f"覆盖率 {pred['coverage_band']}")
        if pred.get("volatility_band"):
            env_slices.append(f"波动率 {pred['volatility_band']}")
        if pred.get("data_status"):
            env_slices.append(f"数据状态 {pred['data_status']}")
        env_str = " | ".join(env_slices) if env_slices else "N/A"

        actual_top_sectors = ", ".join(res.get("top_sectors", [])) or "无"
        pred_top = pred.get("top_sector") or "无"
        reasons = ", ".join(res.get("error_reasons", [])) or "未填归因"

        print(f"\n【错案 #{rank} | {d} | Brier={brier:.3f}】")
        print(f"  • 预测: 最大概率【{STATE_CN.get(max_state, max_state)}】({pred_prob_str}) | 机会分: {pred.get('opportunity', 'N/A')} | 预估主线: {pred_top}")
        print(f"  • 实际: 走势【{actual_state_cn}】(Z_ATR={res.get('z_atr', 'N/A')}) | 实际领涨: {actual_top_sectors}")
        print(f"  • 环境: {env_str}")
        print(f"  • 归因: [{reasons}]")

        if auc:
            b_auc = brier_multiclass(auc["probs"], res["actual_state"])
            auc_probs = auc.get("probs", {})
            auc_max = max(auc_probs, key=auc_probs.get) if auc_probs else "N/A"
            if b_auc < brier - 1e-9:
                auc_note = f"修正为【{STATE_CN.get(auc_max, auc_max)}】(Brier改善至 {b_auc:.3f}，改对了)"
            elif b_auc > brier + 1e-9:
                auc_note = f"修正为【{STATE_CN.get(auc_max, auc_max)}】(Brier恶化至 {b_auc:.3f}，改错了)"
            else:
                auc_note = f"维持原判 (Brier={b_auc:.3f})"
            print(f"  • 竞价后验: {auc_note}")
        else:
            print("  • 竞价后验: 当日无 9:25 竞价修订记录")

    return 0


def cmd_report_mainline(args):
    """主线状态机转移台账：把每日状态落盘积累成实际转移频率矩阵"""
    if getattr(args, "all_versions", False):
        for version in ledger_versions(args.daily_ledger, {"daily_review"}):
            print(f"\n--- model_version={version} ---")
            child = argparse.Namespace(**vars(args))
            child.all_versions = False
            child.filter_version = version
            cmd_report_mainline(child)
        return
    selected_version = getattr(args, "filter_version", None) or getattr(args, "model_version", None)
    records = load_daily_ledger(args.daily_ledger, selected_version)
    seq = [(r["date"], str(r.get("mainline_sector", "")), r.get("mainline_state")) for r in records]
    observed = [item for item in seq if item[1] and item[2]]
    print(f"=== 主线状态机台账（累计 {len(observed)} 日观测，窗口 {args.window}） ===")
    if not observed:
        print("尚无主线状态记录。每日收盘复盘后执行 record-daily --mainline-sector <板块> --mainline-state <启动|强化|加速|分歧|弱化|退潮> [--sei <0-100>]")
        return
    observed = observed[-args.window:]
    for date, sector, state in observed[-10:]:
        print(f"  {date}  {sector}  {state}")

    per_sector = {}
    previous_sector = None
    switches = 0
    for _, sector, _state in observed:
        if previous_sector is not None and sector != previous_sector:
            switches += 1
        previous_sector = sector
    for date, sector, state in observed:
        per_sector.setdefault(sector, []).append((date, state))
    print(f"• 主线切换次数: {switches}（观测 {len(observed)} 日）")
    for sector, entries in per_sector.items():
        transitions = {}
        stays = {}
        previous_state = None
        for _date, state in entries:
            if previous_state is not None:
                if state == previous_state:
                    stays[previous_state] = stays.get(previous_state, 0) + 1
                else:
                    key = f"{previous_state} -> {state}"
                    transitions[key] = transitions.get(key, 0) + 1
            previous_state = state
        segments = sum(transitions.values()) + 1
        print(f"• {sector}: 观测 {len(entries)} 日，平均停留 {len(entries) / segments:.1f} 日/段")
        for key, count in sorted(transitions.items()):
            print(f"    {key}: {count} 次")
        if stays:
            print("    延续: " + " | ".join(f"{k}×{v}日" for k, v in sorted(stays.items())))
    if len(observed) < 30:
        print(f"[NOTE] 样本 {len(observed)} 日 < 30 日：转移频率仅供观察，不足以校准状态机概率；持续每日落盘。")
    else:
        print("[NOTE] 样本 ≥ 30 日：可用上述转移频率校准 SKILL 状态机的预期停留与转移概率，并披露样本期。")


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
    for cluster in EVIDENCE_CLUSTERS:
        p_rec.add_argument(f"--{cluster}", choices=EVIDENCE_STANCES,
                           help=f"证据簇 {cluster.upper()} 判档（对应 SKILL 似然表档位）")
    p_rec.add_argument("--r1", type=float, default=None, help="上证 R1 压力位（用于点位有效率）")
    p_rec.add_argument("--s1", type=float, default=None, help="上证 S1 支撑位（用于点位有效率）")
    p_rec.add_argument("--model-version", default=discover_model_version(), help="模型版本，默认读取当前项目版本")
    p_rec.add_argument("--formula-version", default=PREDICTION_FORMULA_VERSION, help="预测公式版本")
    p_rec.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_rec.add_argument("--market-phase", choices=("preopen", "auction"), default="preopen", help="预测阶段")
    p_rec.add_argument("--coverage-band", choices=("high", "medium", "low", "insufficient"), help="证据覆盖率分组")
    p_rec.add_argument("--volatility-band", choices=("low", "normal", "high"), help="波动率分组")
    p_rec.add_argument("--data-status", choices=("ok", "partial", "degraded"), help="数据状态分组")
    p_rec.add_argument("--revise", action="store_true", help="显式追加修订，不覆盖原预测")
    p_rec.add_argument("--revision-reason", help="修订原因；--revise 时必填")
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
    p_res.add_argument("--top1-sector-change", type=float, default=None,
                       help="当日实际第一主线板块涨幅%%（用于机会分有效性验证）")
    p_res.add_argument("--model-version", default=discover_model_version(), help="模型版本，须与对应预测一致")
    p_res.add_argument("--formula-version", default=PREDICTION_FORMULA_VERSION, help="结果归并公式版本")
    p_res.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_res.add_argument("--error-reasons", help="未命中归因，逗号分隔：data_missing/source_delay/event_shock/regime_misread/sector_mapping/threshold_issue/evidence_conflict/overconfidence")
    p_res.add_argument("--revise", action="store_true", help="显式追加结果纠错，不覆盖原记录")
    p_res.add_argument("--revision-reason", help="结果修订原因；--revise 时必填")
    p_res.set_defaults(func=cmd_result)

    p_rpt = sub.add_parser("report", help="输出滚动评估指标")
    p_rpt.add_argument("--window", type=int, default=20, help="滚动窗口天数 (默认 20)")
    p_rpt.add_argument("--model-version", default=discover_model_version(), help="默认统计的当前模型版本")
    p_rpt.add_argument("--filter-version", help="指定统计某个模型版本")
    p_rpt.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_rpt.add_argument("--market-phase", choices=("preopen", "auction"), default="preopen", help="分别评估盘前或竞价后验")
    p_rpt.add_argument("--validate-opportunity", action="store_true", help="输出机会分分层的有效性验证统计")
    p_rpt.set_defaults(func=cmd_report)

    p_replay = sub.add_parser("replay", help="当日推演化回放：盘前→竞价→收盘→修订对错")
    p_replay.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    p_replay.set_defaults(func=cmd_replay)

    p_misses = sub.add_parser("misses", help="错案集复盘：按单日 Brier 最差排序拉出上下文与归因卡")
    p_misses.add_argument("--top", type=int, default=5, help="输出最差 Top N 案例 (默认 5)")
    p_misses.add_argument("--min-brier", type=float, default=0.0, help="最小 Brier 门槛 (默认 0.0)")
    p_misses.add_argument("--market-phase", choices=("preopen", "auction"), default="preopen", help="评估阶段 (默认 preopen)")
    p_misses.add_argument("--model-version", default=discover_model_version(), help="默认统计的模型版本")
    p_misses.add_argument("--filter-version", help="指定统计某个模型版本")
    p_misses.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_misses.set_defaults(func=cmd_misses)

    p_ml = sub.add_parser("report-mainline", help="主线状态机转移台账：实际转移频率与停留时长")
    p_ml.add_argument("--window", type=int, default=120, help="滚动窗口交易日 (默认 120)")
    p_ml.add_argument("--model-version", default=discover_model_version(), help="默认统计的当前模型版本")
    p_ml.add_argument("--filter-version", help="指定统计某个模型版本")
    p_ml.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_ml.set_defaults(func=cmd_report_mainline)

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
    p_drec.add_argument("--mainline-sector", default="", help="当日第一主线板块（主线状态台账）")
    p_drec.add_argument("--mainline-state", choices=MAINLINE_STATES,
                        help="主线生命周期状态：启动/强化/加速/分歧/弱化/退潮")
    p_drec.add_argument("--sei", type=float, help="主线衰竭指数 SEI 0-100")
    p_drec.add_argument("--model-version", default=discover_model_version(), help="模型版本，默认读取当前项目版本")
    p_drec.add_argument("--formula-version", default=DAILY_FORMULA_VERSION, help="每日评分公式版本")
    p_drec.add_argument("--source-snapshot", help="关联的来源快照或 Handoff ID")
    p_drec.set_defaults(func=cmd_record_daily)

    p_drpt = sub.add_parser("report-daily", help="输出每日评分分布与固定阈值历史落位")
    p_drpt.add_argument("--window", type=int, default=60, help="滚动窗口交易日 (默认 60)")
    p_drpt.add_argument("--model-version", default=discover_model_version(), help="默认统计的当前模型版本")
    p_drpt.add_argument("--filter-version", help="指定统计某个模型版本")
    p_drpt.add_argument("--all-versions", action="store_true", help="按模型版本分组展示")
    p_drpt.add_argument("--extremes", action="store_true", help="输出情绪极值及其后续市场表现统计")
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
