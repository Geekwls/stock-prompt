# -*- coding: utf-8 -*-
"""UI 结构化事件协议路由与执行调度器 (UI Event Router)。

实现 UI 交互层与 Agent 模型层解耦：
- 确定性事件（view_evidence / render_report / retry_data / view_calibration）直接交由工具层处理，不消耗 LLM；
- 分析推理事件（start_preopen / update_auction / run_close_review / run_rotation / diagnose_stock）定向分发至专业 Skill。
"""

from typing import Any, Callable, Dict, List, Optional

from tools.agent_tools import (
    evaluate_prediction_tool,
    load_artifact_tool,
    render_report_tool,
    save_artifact_tool,
)

VALID_EVENTS = {
    "start_preopen",
    "update_auction",
    "run_close_review",
    "run_rotation",
    "diagnose_stock",
    "view_evidence",
    "view_calibration",
    "retry_data",
    "render_report",
    "save_artifact",
    "load_artifact",
    "evaluate_prediction",
}

DETERMINISTIC_EVENTS = {
    "view_evidence",
    "view_calibration",
    "retry_data",
    "render_report",
    "save_artifact",
    "load_artifact",
    "evaluate_prediction",
}

EVENT_TO_SKILL = {
    "start_preopen": "market-prediction",
    "update_auction": "market-prediction",
    "run_close_review": "daily-review",
    "run_rotation": "sector-rotation",
    "diagnose_stock": "stock-analysis",
}


def validate_ui_event(event: Dict[str, Any]) -> List[str]:
    """轻量校验 UI 事件字典是否符合 Schema 约束，返回错误列表。"""
    errors = []
    if not isinstance(event, dict):
        return ["事件格式必须是字典对象"]
    event_name = event.get("event")
    if not event_name or not isinstance(event_name, str):
        errors.append("缺失或非法的 'event' 字段")
    elif event_name not in VALID_EVENTS:
        errors.append(f"未知事件类型: {event_name}")

    timestamp = event.get("timestamp")
    if not timestamp or not isinstance(timestamp, str):
        errors.append("缺失或非法的 'timestamp' 字段")

    payload = event.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append("'payload' 必须是字典对象")
    elif isinstance(payload, dict) and event_name == "diagnose_stock":
        if not payload.get("symbol") or not str(payload.get("symbol")).strip():
            errors.append("diagnose_stock 事件必须在 payload 中提供有效 'symbol'")
    if isinstance(payload, dict) and event_name == "save_artifact" and not isinstance(payload.get("artifact"), dict):
        errors.append("save_artifact 事件必须在 payload 中提供 'artifact' 对象")

    context = event.get("context")
    if context is not None and not isinstance(context, dict):
        errors.append("'context' 必须是字典对象")
    elif isinstance(context, dict) and context.get("artifact_ids") is not None:
        artifact_ids = context["artifact_ids"]
        if not isinstance(artifact_ids, list) or not all(isinstance(item, str) for item in artifact_ids):
            errors.append("context.artifact_ids 必须是字符串数组")

    if isinstance(payload, dict) and event_name in {"view_calibration", "evaluate_prediction"}:
        context_ids = context.get("artifact_ids", []) if isinstance(context, dict) else []
        if not payload.get("prediction_snapshot_id") and not context_ids:
            errors.append(f"{event_name} 事件缺少 prediction_snapshot_id")
        if not payload.get("actual_snapshot_id") and len(context_ids) < 2:
            errors.append(f"{event_name} 事件缺少 actual_snapshot_id")

    return errors


def route_ui_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """对 UI 事件执行路由判定。

    Returns:
        {
            "valid": bool,
            "event": str,
            "requires_llm": bool,
            "target_skill": Optional[str],
            "action": str,
            "parameters": dict,
            "errors": list
        }
    """
    errors = validate_ui_event(event)
    if errors:
        return {
            "valid": False,
            "event": event.get("event", "unknown") if isinstance(event, dict) else "unknown",
            "requires_llm": False,
            "target_skill": None,
            "action": "reject",
            "parameters": {},
            "errors": errors,
        }

    event_name = event["event"]
    payload = event.get("payload", {}) or {}
    context = event.get("context", {}) or {}

    if event_name in DETERMINISTIC_EVENTS:
        return {
            "valid": True,
            "event": event_name,
            "requires_llm": False,
            "target_skill": None,
            "action": f"execute_tool_{event_name}",
            "parameters": {**payload, "context": context},
            "errors": [],
        }

    target_skill = EVENT_TO_SKILL.get(event_name)
    return {
        "valid": True,
        "event": event_name,
        "requires_llm": True,
        "target_skill": target_skill,
        "action": f"invoke_{target_skill}",
        "parameters": {**payload, "context": context},
        "errors": [],
    }


