# sector-rotation 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与 5 日轮动采集配方

1. **优先调用 MCP `get_rotation_context`**：
   - 入参：`{"days": 5, "top_sectors_count": 5}`
   - 返回标准结构：
     * `indices_5d`：全 5 日宽基指数（沪指、深成指、创业板指、中证全指、沪深300）逐日涨跌幅与成交额；
     * `sectors_fund_flow_5d`：近 5 日行业主力净流入/净流出排行榜及累计净额；
     * `sentiment_5d`：近 5 日情绪序列（连板晋级率、炸板率、红盘率或情绪池替代序列）；
     * `dominant_sectors_kline`：核心主线板块 5/20/60 日区间涨幅与均线排列；
     * `coverage_audit`：覆盖天数（如 5/5）、原始权重覆盖率与归一化权重分配。
   - 降级规则：未注册 MCP 时，按定向模版检索 5 日成交、行业资金流与连板复盘；覆盖天数 <3 日或有效权重 <70% 时禁用 5 日量化分。

2. **席位与产业链深度补数**：
   - 调用 `get_longhubang_detail`（支持历史日期）核验领涨标的的机构/游资买卖席位与筹码锁定；
   - 调用 `get_sector_kline` 评估细分赛道量价结构与背离。

---

## 二、确定性计算函数配方

模型负责各维度特征定性与分档，精确计算统一调用 `scripts/calculate.py` 纯函数库：

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **主线衰竭指数 (SEI 直接打分)** | `python scripts/calculate.py calculate_sector_exhaustion --json '{"price_volume_divergence": 28, "relay_risk": 22, "capital_spillover": 14}'` | `price_volume_divergence` (0-40), `relay_risk` (0-30), `capital_spillover` (0-30) |
| **主线衰竭指数 (SEI 客观自动推导)** | `python scripts/calculate.py calculate_sector_exhaustion --json '{"new_high_shrink_days": 2, "divergence_ratio": 0.5, "relay_failed_ratio": 0.4, "break_rate": 0.2, "sector_turnover_share": 12, "low_position_spillover": 0.2, "auto_derive": true}'` | 缩量天数、背离比率、断板率、炸板率、成交占比、低位扩散比率；自动推导三项子分并输出 SEI |
| **存量吸血极化度** | `python scripts/calculate.py calculate_sector_cannibalization --json '{"leader_sector_turnover_share": 12.5, "market_amount_ratio": 0.95, "outflow_sectors_loss_rate": 2.1}'` | 领涨占比、两市成交额比、流出板块跌幅；输出 siphon_index 与受损板块 |
| **5日情绪温度加权分** | `python scripts/calculate.py calculate_5d_sentiment_score --json '{"daily_scores": [50, 65, 55, 70, 68], "weights": [0.05, 0.05, 0.20, 0.30, 0.40]}'` | `daily_scores`, `weights` |
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
  "risk_flags": ["主线SEI 64分(严重衰竭)"],
  "next_triggers": [{"id": "TRG-0912-925", "condition": "次日农业竞价金额比>=1.5且开盘溢价", "status": "pending"}]
}
JSON

# 2. 可选：战报长图卡片渲染
python scripts/generate_report_card.py --type rotation --json report.json
```
