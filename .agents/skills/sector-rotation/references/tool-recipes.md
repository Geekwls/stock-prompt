# sector-rotation 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与多周期轮动采集配方

1. **优先调用 MCP `get_rotation_context`**：
   - 入参：`{"days": 5, "sector_count": 10}`（`days` 取 2–10，`sector_count` 取 5–30）
   - 返回标准结构（payload 固定 5 个区块）：
     * `sector_fund_flows`：行业主力净流入/净流出与涨幅榜（东财行业口径，含 `top_inflow_sectors` / `top_outflow_sectors`）；
     * `index_trend`：核心宽基指数（沪指、创业板指、中证全指）走势对比；
     * `breadth_trend`：市场广度 / 红盘率序列；
     * `dominant_sectors_kline`：净流入前列主线板块逐板块的 5/20/60 日区间涨幅、均线排列（`ma_alignment`）与成交额；
     * `coverage_audit`：计划权重（T-4 至 T，近期不低于远期）、分块覆盖、`mainline_block_present` 与量化分门槛判定（`score_gate`）。
   - 降级规则：未注册 MCP 时，按定向模版检索 5 日成交、行业资金流与连板复盘；覆盖天数 <3 日或有效权重 <70% 时禁用 5 日量化分。
   - **量化分门槛**：`coverage_audit.score_gate == "enabled"` 才允许输出 5 日精确量化分；当 `mainline_block_present == false`（缺失 `dominant_sectors_kline`）时，即便其余三块齐全（75%）也强制 `disabled_qualitative_only`，只输出定性观察与待补清单。

2. **席位与产业链深度补数**：
   - 调用 `get_longhubang_detail`（支持历史日期）核验领涨标的的机构/游资买卖席位与筹码锁定；
   - 调用 `get_sector_kline` 评估细分赛道量价结构与背离。

---

## 二、确定性计算函数配方

模型负责各维度特征定性与分档，精确计算统一调用 `scripts/calculate.py` 纯函数库：

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **板块成交容量门槛审计** | `python scripts/calculate.py validate_sector_capacity --json '{"sector_amount_yi": 45.0, "market_total_amount_yi": 12000.0, "market_amount_baseline_yi": 12000.0}'` | `sector_amount_yi`, `market_total_amount_yi`, 可选 `market_amount_baseline_yi`（两市成交额基准，提供后按 baseline/10000 缩放绝对额门槛）；`mega_mainline` 需**同时**满足份额 ≥4% 与绝对额达标 |
| **资金跷跷板对冲矩阵** | `python scripts/calculate.py map_capital_seesaw_matrix --json '{"current_mainline": "AI算力与芯片", "current_lifecycle": "retreat", "counterpart_change_pct": 1.8, "counterpart_net_flow_yi": 32.0}'` | `current_mainline`, `current_lifecycle`；可选 `counterpart_change_pct` / `counterpart_net_flow_yi`（对手板块当日实测表现，传入后 `evidence_status=verified`，否则为 `unverified_rule_only`） |
| **电风扇无效轮动过滤器** | `python scripts/calculate.py assess_rotation_effectiveness --json '{"active_sectors_count": 5, "leader_turnover_share": 4.5, "limit_up_clusters": 1, "market_amount_ratio": 0.95}'` | `active_sectors_count`, `leader_turnover_share`, `limit_up_clusters`, `market_amount_ratio`（**四者均必填**，缺任一即返回 `N/A` / `unavailable`，不再有乐观默认值） |
| **中军与龙头背离审计** | `python scripts/calculate.py calculate_leader_core_divergence --json '{"core_trend": "break_ma20", "core_net_flow": -15.0, "leader_state": "limit_up", "leader_height": 4, "inner_up_ratio": 30.0}'` | `core_trend`, `core_net_flow`, `leader_state`, `leader_height`, `inner_up_ratio` |
| **多周期时间尺度识别** | `python scripts/calculate.py resolve_rotation_timeframe --json '{"catalyst_scope": "macro_trend", "duration_days": 25, "trend_ma20_slope": "up"}'` | `catalyst_scope`, `duration_days`, `trend_ma20_slope` |
| **主线衰竭指数 (SEI 客观自动推导)** | `python scripts/calculate.py calculate_sector_exhaustion --json '{"new_high_shrink_days": 2, "divergence_ratio": 0.5, "relay_failed_ratio": 0.4, "break_rate": 0.2, "sector_turnover_share": 12, "low_position_spillover": 0.2, "auto_derive": true}'` | 缩量天数、背离比率、断板率、炸板率、成交占比、低位扩散比率；输出 `components` 三项子分与 `calibration_status=uncalibrated`（权重 40/30/30 与阈值 30/60/80 未经历史校准） |
| **SEI 与生命周期一致性映射** | `python scripts/calculate.py map_exhaustion_to_lifecycle --json '{"sei": 55, "lifecycle_state": "高位分歧"}'` | `sei`（0–100）与/或 `lifecycle_state`；同时传入时输出 `consistent` 校验与 `conflict_note`，消除「SEI=55 良性分歧」与「高位分歧」并存的矛盾 |
| **轮动状态机 (State 1–4)** | `python scripts/calculate.py calculate_rotation_state --json '{"high_level_selloff": true, "low_position_inflow": true}'` | `core_share`, `positive_days`, `limit_up_count`, `defensive_flow`, `high_level_selloff`, 可选 `low_position_inflow`；State 2 输出 `high_to_low_status`（confirmed/failed/unverified） |
| **板块资金迁移矩阵** | `python scripts/calculate.py calculate_rotation_migration --json '{"daily_rankings": [["半导体","通信"], ["半导体","通信"], ["半导体","医药"]], "top_n": 5}'` | `daily_rankings`（T-4 至 T 逐日净流入排行，缺失日传 null，需 ≥3 个非空日）, `top_n`；区分 `sustained_sectors`（持续流入）与 `one_day_spike_sectors`（单日爆量） |
| **存量吸血极化度** | `python scripts/calculate.py calculate_sector_cannibalization --json '{"leader_sector_turnover_share": 12.5, "market_amount_ratio": 0.95, "outflow_sectors_loss_rate": 2.1}'` | 领涨占比、两市成交额比、流出板块跌幅；输出 siphon_index 与受损板块 |
| **5日情绪温度加权分** | `python scripts/calculate.py calculate_5d_sentiment_score --json '{"daily_scores": [50, 65, 55, 70, 68], "weights": [0.05, 0.05, 0.20, 0.30, 0.40]}'` | `daily_scores`, `weights`（权重须按 T-4 至 T 非递减，否则报错） |
| **资金延续性打分** | `python scripts/calculate.py calculate_capital_continuity --json '{"amount_ratio": 1.08, "break_rate": 0.28, "trigger_count": 5}'` | `amount_ratio`, `break_rate`, `trigger_count` |