def _artifact_id(event: Dict[str, Any]) -> Optional[str]:
    payload = event.get("payload", {}) or {}
    context = event.get("context", {}) or {}
    ids = context.get("artifact_ids", []) or []
    return payload.get("snapshot_id") or (ids[0] if ids else None)


def _execute_view_evidence(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    payload = event.get("payload", {}) or {}
    loaded = load_artifact_tool(_artifact_id(event), artifact_root=artifact_root)
    if loaded.get("data_status") != "ok":
        return loaded
    artifact = loaded["payload"]
    layer_id = payload.get("layer_id")
    if layer_id:
        layer = (artifact.get("layers") or {}).get(layer_id)
        if layer is None:
            return {
                "data_status": "unavailable", "source": "stock-prompt-event-router",
                "error": f"Artifact 不含证据层 {layer_id}", "payload": {},
                "missing": [layer_id], "conflicts": [],
            }
        loaded["payload"] = {"snapshot_id": artifact.get("snapshot_id"), "layer_id": layer_id, "evidence": layer}
    return loaded


def _execute_view_calibration(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    payload = event.get("payload", {}) or {}
    context_ids = (event.get("context", {}) or {}).get("artifact_ids", []) or []
    prediction_id = payload.get("prediction_snapshot_id") or (context_ids[0] if context_ids else None)
    actual_id = payload.get("actual_snapshot_id") or (context_ids[1] if len(context_ids) > 1 else None)
    return evaluate_prediction_tool(prediction_id, actual_id, artifact_root=artifact_root)


def _execute_retry_data(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    """重采需要专业 Skill/数据工具参与，返回明确的后续分发而非伪造成功。"""
    payload = event.get("payload", {}) or {}
    target_stage = payload.get("target_stage")
    target_skill = EVENT_TO_SKILL.get(target_stage, target_stage)
    return {
        "data_status": "partial",
        "source": "stock-prompt-event-router",
        "payload": {
            "dispatch": "skill",
            "target_skill": target_skill,
            "reason": "retry_data 需要重新获取外部数据并由专业 Skill 复核",
            "parameters": payload,
        },
        "missing": [],
        "conflicts": [],
    }


def _execute_render_report(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    payload = dict(event.get("payload", {}) or {})
    payload.setdefault("snapshot_id", _artifact_id(event))
    allowed = {"snapshot_id", "report_type", "report_data", "theme", "output_format", "output_name"}
    return render_report_tool(
        **{key: value for key, value in payload.items() if key in allowed},
        artifact_root=artifact_root,
        report_root=report_root,
    )


def _execute_save_artifact(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    return save_artifact_tool((event.get("payload", {}) or {}).get("artifact"), artifact_root=artifact_root)


def _execute_load_artifact(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    payload = event.get("payload", {}) or {}
    allowed = {"snapshot_id", "artifact_type", "trading_date", "subject"}
    return load_artifact_tool(
        **{key: value for key, value in payload.items() if key in allowed},
        artifact_root=artifact_root,
    )


def _execute_evaluate_prediction(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    return _execute_view_calibration(event, artifact_root=artifact_root, report_root=report_root)


EVENT_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "view_evidence": _execute_view_evidence,
    "view_calibration": _execute_view_calibration,
    "retry_data": _execute_retry_data,
    "render_report": _execute_render_report,
    "save_artifact": _execute_save_artifact,
    "load_artifact": _execute_load_artifact,
    "evaluate_prediction": _execute_evaluate_prediction,
}


def execute_ui_event(event: Dict[str, Any], *, artifact_root=None, report_root=None) -> Dict[str, Any]:
    """校验并执行确定性 UI 事件；推理事件返回专业 Skill 分发指令。"""
    routed = route_ui_event(event)
    if not routed["valid"]:
        return routed
    if routed["requires_llm"]:
        return {
            **routed,
            "executed": False,
            "result": {
                "data_status": "partial",
                "source": "stock-prompt-event-router",
                "payload": {"dispatch": "skill", "target_skill": routed["target_skill"], "parameters": routed["parameters"]},
                "missing": [],
                "conflicts": [],
            },
        }
    handler = EVENT_HANDLERS[event["event"]]
    return {**routed, "executed": True, "result": handler(event, artifact_root=artifact_root, report_root=report_root)}
