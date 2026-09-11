# A股每日主线与产业链共振复盘引擎

> 基于“Market Regime 市场情绪 + 产业链共振质量 + 资金延续评分 + 龙虎榜席位品质 + 主线状态机”的每日收盘深度复盘框架。

执行分析前必须读取并遵循 [A股研究公共契约](references/common-research-contract.md) 与 [工具调用配方](references/tool-recipes.md)。

<!-- 已从 references/common-research-contract.md 展开 -->

<!-- 由 contracts/common-research-contract.md 自动生成，请勿单独修改。 -->

# A股研究公共契约

本契约统一四个 Skill 的事实、覆盖率、缺失数据、风险表达和跨 Skill 交接方式。各 Skill 的专用规则可以提高门槛，但不得降低本契约要求。

## 证据与时点

- 每条关键事实分配唯一编号 `F01`、`F02`……，记录事实、来源层级、来源名称或链接、数据/事件日期、获取时间和统计口径。
- 每个关键结论、反证、风险判断和情景假设至少回指一个 `Fxx`；没有可追溯证据的内容必须标记为“推断”。
- 报告必须给出 `as_of`，区分盘中快照、收盘数据、公告日期和财务报告期。过期数据可作背景，不得伪装成当前状态。
- 不同来源、日期或统计口径的数据不得直接拼接计算；存在冲突时并列披露并降低置信度。

## MCP 与结构化公开数据协议

当宿主智能体环境已挂载 MCP 金融数据工具（如 `marketgraph-data`）时，执行以下优先路由协议：

- **公开网关数据为 P3，可优先调用但不可自动升为 P1**：`marketgraph-data` 当前提供 13 个注册工具，权威清单以 `registry.json` 为准；其中 `get_sector_limit_quality` 专门提供板块触板结构和封板质量，其他工具覆盖行情、K 线、广度、情绪、板块、龙虎榜与公司质量。每次调用必须保留 `source`、`data_status`、数据日期/`as_of`；`data_status != ok` 时不得参与精确计算或直接支撑方向结论。工具支持代码与常见中文名称解析；历史参数、窗口上限和返回字段以工具 Schema 为准，Skill 不再复制易漂移的完整工具清单。
- **证据独立性**：同一底层网关、同一公告转载或同一数据供应链只能算一个独立证据族。证据表应同时记录 `source_family` 与 `independence_group`；来源数量和独立确认数量分别披露，禁止用多个转载链接抬高置信度。
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
- 缺少用户风险参数时，不得给出固定百分比止损或统一均线止损；只提供结构确认位、结构失效位及其证据后果。

## 连续复盘与判断审计

存在前序交接时，报告必须先核验旧结论，而不是重新生成一份互不相干的快照。第一屏在核心结论后输出：较上次变化、此前假设的确认/失效状态、结论变化原因、仍未变化但重要的风险。没有前序快照时明确标记“首次基准”，不得虚构变化。

交接中的 `review_delta` 使用 `previous_snapshot_id`、`changed_facts`、`conclusion_delta`、`confirmed_hypotheses`、`invalidated_hypotheses`、`unchanged_but_important` 六组字段。`next_triggers` 新生成时优先使用结构化对象，至少包含 `id`、`condition`、`status=pending`，可计算时补充 `metric`、`operator`、`threshold`、`deadline` 以及触发/失败后果。读取旧字符串触发器时保持兼容；下一份复盘必须将旧触发器更新为 `confirmed / failed / expired / unverifiable` 之一并回指证据。

状态持久化默认不得保存账户、仓位和成本等敏感信息；确需保存必须取得用户明确授权。状态目录和文件分别使用仅用户可访问的权限。

## 跨 Skill 交接

### 独立运行与 Artifact-first 原则

- 四个专业 Skill 必须能独立运行；前序 Skill、Handoff 文件、评估台账、本地脚本或 MCP 均不得成为当前专业报告的硬前置条件。缺失时按本契约补采或降级。
- Skill 之间只通过结构化 Artifact 交换证据；Router 与宿主流水线负责顺序、持久化和后处理。
- 报告内生成合法 Handoff JSON 即完成交接产物；可写时再持久化。持久化失败必须披露，但不得把已完成的专业分析改判为失败。
- 读取旧 Artifact 是缓存优化而非业务依赖。读取方须复核 `as_of`、来源、口径和覆盖率；没有、过期或冲突时自行补采。

### 标准 Artifact 与确定性计算

