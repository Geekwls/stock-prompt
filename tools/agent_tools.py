"""Agent 可直接调用的研究闭环工具门面。

这里集中封装 Artifact 存取、预测评估与报告渲染。MCP 服务和 UI 事件
路由只负责参数转发，避免在多个入口重复实现业务规则。
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from tools.artifacts.store import load_artifact, save_artifact, select_artifacts
from tools.calculations.metrics import calculate_multiclass_brier, calculate_topk_metrics


SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
ARTIFACT_TYPES = {
    "prediction", "auction", "close_actual", "daily_score",
    "rotation", "stock_diagnostic", "evidence",
}
REPORT_TYPES = {"prediction", "daily", "rotation", "stock"}


def _ok(source: str, payload: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    return {
        "data_status": "ok",
        "source": source,
        "payload": payload,
        "missing": [],
        "conflicts": [],
        **extra,
    }


def _error(message: str, *, missing=None) -> Dict[str, Any]:
    return {
        "data_status": "unavailable",
        "source": "stock-prompt-agent-tools",
        "error": message,
        "payload": {},
        "missing": list(missing or []),
        "conflicts": [],
    }


def save_artifact_tool(payload: Dict[str, Any], *, artifact_root=None) -> Dict[str, Any]:
    """校验并不可变保存一个标准 Artifact。"""
    try:
        path = save_artifact(payload, artifact_root)
    except (OSError, TypeError, ValueError, FileExistsError) as exc:
        return _error(str(exc))
    return _ok(
        "stock-prompt-artifact-store",
        {"snapshot_id": payload["snapshot_id"], "artifact_type": payload["artifact_type"], "path": str(path)},
        formula_version=payload.get("formula_version"),
    )


def load_artifact_tool(
    snapshot_id: Optional[str] = None,
    *,
    artifact_type: Optional[str] = None,
    trading_date: Optional[str] = None,
    subject: Optional[str] = None,
    artifact_root=None,
) -> Dict[str, Any]:
    """按快照 ID 精确读取，或按类型/日期/标的读取最新 Artifact。"""
    if artifact_type is not None and artifact_type not in ARTIFACT_TYPES:
        return _error(f"未知 artifact_type: {artifact_type}")
    try:
        if snapshot_id:
            artifact = load_artifact(snapshot_id, artifact_root)
        else:
            candidates = select_artifacts(artifact_root, artifact_type, trading_date, subject)
            artifact = candidates[-1] if candidates else None
    except (OSError, TypeError, ValueError) as exc:
        return _error(str(exc))
    if artifact is None:
        return _error("未找到匹配的 Artifact", missing=[snapshot_id or artifact_type or "artifact_selector"])
    return _ok(
        "stock-prompt-artifact-store",
        artifact,
        snapshot_id=artifact.get("snapshot_id"),
        formula_version=artifact.get("formula_version"),
    )


def evaluate_prediction_tool(
    prediction_snapshot_id: str,
    actual_snapshot_id: str,
    *,
    artifact_root=None,
) -> Dict[str, Any]:
    """用收盘实际 Artifact 对盘前/竞价预测进行确定性评估。"""
    prediction_result = load_artifact_tool(prediction_snapshot_id, artifact_root=artifact_root)
    actual_result = load_artifact_tool(actual_snapshot_id, artifact_root=artifact_root)
    if prediction_result["data_status"] != "ok":
        return _error("预测 Artifact 不可用", missing=[prediction_snapshot_id])
    if actual_result["data_status"] != "ok":
        return _error("收盘实际 Artifact 不可用", missing=[actual_snapshot_id])

    prediction = prediction_result["payload"]
    actual = actual_result["payload"]
    if prediction.get("artifact_type") not in {"prediction", "auction"}:
        return _error("prediction_snapshot_id 必须指向 prediction 或 auction Artifact")
    if actual.get("artifact_type") != "close_actual":
        return _error("actual_snapshot_id 必须指向 close_actual Artifact")
    if prediction.get("trading_date") != actual.get("trading_date"):
        return _error("预测与收盘实际的 trading_date 不一致")

    probabilities = prediction.get("probabilities") or prediction.get("posterior_probabilities")
    actual_state = actual.get("actual_state")
    if not isinstance(probabilities, dict):
        return _error("预测 Artifact 不含可评估概率（可能因低覆盖率被抑制）", missing=["probabilities"])
    brier = calculate_multiclass_brier(probabilities, actual_state, prediction_snapshot_id)
    if brier.get("status") not in {"complete", "partial"} or brier.get("value") == "N/A":
        return _error("预测概率或实际状态不完整", missing=brier.get("missing"))

    predicted_state = max(("up", "side", "down"), key=lambda state: probabilities[state])
    sector_metrics = calculate_topk_metrics(
        prediction.get("top_sectors", []), actual.get("top_sectors", []), 3, prediction_snapshot_id
    )
    r1, s1 = prediction.get("r1"), prediction.get("s1")
    high, low = actual.get("high"), actual.get("low")
    point_checks = {
        "r1_touched": bool(isinstance(r1, (int, float)) and isinstance(high, (int, float)) and high >= r1),
        "s1_touched": bool(isinstance(s1, (int, float)) and isinstance(low, (int, float)) and low <= s1),
    }
    return _ok(
        "stock-prompt-evaluation-engine",
        {
            "trading_date": prediction["trading_date"],
            "prediction_snapshot_id": prediction_snapshot_id,
            "actual_snapshot_id": actual_snapshot_id,
            "predicted_state": predicted_state,
            "actual_state": actual_state,
            "direction_hit": predicted_state == actual_state,
            "brier_score": brier["value"],
            "top3_sector_metrics": sector_metrics["value"],
            **point_checks,
        },
        formula_version="prediction-evaluation-v1",
    )


def _report_root(explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    override = os.environ.get("STOCK_PROMPT_REPORT_DIR")
    return Path(override).expanduser() if override else Path.home() / ".stock-prompt" / "reports"


def _markdown_report(artifact: Dict[str, Any]) -> str:
    subject = artifact.get("subject") or {}
    title = subject.get("name") or subject.get("id") or artifact.get("artifact_type", "研究")
    summary = artifact.get("summary_card") or {}
    lines = [
        f"# {title} 研究报告",
        "",
        f"- 快照：`{artifact.get('snapshot_id', 'N/A')}`",
        f"- 日期：{artifact.get('trading_date', 'N/A')}",
        f"- 数据状态：{artifact.get('data_status', 'N/A')}",
        f"- 覆盖率：{artifact.get('coverage', 'N/A')}",
        f"- 结论：{summary.get('summary') or artifact.get('logic_health') or artifact.get('market_regime') or 'N/A'}",
        "",
        "## 结构化数据",
        "",
        "```json",
        json.dumps(artifact, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def _report_runtime():
    """定位仓库母本或安装包内任一完整的报告卡运行时。"""
    from tools.artifacts.store import project_root

    root = project_root()
    candidates = [root / "scripts"] + [
        root / skill / "scripts"
        for skill in ("daily-review", "market-prediction", "sector-rotation", "stock-analysis")
    ]
    scripts_dir = next((path for path in candidates if (path / "generate_report_card.py").is_file()), None)
    if scripts_dir is None:
        raise ImportError("未找到报告卡渲染运行时")
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from generate_report_card import (
        render_daily_review_card, render_report_card,
        render_sector_rotation_card, render_stock_analysis_card,
    )
    from report_card.validation import validate_report_data

    return validate_report_data, {
        "prediction": render_report_card,
        "daily": render_daily_review_card,
        "rotation": render_sector_rotation_card,
        "stock": render_stock_analysis_card,
    }


def render_report_tool(
    *,
    snapshot_id: Optional[str] = None,
    report_type: Optional[str] = None,
    report_data: Optional[Dict[str, Any]] = None,
    theme: str = "light",
    output_format: str = "png",
    output_name: Optional[str] = None,
    artifact_root=None,
    report_root=None,
) -> Dict[str, Any]:
    """将完整报告数据渲染为 PNG，或将任意 Artifact 渲染为 Markdown。"""
    if theme not in {"light", "dark"}:
        return _error("theme 只能是 light 或 dark")
    if output_format not in {"png", "markdown"}:
        return _error("output_format 只能是 png 或 markdown")

    artifact = None
    if snapshot_id:
        loaded = load_artifact_tool(snapshot_id, artifact_root=artifact_root)
        if loaded["data_status"] != "ok":
            return loaded
        artifact = loaded["payload"]
        if report_data is None:
            report_data = artifact.get("report_data")
        if report_type is None:
            report_type = {
                "prediction": "prediction", "auction": "prediction", "daily_score": "daily",
                "rotation": "rotation", "stock_diagnostic": "stock",
            }.get(artifact.get("artifact_type"))

    suffix = ".md" if output_format == "markdown" else ".png"
    output_name = output_name or f"report_{snapshot_id or report_type or 'research'}{suffix}"
    if not output_name.endswith(suffix):
        output_name += suffix
    if not SAFE_OUTPUT_NAME.fullmatch(output_name):
        return _error("output_name 只能包含字母、数字、点、下划线或连字符")
    destination_root = _report_root(report_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / output_name

    try:
        if output_format == "markdown":
            if artifact is None:
                return _error("Markdown 渲染需要 snapshot_id")
            destination.write_text(_markdown_report(artifact), encoding="utf-8")
        else:
            if report_type not in REPORT_TYPES:
                return _error("PNG 渲染需要有效 report_type")
            if not isinstance(report_data, dict):
                return _error("PNG 渲染需要完整 report_data；Artifact 可通过 report_data 字段携带")
            validate_report_data, renderers = _report_runtime()
            validate_report_data(report_type, report_data)
            renderer = renderers[report_type]
            renderer(data=report_data, output_path=str(destination), theme=theme)
    except (ImportError, OSError, TypeError, ValueError) as exc:
        return _error(str(exc))

    return _ok(
        "stock-prompt-report-renderer",
        {"path": str(destination), "format": output_format, "report_type": report_type},
        formula_version="report-render-v1",
    )
