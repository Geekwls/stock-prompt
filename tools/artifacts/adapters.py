"""从既有台账与交接记录转换为标准 Artifact 的双写适配器。

设计约束（与 v7.2.0 基线一致）：
- 只做只读转换，不改写既有 Handoff / Thesis / 评估台账；
- 快照 ID 确定性派生（同源记录重复镜像天然幂等，存储层再以不可覆盖约束兜底）；
- 低覆盖率（coverage_band=insufficient 或 coverage<50%）不得生成精确概率与机会分，
  一律降级为条件化 Artifact（probabilities/opportunity_score = null，status=degraded）；
- 任何失败由调用方捕获后仅告警，绝不影响报告与台账写入。
"""

import hashlib
import json

LOW_COVERAGE_BANDS = {"insufficient"}


def _digest(*parts):
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:10]


def _coverage_percent(record):
    coverage = str(record.get("coverage", "") or "").strip()
    if coverage.endswith("%"):
        return coverage
    if coverage == "N/A":
        return "N/A"
    return "N/A"


def _is_low_coverage(record):
    band = str(record.get("coverage_band", "") or "").lower()
    if band in LOW_COVERAGE_BANDS:
        return True
    coverage = _coverage_percent(record)
    if coverage.endswith("%"):
        try:
            return float(coverage[:-1]) < 50
        except ValueError:
            return False
    return False


def _common(record, artifact_type, snapshot_suffix, formula_version):
    trading_date = str(record.get("date") or str(record.get("as_of", ""))[:10] or "")[:10]
    data_status = record.get("data_status")
    if data_status not in ("ok", "partial", "unavailable"):
        data_status = "ok"
    return {
        "artifact_type": artifact_type,
        "schema_version": "1.0",
        "snapshot_id": f"{artifact_type}-{trading_date}-{snapshot_suffix}",
        "trading_date": trading_date,
        "as_of": str(record.get("recorded_at") or record.get("as_of") or trading_date),
        "data_status": data_status,
        "coverage": _coverage_percent(record),
        "coverage_band": record.get("coverage_band") or "unknown",
        "evidence_ids": list(record.get("evidence_ids") or []),
        "model_version": record.get("model_version") or "unknown",
        "formula_version": formula_version,
        "status": "degraded" if _is_low_coverage(record) else "complete",
        "source_kind": "dual_write",
    }


def _top_sectors(record):
    sectors = [str(s) for s in (record.get("top_sectors") or []) if str(s).strip()]
    if not sectors and record.get("top_sector"):
        sectors = [str(record["top_sector"])]
    return sectors


def mirror_prediction_record(record, parent_lookup=None):
    """盘前预测 → prediction（PREOPEN_V1）；9:25 修订 → auction（AUCTION_V2，必须引用既有 PREOPEN 快照）。"""
    phase = str(record.get("market_phase", "preopen"))
    source_snapshot = str(record.get("snapshot_id") or _digest(record))
    common = _common(record, "prediction" if phase == "preopen" else "auction",
                     _digest(source_snapshot), record.get("formula_version", "prediction-v2"))
    low = _is_low_coverage(record)
    probs = record.get("probs")
    if phase == "preopen":
        common.update({
            "stage": "PREOPEN_V1",
            "market_regime": str(record.get("regime", "")),
            "probabilities": None if low else {
                "up": float(probs["up"]), "side": float(probs["side"]), "down": float(probs["down"]),
            },
            "opportunity_score": None if low else record.get("opportunity"),
            "top_sectors": _top_sectors(record),
            "r1": record.get("r1"),
            "s1": record.get("s1"),
        })
        if low:
            common["missing"] = ["precise_probabilities_suppressed_low_coverage"]
        return common
    parent = (parent_lookup or _default_parent_lookup)(str(common["trading_date"]))
    if not parent:
        raise ValueError("auction 镜像需要先存在同日 PREOPEN Artifact 作为 parent_snapshot_id")
    delta = []
    if record.get("revision_reason"):
        delta.append(str(record["revision_reason"]))
    common.update({
        "stage": "AUCTION_V2",
        "parent_snapshot_id": parent,
        "posterior_probabilities": None if low else {
            "up": float(probs["up"]), "side": float(probs["side"]), "down": float(probs["down"]),
        },
        "information_delta": delta,
        "top_sectors": _top_sectors(record),
    })
    if low:
        common["missing"] = ["precise_probabilities_suppressed_low_coverage"]
    return common


