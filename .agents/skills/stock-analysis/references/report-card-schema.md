# 个股报告卡数据契约

报告卡沿用既有字段，并增加以下诊断字段：

```json
{
  "logic_health": "稳定",
  "structure_timing": "等待确认",
  "hard_gate_status": "通过",
  "technical_layers_scored": true,
  "composite_score_status": "calculated",
  "coverage_breakdown": [
    ["复权行情与成交", "25%", "25%", "F01-F03", "无"],
    ["市场与行业基准", "12%", "12%", "F04-F05", "无"],
    ["板块归属与横截面", "10%", "10%", "F06", "无"],
    ["公告与催化", "13%", "13%", "F07-F08", "无"],
    ["财务质量与估值", "20%", "20%", "F09-F11", "无"],
    ["治理与重大风险", "10%", "10%", "F12-F13", "无"],
    ["目标位与流动性", "10%", "10%", "F14-F15", "无"]
  ],
  "company_risk_status": "中",
  "audit_status": "未经审计",
  "pledge_details": [
    ["质押股份/总股本", "N/A"],
    ["控股股东质押股份/其持股数", "N/A"]
  ],
  "dilution_status": "理论最大摊薄比例N/A，尚未实际发生",
  "next_review_triggers": ["关键结构位突破并完成回踩", "新财报或重大公告"],
  "evidence_freshness": "行情截至YYYY-MM-DD收盘，财务截至YYYY年QX",
  "company_details": [
    ["盈利质量", "收入与利润趋势及证据日期"],
    ["现金流", "经营现金流与利润匹配情况"],
    ["资产负债", "应收、存货、商誉、负债风险"],
    ["估值位置", "历史与行业可比口径"],
    ["治理事件", "减持、解禁、质押、问询、诉讼与审计意见"]
  ]
}
```

其余必需字段：

```text
stock_name, stock_code, date, price, coverage,
market_wind, sector_role, catalyst_level, rs_rank,
wyckoff_phase, position_status, risk_reward_ratio,
confidence_level, research_status, core_logic,
hard_gate_status, technical_layers_scored, composite_score_status,
coverage_breakdown, audit_status, pledge_details, dilution_status,
market_details, sector_details, catalyst_details, rs_details,
wyckoff_details, position_table, rr_details, evidence_map,
fusion_scores, trade_strategy, exit_plan, falsification_rule,
next_review_triggers, evidence_freshness
```

约束：

- `research_status` 组合双轴结论，例如 `【逻辑健康度：稳定｜结构位置：等待确认】`。
- `evidence_map` 应包含 L1–L8 八层结果。
- `fusion_scores` 应包含 L1–L8、参与评分权重及综合分区间；N/A 不得伪装成中性分。
- `confidence_level` 只能填写 `高 / 中 / 低 / 数据不足`。
- `company_details` 只写可核验信息；没有数据时写明 `N/A` 及缺失项。
- `company_risk_status` 使用 `低 / 中 / 高 / 极高 / N/A`，不得用含糊词替代。
- `hard_gate_status` 只能为 `通过 / 失败`。失败时 `structure_timing` 必须为“暂不评级”、`confidence_level` 必须为“数据不足”，L4–L7不得出现评分。
- 行情硬门槛失败时，`technical_layers_scored=false` 且 `composite_score_status=not_applicable`；通过门槛也不自动代表覆盖率足以计算综合分。
- `coverage` 必须是可复算的精确百分比，禁止“约75%”；`coverage_breakdown` 逐组列出计划权重、取得权重、证据编号与缺失项。
- `audit_status` 使用 `标准无保留 / 保留 / 否定 / 无法表示 / 未经审计 / N/A`。半年报未经审计时不得填写“未发现非标”。
- `pledge_details` 必须同时包含占总股本比例和占控股股东持股比例；`dilution_status` 区分理论上限与实际发行结果。
- `next_review_triggers` 至少包含两个可观察、可触发的条件；`evidence_freshness` 说明行情和财务数据截至日期。
- 正式渲染必须传入完整 JSON，不得依赖脚本内置演示值。