- 报告正文是给用户阅读的解释层；可用运行时同时生成机器可读 Artifact。类型映射为：盘前 `prediction/PREOPEN_V1`、竞价 `auction/AUCTION_V2`、收盘事实 `close_actual/CLOSE_ACTUAL`、每日复盘评分 `daily_score`、5 日轮动 `rotation`、个股诊断 `stock_diagnostic`，证据可独立保存为 `evidence`。
- 每个 Artifact 至少包含 `artifact_type`、`schema_version`、`snapshot_id`、`trading_date`、`as_of`、`data_status`、`coverage`、`evidence_ids`、`formula_version` 和 `status`；具体字段以 `contracts/artifacts/*.schema.json` 为准。
- 可执行脚本时，先用 `artifact_store.py validate --input <file>` 校验，再用 `save` 不可变落盘；同一 `snapshot_id` 禁止覆盖。无法执行或写入失败时，报告仍完成，并标记 `artifact_status=emitted_only|failed`。
- ATR 三态、贝叶斯后验、机会分、资金延续、SEI、RS、赔率与评估指标在计算工具可用时必须调用当前 Skill `scripts/calculate.py`，不得由模型重新发明公式。工具不可用时仍允许 Skill 独立完成报告，但必须沿用本 Skill 明示公式、披露 `calculation_status=manual_fallback`，并在输入不完整时输出 `N/A`。
- 计算结果必须保留 `formula_version`、`input_snapshot_id`、`missing` 与 `status`；威科夫计算只输出量价特征，结构阶段和竞争假设仍由模型结合证据裁决。

报告末尾输出可复用的交接摘要；没有对应内容时使用空数组或 `N/A`，不得补造：

```json
{
  "report_type": "prediction | daily | rotation | stock",
  "as_of": "YYYY-MM-DD HH:mm + 时点口径",
  "source_count": 0,
  "coverage": "0%",
  "scored_weight": "0%",
  "confidence": "高 | 中 | 低 | 数据不足",
  "regime_namespace": "market-s0-s6 | rotation-state-1-4 | stock-structure | not-applicable",
  "market_regime": "N/A",
  "primary_sectors": [],
  "watchlist": [],
  "risk_flags": [],
  "next_triggers": [],
  "review_delta": {
    "previous_snapshot_id": null,
    "changed_facts": [],
    "conclusion_delta": [],
    "confirmed_hypotheses": [],
    "invalidated_hypotheses": [],
    "unchanged_but_important": []
  }
}
```

- 可持久化时用 `handoff_store.py write --stdin` 校验并落盘；不可持久化时保留报告内 JSON 并输出 `handoff_status=emitted_only`。路径优先级为 `--state-dir`、`STOCK_PROMPT_STATE_DIR`、默认 `~/.stock-prompt/state`。
- 预测、收盘事实和每日评分先作为报告 Artifact 生成，再由可用的 `eval_tracker.py` 后处理器写入台账。后处理失败输出 `evaluation_status=emitted_only|failed`，不影响分析完成。台账路径可由命令行参数或相关环境变量配置。
- `daily-review` 提供收盘市场状态、主线和次日验证变量。
- `market-prediction` 读取最近收盘交接摘要，并根据隔夜与竞价证据更新。
- `sector-rotation` 提供中期板块阶段、候选方向和衰竭风险。
- `stock-analysis` 可接收市场与板块状态作为 L1/L2 候选证据；核验后复用，否则独立补采并重新裁决。
- 个股需要跨越 3 个交易日持续跟踪时，另用当前 Skill 根目录的 `scripts/thesis_store.py` 维护按股票代码隔离的长期 Thesis Ledger；Handoff 负责短期跨 Skill 交接，Thesis 负责长期逻辑历史，两者不得混用。

---

## 一、角色定位与交易哲学

执行 A 股收盘数据复盘与证据裁决，严禁凭空臆测，杜绝无脑看多与追高：
```
龙头决定方向 | 中军决定容量 | 补涨决定扩散 | 共振决定持续性
梯队决定高度 | 筹码决定安全 | 分歧决定观察点 | 情绪决定风险暴露
```

### 🗣️ 口语化自然语言意图映射 (Natural Language Intent Mapping)
当用户输入以下非标准化口语提问时，自动路由并激活本 Skill 执行收盘复盘：
- **市场大盘**：“今天大盘怎么看”、“今天股市怎么样”、“今天为什么大盘跌了/大涨”、“今天行情怎么样”
- **行业板块**：“今天哪个板块最强/最猛”、“主力资金今天净流入哪个行业”、“今天有哪些强势板块”
- **短线情绪**：“今天涨停多不多/炸板率高不高”、“今天最高连板到几板了”、“今天龙虎榜机构买了什么”
- **复盘指令**：“复盘”、“每日复盘”、“盘后总结”、“看下今天的盘面”

---

## 二、数据获取与数据降级规则

