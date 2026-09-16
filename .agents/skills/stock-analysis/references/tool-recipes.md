# stock-analysis 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与个股诊断采集配方

1. **优先调用 MCP `get_stock_diagnostic_context`**：
   - 入参：`{"symbol": "600371", "sector": "农业种植", "benchmark": "SHCI", "archetype_hints": {"sector_role": "核心龙头", "limit_up_streak": 2}, "position_context": {"position_state": "watching", "holding_horizon": "short_swing", "risk_tolerance": "medium"}}`
   - 返回标准结构：
     * `stock_kline`：前复权日K OHLCV、均线簇 (MA5/20/50/120/250)、ATR14、Bias、20日量比、120日量能分位与3年价格分位；
     * `sector_kline` 与 `index_kline`：行业与宽基同期日K，用于对齐计算 5日/20日双基准超额收益 (RS)；
     * `sector_fund_flow`：所属板块近 5 日主力资金净流入连续性；
     * `longhubang`：标的最新龙虎榜席位明细与机构/游资结构；
     * `data_mode`：`full / reduced / event` 能力边界；
     * `archetype` 与 `selected_model`：生态主类型、竞争类型和模型模块；
     * `wyckoff_applicability`：`applicable / partial / not_applicable`；
     * `position_context`：空仓观察、被套风险削减、盈利保护或通用情景；
     * `seat_evidence` 与 `chip_structure`：可核验席位分类和筹码数据缺失状态；
     * `inherited_context`：前序已生成的 L1 市场环境与 L2 板块状态（附时点与来源）。
   - 降级规则：`reduced/event` 不生成综合量化分，但继续输出可验证事实、风险、条件情景和下一补数项。

2. **公司质量与重大风险补数**：
   - 定期报告、解禁流通公告（必须有流通日与占总股本比）、股权质押明细（质押占总股本比与占大股东比）、审计意见与商誉减值。

---

## 二、确定性计算函数配方

模型负责证据判档与逻辑推断，数值计算统一调用 `scripts/calculate.py` 纯函数库：

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **数据模式** | `python scripts/calculate.py resolve_stock_data_mode --json '{"bar_count": 80, "adjusted": true, "benchmark_complete": true, "industry_complete": false, "quote_available": true, "timeline_available": true, "turnover_available": true}'` | K线根数、复权、双基准、事件与实时数据状态 |
| **生态分型** | `python scripts/calculate.py classify_stock_archetype --json '{"limit_up_streak": 3, "sector_role": "核心龙头", "turnover_rate": 22}'` | 只传可核验的情绪、机构、红利或事件证据 |
| **模型选择** | `python scripts/calculate.py select_stock_model --json '{"archetype": "sentiment_leader", "data_mode": "full"}'` | `archetype`, `data_mode` |
| **威科夫适用性** | `python scripts/calculate.py assess_wyckoff_applicability --json '{"data_mode": "event", "event_driven": true}'` | 数据模式、区间天数、连板/一字板和事件状态 |
| **持仓状态** | `python scripts/calculate.py validate_position_context --json '{"position_state": "holding_loss", "cost_price": 18.2, "position_ratio": 30, "holding_horizon": "short_swing", "risk_tolerance": "medium"}'` | 状态、成本、仓位、周期与风险承受力 |
| **席位证据** | `python scripts/calculate.py summarize_seat_evidence --json '{"entries": [{"seat_name": "机构专用", "net_buy": 20000000}]}'` | 龙虎榜公开席位名称与净额；未分类席位不得猜身份 |
| **筹码结构** | `python scripts/calculate.py calculate_chip_structure --json '{"profit_ratio": 72.5, "data_source": "可追溯数据源", "as_of": "2026-09-16"}'` | 指标、数据源、时点与口径 |
| **双基准相对强度 (RS)** | `python scripts/calculate.py calculate_relative_strength --json '{"stock_pct_5d": 8.5, "sector_pct_5d": 2.1, "index_pct_5d": -0.8, "stock_pct_20d": 18.2, "sector_pct_20d": 6.0, "index_pct_20d": 1.2}'` | 个股、行业、指数的 5日与20日涨跌幅 |
| **价格均线乖离与位置** | `python scripts/calculate.py calculate_price_position --json '{"price": 15.2, "ma20": 14.1, "ma50": 13.0, "atr14": 0.65, "structure_level": 14.3}'` | `price`, `ma20`, `ma50`, `atr14`, `structure_level` |
| **盈亏比与空间测算** | `python scripts/calculate.py calculate_risk_reward --json '{"entry": 15.2, "stop": 14.3, "targets": [17.0]}'` | `entry`, `stop`, `targets` |
| **旧硬门槛兼容入口** | `python scripts/calculate.py validate_stock_hard_gate --json '{"bar_count": 250, "adjusted": true, "benchmark_complete": true, "industry_complete": true}'` | 仅用于兼容；新流程使用 `resolve_stock_data_mode` |

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
  "archetype": "sentiment_leader",
  "model_selected": "sentiment-v1",
  "data_mode": "full",
  "position_context": {"position_state": "watching", "holding_horizon": "short_swing", "risk_tolerance": "medium"},
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
