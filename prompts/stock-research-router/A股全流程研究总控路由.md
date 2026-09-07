# A股全流程研究总控路由

本 Skill 只负责判断研究阶段、复用已验证上下文并交接给专业 Skill，不自行替代专业分析，也不假设宿主一定支持程序化调用其他 Skill。

执行前读取并遵循 [A股研究公共契约](references/common-research-contract.md)。

<!-- 已从 references/common-research-contract.md 展开 -->

<!-- 由 contracts/common-research-contract.md 自动生成，请勿单独修改。 -->

# A股研究公共契约

本契约统一四个 Skill 的事实、覆盖率、缺失数据、风险表达和跨 Skill 交接方式。各 Skill 的专用规则可以提高门槛，但不得降低本契约要求。

## 证据与时点

- 每条关键事实分配唯一编号 `F01`、`F02`……，记录事实、来源层级、来源名称或链接、数据/事件日期、获取时间和统计口径。
- 每个关键结论、反证、风险判断和情景假设至少回指一个 `Fxx`；没有可追溯证据的内容必须标记为“推断”。
- 报告必须给出 `as_of`，区分盘中快照、收盘数据、公告日期和财务报告期。过期数据可作背景，不得伪装成当前状态。
- 不同来源、日期或统计口径的数据不得直接拼接计算；存在冲突时并列披露并降低置信度。

## MCP 与确定性数据源协议

当宿主智能体环境已挂载 MCP 金融数据工具（如 `marketgraph-data`）时，执行以下优先路由协议：

- **公开网关数据为 P3，可优先调用但不可自动升为 P1**：`marketgraph-data` 提供 `get_stock_quote`、`get_stock_kline`、`get_stock_timeline`、`get_index_kline`、`get_market_breadth`、`get_market_sentiment`、`get_limit_up_ladder`、`get_sector_fund_flow`、`get_sector_kline`、`get_basket_index`、`get_longhubang_detail` 与 `get_company_quality` 共 12 个工具。每次调用必须保留其 `source`、`data_status`、数据日期/`as_of`；`data_status != ok` 时不得参与计算或输出方向结论。工具支持代码与常见中文名称解析；`get_market_sentiment`、`get_limit_up_ladder` 与 `get_longhubang_detail` 支持历史 `date_str`（`YYYYMMDD` 或工具声明的格式）；`get_sector_fund_flow` 传 `days`（2-10）可回补板块主力资金 N 日历史；`get_index_kline` 提供核心指数 N 日逐日涨跌幅；`get_market_breadth` 最新交易日为精确涨跌家数与红盘率、历史交易日为情绪池替代口径（以 `breadth_precision` 区分，历史红盘率不得估算）。
- **行情硬门槛仅验证序列完整性**：仅当 `get_stock_kline` 明确返回 `adjustment: qfq`、`data_status: ok` 且 `valid_bars >= 120` 时，才可通过“120 日复权 OHLCV”结构门槛；其来源仍按 P3 记录，涉及交易所公告、审计意见、监管和公司事件的关键事实仍须 P2/P1 原始来源核验。
- **构造代理序列边界**：东财板块指数等网关不可用时，代理序列只能来自 `get_basket_index` 等权构造（须显式传入成分股、披露成分覆盖度与失败清单，`series_type=equal_weight_constructed`），不得由模型临时挑选成分股自行拼凑。代理序列属"构造数据"（非 P1–P3 网关原始输出）：只能用于方向性强弱对照（如板块相对强度、主线篮子走势），不得用于精确评分阈值、赔率计算或情绪得分，报告中必须标注"代理序列"并注明成分覆盖度（如"4/6 只成分股"）；等权口径与板块官方市值加权指数存在系统性差异，覆盖度不足（少于半数成分）时宁可保留 N/A。
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

- 交接摘要除在报告末尾输出外，必须通过 `python scripts/handoff_store.py write --stdin` 完成 Schema 校验与原子落盘；读取方优先执行 `python scripts/handoff_store.py latest --within-trading-days 3`，读取最近有效文件并检查返回的日历精度警告，不可执行脚本时才回退当前会话上下文。固定位置仍为 `~/.stock-prompt/state/handoff-<YYYYMMDD>-<report_type>.json`；缺失字段不得补造。
- `market-prediction` 的预测台账统一写入 `~/.stock-prompt/eval/predictions.jsonl`（由 `scripts/eval_tracker.py` 固定，不随工作目录漂移）；`daily-review` 收盘回测读取同一份文件，禁止在其他位置另建台账。
- `daily-review` 提供收盘市场状态、主线和次日验证变量。
- `market-prediction` 读取最近收盘交接摘要，并根据隔夜与竞价证据更新。
- `sector-rotation` 提供中期板块阶段、候选方向和衰竭风险。
- `stock-analysis` 接收市场与板块状态作为 L1/L2 证据，并返回个股确认、失效和复核条件。

## 路由边界

- 明确提到盘前、8:30–9:15 或 9:25 竞价：选择 `market-prediction`。
- 明确提到今日收盘、盘后或每日复盘：选择 `daily-review`。
- 明确提到近5日、周末复盘、板块轮动：选择 `sector-rotation`。
- 明确给出股票代码、名称或要求诊断个股：选择 `stock-analysis`。
- 只有请求横跨两个以上阶段、要求继续前序研究，或意图无法由单一专业 Skill 完成时，才使用本 Router。

用户明确指定的任务优先于时间规则。不要仅因当前时间位于某个窗口，就覆盖用户清晰表达的意图。

## 编排流程

1. 提取用户要求的研究对象、时间范围、所处阶段和最终交付。
2. 使用 `python scripts/handoff_store.py latest --within-trading-days 3` 查找最近有效交接；不可执行脚本时检查当前会话已有摘要。
3. 输出简短路由决策：目标 Skill、可继承证据、仍需补采的数据。不得把旧摘要伪装为当前事实。
4. 若宿主支持 Skill 调度，交由目标专业 Skill 执行；不支持时，明确提示用户调用对应 Skill，不在 Router 内复制整套专业框架。
5. 专业报告完成后，用 `handoff_store.py write --stdin` 校验并落盘交接摘要；写入失败必须披露，不能声称闭环完成。
6. daily-review 或 sector-rotation 输出标的池后，提供 `诊断 <代码或名称>` 的个股穿透入口；个股诊断只继承有来源的 L1/L2，继续补采 L3–L8。

## 多阶段任务顺序

- 盘前到收盘：先 `market-prediction`，收盘后由 `daily-review` 读取同日预测摘要并记录实际结果。
- 收盘到个股：先 `daily-review` 或 `sector-rotation`，再将有证据的市场与板块状态交给 `stock-analysis`。
- 周末全流程：先 `sector-rotation` 确定中期板块状态；若用户指定标的，再执行 `stock-analysis`。

每个阶段保持自己的适用边界：不得在盘前生成尚不存在的收盘数据，不得在收盘复盘中伪造盘前预测，也不得因交接存在而跳过数据新鲜度检查。

## 输出格式

```text
路由决策：<目标 Skill 或执行顺序>
继承上下文：<交接文件、日期、来源；没有则 N/A>
需补数据：<列表>
执行状态：<已交由宿主调度 / 请用户调用对应 Skill / 已完成>
下一入口：<可选的后续 Skill 或“诊断 代码”>
```

Router 不输出市场评分、涨跌概率、威科夫阶段或买卖建议；这些内容只能由相应专业 Skill 基于完整证据生成。
