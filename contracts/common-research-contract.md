# A股研究公共契约

本契约统一四个 Skill 的事实、覆盖率、缺失数据、风险表达和跨 Skill 交接方式。各 Skill 的专用规则可以提高门槛，但不得降低本契约要求。

## 证据与时点

- 每条关键事实分配唯一编号 `F01`、`F02`……，记录事实、来源层级、来源名称或链接、数据/事件日期、获取时间和统计口径。
- 每个关键结论、反证、风险判断和情景假设至少回指一个 `Fxx`；没有可追溯证据的内容必须标记为“推断”。
- 报告必须给出 `as_of`，区分盘中快照、收盘数据、公告日期和财务报告期。过期数据可作背景，不得伪装成当前状态。
- 不同来源、日期或统计口径的数据不得直接拼接计算；存在冲突时并列披露并降低置信度。

## MCP 与确定性数据源协议

当宿主智能体环境已挂载 MCP 金融数据工具（如 `marketgraph-data`）时，执行以下优先路由协议：

- **公开网关数据为 P3，可优先调用但不可自动升为 P1**：`marketgraph-data` 提供 `get_stock_quote`、`get_stock_kline`、`get_stock_timeline`、`get_market_sentiment`、`get_limit_up_ladder`、`get_sector_fund_flow`、`get_longhubang_detail` 与 `get_company_quality`。每次调用必须保留其 `source`、`data_status`、数据日期/`as_of`；`data_status != ok` 时不得参与计算或输出方向结论。工具支持代码与常见中文名称解析；`get_market_sentiment`、`get_limit_up_ladder` 与 `get_longhubang_detail` 支持历史 `date_str`（`YYYYMMDD` 或工具声明的格式）。
- **行情硬门槛仅验证序列完整性**：仅当 `get_stock_kline` 明确返回 `adjustment: qfq`、`data_status: ok` 且 `valid_bars >= 120` 时，才可通过“120 日复权 OHLCV”结构门槛；其来源仍按 P3 记录，涉及交易所公告、审计意见、监管和公司事件的关键事实仍须 P2/P1 原始来源核验。
- **无感优雅回退**：若未检测到 MCP 工具，自动平滑回退至网络检索（P4）与公告核验（P2），并严格执行常规数据缺省审计。

## 覆盖率与缺失数据

统一公式：

```text
Data Coverage = 已验证证据权重 / 计划证据总权重
Scored Weight = 实际参与评分的原始权重
```

各 Skill 必须明确自己的计划证据组和权重。不得只按“找到几个字段”计算覆盖率，也不得把 N/A 作为 0 分或中性分。

- `>=85%`：允许完整评分；高置信仍需证据一致。
- `70%–84%`：允许条件化评分，置信度最高为“中”。
- `50%–69%`：只输出条件判断，不输出精确概率、综合分或个性化风险暴露。
- `<50%`：输出数据审计、已知事实和待补清单，核心结论暂不评级。

核心模块即使缺失也应保留并标记 `N/A`，同时说明缺失对结论的影响；仅可省略纯展示性模块。

## 风险表达

- 默认输出风险暴露等级：`积极观察 / 中性观察 / 防守观察 / 暂不评级`，不直接给账户仓位比例。
- 只有用户提供当前仓位、成本、分析周期、最大可承受回撤和风险预算后，才允许给出条件化仓位情景。
- 评分、概率和历史命中率都不代表收益承诺；不得输出确定性买卖指令。

## 跨 Skill 交接

报告末尾输出可复用的交接摘要；没有对应内容时使用空数组或 `N/A`，不得补造：

```json
{
  "report_type": "prediction | daily | rotation | stock",
  "as_of": "YYYY-MM-DD HH:mm + 时点口径",
  "source_count": 0,
  "coverage": "0%",
  "scored_weight": "0%",
  "confidence": "高 | 中 | 低 | 数据不足",
  "market_regime": "N/A",
  "primary_sectors": [],
  "watchlist": [],
  "risk_flags": [],
  "next_triggers": []
}
```

- 交接摘要除在报告末尾输出外，必须同时落盘到固定位置 `~/.stock-prompt/state/handoff-<YYYYMMDD>-<report_type>.json`（如 `handoff-20260904-daily.json`），保证跨会话可继承。读取方（`market-prediction` / `stock-analysis`）优先检查最近 3 个交易日内最新的落盘交接文件，其次回退到当前会话上下文。
- `market-prediction` 的预测台账统一写入 `~/.stock-prompt/eval/predictions.jsonl`（由 `scripts/eval_tracker.py` 固定，不随工作目录漂移）；`daily-review` 收盘回测读取同一份文件，禁止在其他位置另建台账。
- `daily-review` 提供收盘市场状态、主线和次日验证变量。
- `market-prediction` 读取最近收盘交接摘要，并根据隔夜与竞价证据更新。
- `sector-rotation` 提供中期板块阶段、候选方向和衰竭风险。
- `stock-analysis` 接收市场与板块状态作为 L1/L2 证据，并返回个股确认、失效和复核条件。
