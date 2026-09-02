# 个股报告卡数据契约

报告卡沿用既有字段，并增加以下诊断字段：

```json
{
  "logic_health": "稳定",
  "structure_timing": "等待确认",
  "company_risk_status": "中",
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
- `next_review_triggers` 至少包含两个可观察、可触发的条件；`evidence_freshness` 说明行情和财务数据截至日期。
- 正式渲染必须传入完整 JSON，不得依赖脚本内置演示值。
