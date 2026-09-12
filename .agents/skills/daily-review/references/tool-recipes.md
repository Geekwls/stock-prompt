# daily-review 工具调用与计算配方 (Tool Recipes)

## 一、数据获取配方

### 盘中快照（交易日 09:30–15:00）

- 分别调用 `get_index_kline`、`get_market_breadth`、`get_market_sentiment`、`get_sector_fund_flow`，必要时用 `get_stock_quote` 核验异动标的。
- 所有结论以当前 `as_of` 为截止点，`status=partial`；不生成全天 Z_ATR、收盘主线阶段或次日矩阵，不写 `result` / `record-daily` 台账。

### 收盘事实（15:00 后）

1. **优先调用 MCP `get_close_review_context`**：
   - 入参：`{"date_str": "YYYYMMDD", "top_sectors_count": 5}`
   - 返回标准结构：`indices`（收盘与涨跌幅）、`sentiment`（两市量能与真实炸板率）、`breadth`（精确红盘率分布）、`top_fund_flow_sectors`（主力资金排行榜）与 `mainline_limit_quality`（领涨主线封板质量）；
   - 自动包含冲突审计（如指数涨但红盘率偏低的二八分化预警）。
2. **多日资金延续性核验**：
   - 调用 MCP `get_sector_fund_flow(count=10, days=2)` 获取主线板块 T-1 与 T 日主力资金连续性；
   - 调用 MCP `get_sector_limit_quality(sector, date_str)` 获取主线封板质量与前缀安全归因。

---

## 二、确定性计算函数配方

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **情绪五项加权分** | `python scripts/calculate.py calculate_market_sentiment_score --json '{"amount_score": 75, "breadth_score": 60, "limit_score": 70, "blown_score": 65, "ladder_score": 60, "volume_dev": -5, "up_ratio": 58, "coverage": 100}'` | 5项维度分 (0-100)、`volume_dev`、`up_ratio`、`coverage`；缩量且红盘占优时自动封顶 60 |
| **连板梯队健康度** | `python scripts/calculate.py calculate_ladder_health --json '{"ladder_distribution": {"7": 1, "6": 0, "5": 0, "4": 0, "3": 0, "2": 2, "1": 15}}'` | `ladder_distribution` 字典；最高板 $\ge 4$ 且断层 $\ge 2$ 触发孤桩龙头预警 |
| **存量吸血极化度** | `python scripts/calculate.py calculate_sector_cannibalization --json '{"leader_sector_turnover_share": 12.5, "market_amount_ratio": 0.95, "outflow_sectors_loss_rate": 2.1}'` | 领涨占比、两市成交额比、流出板块跌幅；输出 siphon_index 与受损板块 |
| **资金延续评分** | `python scripts/calculate.py calculate_capital_continuity --json '{"amount_ratio": 0.85, "break_rate": 0.0909, "trigger_count": 5}'` | `amount_ratio` (0-1), `break_rate` (支持 0.0909 或 9.09 百分数自适应), `trigger_count` (<3 缺失归一化) |
| **实际 Z_ATR 状态** | `python scripts/calculate.py calculate_atr_state --json '{"close": 3940, "previous_close": 3932, "atr14": 35}'` | `close`, `previous_close`, `atr14` |
| **多分类 Brier 误差** | `python scripts/calculate.py calculate_multiclass_brier --json '{"probabilities": {"up": 0.36, "side": 0.48, "down": 0.16}, "actual_state": "side"}'` | `probabilities`, `actual_state` |

---

## 三、台账回测与不可变 Artifact 落地

```bash
# 15:00 收盘后：记录收盘结果（自动双写 close_actual Artifact）
python scripts/stock_prompt.py eval result --date YYYY-MM-DD --z-atr 0.22 \
    --top-sectors 农业种植,半导体,城市更新 --close 3940.55 --high 3955.0 --low 3930.0 --top1-sector-change 3.8

# 记录每日情绪与主线状态转移（自动双写 daily_score Artifact）
python scripts/stock_prompt.py eval record-daily --date YYYY-MM-DD \
    --sentiment-total 68 --capital-continuity 75 --opportunity 54 \
    --mainline-sector 农业种植 --mainline-state 强化
```