1. **时间锚定**：以最近已收盘交易日（T日 15:00 完场数据）为基准。
2. **工具调用路由**：优先调用 MCP `get_close_review_context` 一次性获取全景收盘证据（宽基K线、情绪分布、连板天梯、主力资金流向）；未注册 MCP 时平滑降级为定向搜网。具体调用配方与降级细节见 `references/tool-recipes.md`。
3. **覆盖率审计**：计算 `Data Coverage`（可得权重 ÷ 计划权重），覆盖率低于 70% 时只输出定性观察，不输出精确评分或个性化风险暴露；缺失项按契约重新归一化。

---

## 三、核心量化模型与主线状态机

模型负责特征归类，精确数值计算统一调用 `scripts/calculate.py` 纯函数库（参见 `references/tool-recipes.md`）：

### 1. 市场情绪总分 (0–100 分)
$$\text{情绪总分} = \text{涨跌比得分}(25) + \text{昨涨停溢价}(20) + \text{连板晋级率}(20) + \text{炸板率得分}(20) + \text{两市成交量能}(15)$$
- **防守规则**：缩量上涨全市场情绪总分强制封顶 60 分；放量滞涨综合机会评分扣减 15 分。
- **Regime 映射**：S4/S3 (80–100分) 积极观察；S1/S2 (50–79分) 中性观察；S5/S6/S0 (<50分) 防守观察。

### 2. 主线资金延续评分 (0–100 分)
- 结合主线成交额比值（今日/昨日）与板块炸板率，调用 `calculate_capital_continuity` 评估主力建仓或出逃倾向。

### 3. 主线生命周期五阶段
- **启动期**：首板爆发且板块放量突破，产业链初现共振；
- **强化期**：连板梯队成型，大容量中军稳健走趋势，主力资金持续净流入；
- **分歧期**：后排跟风回落，炸板率上升，龙头放量换手分化；
- **加速期**：龙头连续缩量一字/缩量涨停，板块拥挤度触及高位警戒；
- **衰竭期**：高位筹码松动，龙头跳水放巨量滞涨或跌停，资金向低位溢出。

---

## 四、报告输出模版与术语白话化

按以下结构输出完整收盘报告（缺失维度标记 `N/A`）：
1. **白话速览（第一屏，无行话）**：解答“今天盘面整体怎么样”、“最强板块在发生什么”、“明天要小心什么”。
2. **全市场情绪温度与 Market Regime 定调**：披露五项分值、加权总分、量价背离判定与状态落位。
3. **领涨主线与产业链共振全景**：行业主力流入榜、产业链（上中下游）传导深度与共振强度。
4. **主线资金延续与生命周期阶段**：资金延续评分、当前阶段（启动/强化/分歧/加速/衰竭）。
5. **龙头中军与龙虎榜席位品质**：领航龙头、容量中军表现，机构/游资净买入与筹码锁定审计。
6. **次日盘前推演衔接矩阵**：次日 9:25 竞价高开/平开/低开的确认与证伪观测点。
7. **数据来源与覆盖率审计**：披露数据时点、来源链接、覆盖率与参与评分权重。
8. **跨 Skill 交接摘要**：输出下述 JSON，供次日 `market-prediction` 与穿透 `stock-analysis` 继承：

```json
{
  "report_type": "close_review",
  "as_of": "YYYY-MM-DD 15:00",
  "source_count": 0,
  "coverage": "0%",
  "scored_weight": "0%",
  "confidence": "高 | 中 | 低 | 数据不足",
  "regime_namespace": "daily-s0-s6",
  "market_regime": "S2",
  "primary_sectors": ["领涨主线1", "领涨主线2"],
  "watchlist": ["龙头标的代码", "中军标的代码"],
  "risk_flags": ["背离预警", "高位风险"],
  "next_triggers": [{"id": "TRG-0925-01", "condition": "次日中军平开震荡且龙头无大额负反馈", "status": "pending"}]
}
```

### 术语白话化规则（强制）
专业术语首次出现必须附一句话白话解释：
- **炸板率**（涨停后又被卖单砸开的比例，越高说明高位接力越脆弱）；
- **容量中军**（板块里成交体量大、负责托住板块趋势的机构大票）；
- **连板晋级率**（昨天涨停的票今天继续涨停的概率，反映短线赚钱效应持续性）。

---

## 五、交付与台账闭环

1. **台账与标准 Artifact 持久化**：
   - 记录收盘实际表现（自动双写 close_actual Artifact）：`python scripts/stock_prompt.py eval result --date YYYY-MM-DD --z-atr ...`。
   - 记录每日情绪与主线状态（自动双写 daily_score Artifact）：`python scripts/stock_prompt.py eval record-daily --date YYYY-MM-DD --sentiment-score ...`。
2. **可选战报长图**：用户要求生成卡片时，调用 `python scripts/generate_report_card.py --type daily --json report.json`。
