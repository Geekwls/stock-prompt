"""战报卡机器输入的统一校验。"""

import re


REQUIRED_FIELDS = {
    "prediction": {"title", "date", "regime", "sentiment_score", "position", "opportunity_score", "top_sector", "evidence", "indices_full", "sectors_full", "chain_lines", "seat_lines", "trade_lines", "watchlist_full", "eval_summary", "risk_warning"},
    "daily": {"title", "date", "regime", "sentiment_score", "top_sector", "retention", "opportunity_score", "sentiment_breakdown", "regime_notes", "sectors_daily", "resonance_cards", "chain_lines", "stocks_pool", "opportunity_line", "strategy_line", "scenarios", "risk_line"},
    "rotation": {"title", "date_range", "summary", "volume_5d", "fund_flow", "institution_lines", "hotmoney_lines", "sei_breakdown", "chain_lines", "sentiment_5d", "zhongjun_anchor", "longtou_anchor", "watchlist"},
    "stock": {"stock_name", "stock_code", "date", "price", "coverage", "market_wind", "sector_role", "catalyst_level", "rs_rank", "wyckoff_phase", "position_status", "risk_reward_ratio", "logic_health", "structure_timing", "company_risk_status", "company_details", "hard_gate_status", "technical_layers_scored", "composite_score_status", "coverage_breakdown", "audit_status", "pledge_details", "dilution_status", "confidence_level", "research_status", "core_logic", "market_details", "sector_details", "catalyst_details", "rs_details", "wyckoff_details", "position_table", "rr_details", "evidence_map", "fusion_scores", "trade_strategy", "exit_plan", "falsification_rule", "next_review_triggers", "evidence_freshness"},
}


def validate_report_data(report_type, data):
    if report_type not in REQUIRED_FIELDS:
        raise ValueError("未知报告类型")
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象")
    missing = sorted(key for key in REQUIRED_FIELDS[report_type] if key not in data or data[key] is None or data[key] == "" or data[key] == [])
    if missing:
        raise ValueError("正式报告缺少必要字段: " + ", ".join(missing) + "。请补齐真实数据；如需示例图请显式使用 --demo。")
    if report_type != "stock":
        return
    if data["company_risk_status"] not in {"低", "中", "高", "极高", "N/A"}:
        raise ValueError("company_risk_status 只能为: 低 / 中 / 高 / 极高 / N/A")
    if data["hard_gate_status"] not in {"通过", "失败"}:
        raise ValueError("hard_gate_status 只能为: 通过 / 失败")
    if data["composite_score_status"] not in {"calculated", "not_applicable"}:
        raise ValueError("composite_score_status 只能为: calculated / not_applicable")
    if not isinstance(data["technical_layers_scored"], bool):
        raise ValueError("technical_layers_scored 必须为布尔值")
    if data["hard_gate_status"] == "失败":
        if data["technical_layers_scored"]:
            raise ValueError("行情硬门槛失败时 technical_layers_scored 必须为 false")
        if data["composite_score_status"] != "not_applicable":
            raise ValueError("行情硬门槛失败时不得计算综合评分")
        if data["structure_timing"] != "暂不评级" or data["confidence_level"] != "数据不足":
            raise ValueError("行情硬门槛失败时结构必须暂不评级且证据置信度必须为数据不足")
    coverage = str(data["coverage"])
    if not re.fullmatch(r"(?:100|\d{1,2})(?:\.\d+)?%", coverage):
        raise ValueError("coverage 必须为可复算的精确百分比，例如 75% 或 72.5%")
    coverage_value = float(coverage[:-1])
    if coverage_value > 100:
        raise ValueError("coverage 不得超过100%")
    breakdown = data["coverage_breakdown"]
    if not isinstance(breakdown, list) or len(breakdown) < 7:
        raise ValueError("coverage_breakdown 必须覆盖全部7个数据组")
    try:
        planned = [float(str(row[1]).rstrip("%")) for row in breakdown]
        obtained = [float(str(row[2]).rstrip("%")) for row in breakdown]
        if any(len(row) < 5 for row in breakdown):
            raise ValueError
    except (IndexError, TypeError, ValueError):
        raise ValueError("coverage_breakdown 每行必须包含数据组、计划权重、取得权重、证据编号和缺失项")
    if abs(sum(planned) - 100) > 0.01 or abs(sum(obtained) - coverage_value) > 0.01:
        raise ValueError("coverage 与 coverage_breakdown 权重不一致")
    if data["audit_status"] not in {"标准无保留", "保留", "否定", "无法表示", "未经审计", "N/A"}:
        raise ValueError("audit_status 不符合允许的审计状态枚举")
    if not isinstance(data["pledge_details"], list) or len(data["pledge_details"]) < 2:
        raise ValueError("pledge_details 必须同时包含两类质押比例")
    if not isinstance(data["next_review_triggers"], list) or len(data["next_review_triggers"]) < 2:
        raise ValueError("next_review_triggers 至少包含两个可观察的复核条件")
