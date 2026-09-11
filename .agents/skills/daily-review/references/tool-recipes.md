# daily-review 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与收盘事实采集配方

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
| **情绪五项加权分** | `python scripts/calculate.py calculate_market_sentiment_score --json '{"amount_score": 75, "breadth_score": 60, "limit_score": 70, "blown_score": 65, "ladder_score": 60}'` | 5项维度分 (0-100) |
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
    --sentiment-score 68 --continuity-score 75 --opportunity-score 54 \
    --mainline-sector 农业种植 --mainline-stage 强化期
```
