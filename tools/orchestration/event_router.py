# -*- coding: utf-8 -*-
"""UI 结构化事件协议路由与状态机调度器 (UI Event Router)。

实现 UI 交互层与 Agent 模型层解耦：
- 确定性事件（view_evidence / render_report / retry_data / view_calibration）直接交由工具层处理，不消耗 LLM；
- 分析推理事件（start_preopen / update_auction / run_close_review / run_rotation / diagnose_stock）定向分发至专业 Skill。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
}

DETERMINISTIC_EVENTS = {
    "view_evidence",
    "view_calibration",
    "retry_data",
    "render_report",
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