---

## 三、交接落盘、不可变 Artifact 与战报渲染

```bash
# 1. 5日轮动交接摘要落盘（自动双写 rotation 标准 Artifact）
cat << 'JSON' | python scripts/handoff_store.py write --stdin
{
  "report_type": "rotation",
  "as_of": "2026-09-11 15:00",
  "source_count": 8,
  "coverage": "95%",
  "scored_weight": "100%",
  "confidence": "高",
  "regime_namespace": "rotation-state-1-4",
  "market_regime": "State 2: 畏高切低/补涨",
  "primary_sectors": ["农业种植", "基础化工"],
  "watchlist": ["600371", "002588"],
  "risk_flags": ["主线SEI 64分(严重衰竭)", "中军背离出货风险"],
  "next_triggers": [
    {
      "id": "TRG-0912-925",
      "trigger_type": "竞价强弱",
      "condition": "次日农业竞价金额比>=1.5且开盘溢价",
      "status": "pending",
      "condition_above": "竞价金额比>=2.0且高开>=2%",
      "action_above": "确认新主线启动，第一波低吸切入",
      "condition_below": "竞价低开且金额比<1.0",
      "action_below": "判定为虚假脉冲，放弃买入计划"
    }
  ]
}
JSON

# 2. 可选：战报长图卡片渲染
python scripts/generate_report_card.py --type rotation --json report.json
```

---

## 四、战术结论评估台账（可选持久化）

轮动报告的结论必须可被次日行情证伪。收盘复盘后把当日战术结论落盘，次日回填实际结果，累积后即可校准 SKILL 判定阈值：

```bash
# 1. 收盘落盘当日战术结论（rotation_type 来自 assess_rotation_effectiveness，divergence_type 来自 calculate_leader_core_divergence）
python scripts/eval_tracker.py record-daily --date 2026-09-28 \
  --rotation-type electric_fan --divergence-type core_desertion \
  --opportunity 55

# 2. 次日回填实际结果（confirmed / failed / unverifiable）
python scripts/eval_tracker.py reconcile-tactics --date 2026-09-28 \
  --rotation-outcome confirmed --divergence-outcome failed --note "次日主线延续但中军回落"

# 3. 输出历史命中率（unverifiable 不计入分母；可判定样本 <20 时仅作观察）
python scripts/eval_tracker.py report-tactics --window 60
```

`record-daily` 仅落盘结论不构成验证；未回填结果的日期在 `report-tactics` 中不计入命中率。台账不可用时在报告中标注 `evaluation_status=emitted_only`，不影响专业分析完成。
