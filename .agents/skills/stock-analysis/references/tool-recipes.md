# stock-analysis 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与个股诊断采集配方

1. **优先调用 MCP `get_stock_diagnostic_context`**：
   - 入参：`{"symbol": "600371", "sector": "农业种植", "benchmark_index": "SHCI"}`
   - 返回标准结构：
     * `stock_kline`：前复权日K OHLCV、均线簇 (MA5/20/50/120/250)、ATR14、Bias、20日量比、120日量能分位与3年价格分位；
     * `sector_kline` 与 `index_kline`：行业与宽基同期日K，用于对齐计算 5日/20日双基准超额收益 (RS)；
     * `sector_fund_flow`：所属板块近 5 日主力资金净流入连续性；
     * `longhubang`：标的最新龙虎榜席位明细与机构/游资结构；
     * `hard_gates`：硬门槛预检（是否 ST/*ST、上市是否 <60日、是否停牌、有效K线数）；
     * `inherited_context`：前序已生成的 L1 市场环境与 L2 板块状态（附时点与来源）。
   - 降级规则：行情硬门槛若判定失败，强制将 L4–L7 标记为 `N/A`，结构裁定“暂不评级”，不生成综合量化分。

2. **公司质量与重大风险补数**：
   - 定期报告、解禁流通公告（必须有流通日与占总股本比）、股权质押明细（质押占总股本比与占大股东比）、审计意见与商誉减值。

---

## 二、确定性计算函数配方

模型负责证据判档与逻辑推断，数值计算统一调用 `scripts/calculate.py` 纯函数库：

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **双基准相对强度 (RS)** | `python scripts/calculate.py calculate_relative_strength --json '{"stock_pct_5d": 8.5, "sector_pct_5d": 2.1, "index_pct_5d": -0.8, "stock_pct_20d": 18.2, "sector_pct_20d": 6.0, "index_pct_20d": 1.2}'` | 个股、行业、指数的 5日与20日涨跌幅 |
| **价格均线乖离与位置** | `python scripts/calculate.py calculate_price_position --json '{"price": 15.2, "ma20": 14.1, "ma50": 13.0, "atr14": 0.65, "structure_level": 14.3}'` | `price`, `ma20`, `ma50`, `atr14`, `structure_level` |
| **盈亏比与空间测算** | `python scripts/calculate.py calculate_risk_reward --json '{"entry": 15.2, "stop": 14.3, "targets": [17.0]}'` | `entry`, `stop`, `targets` |
| **行情硬门槛自动校验** | `python scripts/calculate.py validate_stock_hard_gate --json '{"bar_count": 250, "adjusted": true, "benchmark_complete": true, "industry_complete": true}'` | `bar_count`, `adjusted`, `benchmark_complete`, `industry_complete` |

---

## 三、交接落盘、不可变 Artifact 与 Thesis 管理

```bash
# 1. 个股交接摘要落盘（强制 subject 隔离，自动双写 stock_diagnostic 标准 Artifact）
cat << 'JSON' | python scripts/handoff_store.py write --stdin
{
  "report_type": "stock",
  "subject": {"type": "stock", "id": "600371", "name": "万向德农"},
  "as_of": "2026-09-11 15:00",
  "source_count": 12,
  "coverage": "92%",
  "scored_weight": "100%",
  "confidence": "高",
  "regime_namespace": "stock-structure",
  "market_regime": "吸筹观察",
  "structure_position": "吸筹观察",
  "primary_sectors": ["农业种植"],
  "watchlist": ["600371"],
  "risk_flags": ["硬门槛正常", "无违规质押"],
  "next_triggers": [{"id": "TRG-600371-01", "condition": "放量突破 16.20 确认SOS；跌破 14.30 证伪", "status": "pending"}]
}
JSON

# 2. 长期 Thesis 存取
python scripts/thesis_store.py get --stock-code 600371
python scripts/thesis_store.py write --stdin < thesis.json

# 3. 可选：个股诊断长图卡片渲染
python scripts/generate_report_card.py --type stock --json report.json
```