def _default_parent_lookup(trading_date):
    from tools.artifacts.store import select_artifacts

    candidates = select_artifacts(artifact_type="prediction", trading_date=trading_date)
    return candidates[-1]["snapshot_id"] if candidates else None


def mirror_result_record(record):
    """收盘结果 → close_actual（CLOSE_ACTUAL）。"""
    common = _common(record, "close_actual", _digest(record.get("snapshot_id") or record),
                     record.get("formula_version", "prediction-v2"))
    common.update({
        "stage": "CLOSE_ACTUAL",
        "actual_state": record.get("actual_state"),
        "z_atr": float(record["z_atr"]),
        "top_sectors": _top_sectors(record),
        "close": record.get("close"),
        "high": record.get("high"),
        "low": record.get("low"),
    })
    if record.get("top1_sector_change") is not None:
        common["top1_sector_change"] = record["top1_sector_change"]
    if record.get("error_reasons"):
        common["error_reasons"] = list(record["error_reasons"])
    return common


def mirror_daily_record(record):
    """每日复盘评分 → daily_score（DAILY_SCORE_V1，含主线状态）。"""
    common = _common(record, "daily_score", _digest(record), record.get("formula_version", "daily-v2"))
    metrics = {
        key: record[key]
        for key in ("up_ratio", "premium", "promotion", "break_rate", "volume_dev",
                    "sentiment_total", "capital_continuity", "opportunity",
                    "mainline_sector", "mainline_state", "sei")
        if record.get(key) is not None
    }
    common.update({"metrics": metrics, "top_sector": record.get("top_sector")})
    return common


def mirror_handoff(payload):
    """板块轮动交接 → rotation；个股诊断交接 → stock_diagnostic（按 subject 隔离）。"""
    report_type = str(payload.get("report_type", ""))
    if report_type == "rotation":
        common = _common(payload, "rotation", _digest(payload.get("previous_snapshot_id") or payload),
                         "rotation-v1")
        common.update({
            "window": 5,
            "rotation_state": str(payload.get("market_regime", "N/A")),
            "sector_ranking": [str(s) for s in payload.get("primary_sectors", [])],
            "exhaustion_score": None,
            "watchlist": [str(s) for s in payload.get("watchlist", [])],
        })
        return common
    if report_type == "stock":
        subject = payload.get("subject") or {}
        if not subject.get("id"):
            raise ValueError("stock 交接镜像需要 subject.id")
        common = _common(payload, "stock_diagnostic", _digest(subject.get("id"), payload.get("as_of")),
                         "stock-v1")
        triggers = payload.get("next_triggers", [])
        pending = [t.get("condition", str(t)) if isinstance(t, dict) else str(t) for t in triggers]
        common.update({
            "subject": {"type": "stock", "id": str(subject["id"]), "name": str(subject.get("name", ""))},
            "layers": {"source": "handoff_summary"},
            "logic_health": str(payload.get("logic_health") or "暂不评级"),
            "structure_position": str(payload.get("structure_position") or "暂不评级"),
            "confidence": str(payload.get("confidence", "数据不足")),
            "confirmation_conditions": pending,
            "invalidation_conditions": [str(flag) for flag in payload.get("risk_flags", [])],
        })
        return common
    return None


def mirror_and_store(kind, record):
    """双写入口：转换并落盘。已存在（幂等重放）返回既有路径，失败向上抛出由调用方降级。"""
    from tools.artifacts.store import save_artifact

    if kind in ("prediction", "auction"):
        payload = mirror_prediction_record(record)
    elif kind == "close_actual":
        payload = mirror_result_record(record)
    elif kind == "daily_score":
        payload = mirror_daily_record(record)
    elif kind == "handoff":
        payload = mirror_handoff(record)
        if payload is None:
            return None
    else:
        raise ValueError(f"未知镜像类型: {kind}")
    try:
        return save_artifact(payload)
    except FileExistsError:
        from tools.artifacts.store import state_root

        return state_root() / f"{payload['snapshot_id']}.json"
