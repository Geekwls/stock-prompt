# A股盘前实战全景研判与情景作战推演引擎

> 基于“市场Regime先验 ➡️ 去重证据簇启发式贝叶斯更新 ➡️ 隔夜利好透支审计 ➡️ ATR空间盈亏比 ➡️ 趋势与情绪双轨机会 ➡️ 三套If-Then作战剧本 ➡️ 9:25竞价300秒极速红绿灯 ➡️ 评估闭环”的实盘作战系统。

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

- **公开网关数据为 P3，可优先调用但不可自动升为 P1**：`marketgraph-data` 当前提供 21 个注册工具，权威清单以 `registry.json` 为准；其中既有行情、K 线、广度、情绪、板块、龙虎榜与公司质量工具，也有上下文聚合和 Artifact 闭环工具。每次调用必须保留 `source`、`data_status`、数据日期/`as_of`；`data_status != ok` 时不得参与精确计算或直接支撑方向结论。工具支持代码与常见中文名称解析；历史参数、窗口上限和返回字段以工具 Schema 为准，Skill 不再复制易漂移的完整工具清单。
- **证据独立性**：同一底层网关、同一公告转载或同一数据供应链只能算一个独立证据族。证据表应同时记录 `source_family` 与 `independence_group`；来源数量和独立确认数量分别披露，禁止用多个转载链接抬高置信度。
- **个股数据模式替代一刀切硬门槛**：`get_stock_kline` 返回前复权序列后，stock-analysis 必须通过 `resolve_stock_data_mode` 选择 `full / reduced / event`。`valid_bars >= 120` 且双基准齐全才允许 full 模式模型内评分；20–119 根进入 reduced；次新、复牌或重大事件进入 event。后两者仍可输出事实、风险与条件情景，但禁止长期 RS、完整威科夫确认和综合分。来源仍按 P3 记录，公告、审计、监管和公司事件须 P2/P1 核验。
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
- 个股诊断必须区分 `watching / holding_profit / holding_loss / unknown`。缺少成本、仓位、周期和风险参数时，不得给出固定百分比止损、统一均线止损或个性化仓位动作；只提供结构确认位、结构失效位及其证据后果。

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
- 计算结果必须保留 `formula_version`、`input_snapshot_id`、`missing` 与 `status`；盘前机会函数（Opportunity）若 `missing` 包含 `direction`，说明核心方向概率缺失或非法，其数值仅为残缺偏置分（`status=partial`），严禁直接作为正式机会评分引用；主线衰竭指数（SEI）支持客观推导模式（`derivation=objective`），基于缩量天数、背离比率、断板率、炸板率、成交占比与低位扩散比率自动推导；涉及比例类参数（`divergence_ratio`、`relay_failed_ratio`、`break_rate`、`sector_turnover_share`、`low_position_spillover`），统一推荐传入 `0–1` 标准小数（如 1% 传 `0.01`）或显式百分比字符串（如 `'1%'`、`'12%'`），严禁对 1% 传入裸数值 `1` 或 `1.0`（系统强制抛出 ValueError 拦截 100 倍歧义）；连板梯队必须经过 `calculate_ladder_health` 审计，最高板 $\ge 4$ 且断层 $\ge 2$ 时强制输出 `isolated_leader_risk` 孤桩龙头风险；存量博弈下领涨主线成交额占比 $\ge 8\%$ 且流出板块平均跌幅 $> 1.5\%$ 时由 `calculate_sector_cannibalization` 触发 `siphon_extreme` 存量吸血极化预警；盘中快照模式（09:30–15:00）须遵循 10:00 分水岭规则，早盘 10:00 前板块脉冲标为 `early_morning_impulse`，需经分时均线站稳方确认为日内强势；威科夫计算只输出量价特征，结构阶段和竞争假设仍由模型结合证据裁决。

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
  "next_triggers": [
    {
      "id": "TRG-01",
      "trigger_type": "竞价强弱 | 分时均线 | 中军承接",
      "condition": "主触发条件描述",
      "status": "pending",
      "condition_above": "超预期条件",
      "action_above": "超预期执行预案",
      "condition_as_expected": "符合预期条件",
      "action_as_expected": "符合预期执行预案",
      "condition_below": "低于预期条件",
      "action_below": "低于预期执行预案",
      "invalidation_condition": "失效条件"
    }
  ],
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

兼容读取历史交接时，将 `report_type=close_review` 归一化为 `daily`，并将 `regime_namespace=daily-s0-s6|preopen-s0-s6` 归一化为 `market-s0-s6`；新写入和新报告只使用标准值。

- 可持久化时用 `handoff_store.py write --stdin` 校验并落盘；不可持久化时保留报告内 JSON 并输出 `handoff_status=emitted_only`。存储路径优先级为命令行参数 > 模块专属环境变量（`STOCK_PROMPT_STATE_DIR` / `STOCK_PROMPT_ARTIFACT_DIR` 等） > 统一根目录 `STOCK_PROMPT_HOME` > 默认 `~/.stock-prompt/`。
- 预测、收盘事实和每日评分先作为报告 Artifact 生成，再由可用的 `eval_tracker.py` 后处理器写入台账。后处理失败输出 `evaluation_status=emitted_only|failed`，不影响分析完成。台账路径可由命令行参数或相关环境变量配置。
- `daily-review` 提供收盘市场状态、主线和次日验证变量。
- `market-prediction` 读取最近收盘交接摘要，并根据隔夜与竞价证据更新。
- `sector-rotation` 提供中期板块阶段、候选方向和衰竭风险。
- `stock-analysis` 可接收市场与板块状态作为 L1/L2 候选证据；核验后复用，否则独立补采并重新裁决。
- 个股需要跨越 3 个交易日持续跟踪时，另用当前 Skill 根目录的 `scripts/thesis_store.py` 维护按股票代码隔离的长期 Thesis Ledger；Handoff 负责短期跨 Skill 交接，Thesis 负责长期逻辑历史，两者不得混用。

## Agent 输出协议（首屏与可追问展示）

五个 Skill 的报告首屏必须先输出统一摘要卡，再展开专业详情。摘要卡字段固定为：

```text
结论：<一句话，不得超过两句>
逻辑状态：<强化/稳定/弱化/证伪/不适用>
当前位置：<阶段或位置；不适用时写 N/A>
置信度：<高/中/低/数据不足>
数据覆盖率：<精确百分比或 N/A>
数据状态：<完整数据/部分数据/数据不足>
最大风险：<一至三项>
下一步观察：<一至三项可验证变量>
```

同时输出机器可读的 `summary_card`，字段至少包含 `summary`、`logic_health`、`structure_position`、`confidence`、`coverage`、`data_status`、`risk_flags`、`next_actions`。`next_actions` 只能使用当前能力支持的操作，例如 `view_evidence`、`retry_data`、`render_report`、`view_calibration` 或跳转其他专业 Skill。

展示规则：首屏只显示摘要卡和各证据层的一句话状态；用户追问或调用 `view_evidence` 后，再展开事实、推断、反证、来源、数据时间和覆盖率。`coverage < 70%` 时 `data_status` 必须为“部分数据”或“数据不足”，只做条件化判断，不得输出精确综合评分。

## 版本提醒（非阻断）

当前 Skill 根目录存在 `scripts/update_manager.py` 时，可在每次研究开始前执行 `python scripts/update_manager.py reminder --quiet`。脚本自行保证默认 24 小时内最多联网检查一次；无新版本或缓存仍有效时不输出。发现新版本时仅在报告末尾提示版本号与更新命令，不得中断研究，也不得未经用户明确确认执行 `apply --yes`。检查失败保持静默，不降低研究结论状态。

---

## 一、核心哲学与实战作战体系

系统彻底解耦为四大实战层级，将“宏观研报”全面升级为“交易员按键作战指南”：
1. **Layer 1 宏观状态与三态概率 (Market Forecast)**：研判今日指数方向与胜率分布（$P_{\text{Up}}, P_{\text{Side}}, P_{\text{Down}}$），界定日内震荡箱体（Pivot, R1/R2, S1/S2）。
2. **Layer 2 交易机会函数双轨制 (Dual-Track Opportunity)**：
   - **趋势机会分 (Trend Opportunity)**：大盘指数共振、宽基 ETF、蓝筹容量中军机会（调用 `calculate_opportunity_score`）；
   - **情绪机会分 (Sentiment Opportunity)**：超短连板、题材龙头、弱市抱团妖股与冰点破局机会（调用 `calculate_sentiment_opportunity_score`），弱势市不一刀切误杀妖股。
3. **Layer 3 三套 If-Then 实战情景作战剧本 (Three Tactical Scenarios)**：
   - **【剧本 A：超预期强攻 (Bullish Breakout)】**：龙头竞价抢筹顶板，大盘平开/高开，战法聚焦打板先锋与回踩均线承接中军，防盲目追后排杂毛；
   - **【剧本 B：平开分歧震荡 (Rotational/Range-bound)】**：指数在 Pivot 附近整理，各半涨跌，战法聚焦 S1 支撑位逢低试仓，严禁半路追脉冲；
   - **【剧本 C：核按钮退潮防守 (Panic/Retreat)】**：高标竞价跌停或龙头跳空重挫，战法聚焦开仓归零、反抽止损、清仓防守。
4. **Layer 4 9:25–9:30 竞价 300 秒极速响应路径 (Auction Fast-Path)**：
   - 盘前（8:30–9:15）备好条件清单；9:25 集合竞价撮合出炉后，**严禁重新生成长篇研报**，必须在 30 秒内仅输出不超过 5 行的“极速红绿灯决策卡”，3 秒扫视即去券商下单；数据校验与台账写入在后台静默执行。

### 🗣️ 口语化自然语言意图映射 (Natural Language Intent Mapping)
当用户输入以下口语提问时，自动路由并激活本 Skill：
- **盘前方向**：“明天大盘怎么走”、“明天大盘会跌吗/会涨吗”、“早盘看多还是看空”、“明天能不能买/要不要减仓”
- **竞价窗口**：“9:25 竞价怎么看”、“今天开盘强不强”、“竞价超预期了吗”、“今天早盘开盘策略”、“9:25 开盘红绿灯”
- **推演指令**：“盘前预测”、“今日推演”、“早盘研判”、“大盘概率推演”、“盘前作战计划”

---

## 二、证据采集与博弈反身性审计

采集截至 8:30 的客观数据，归入 **4 大独立证据簇**（权重为 $E_1$ 25%, $E_2$ 25%, $E_3$ 20%, $E_4$ 30%）：
- **$E_1$ 全球与亚太科技偏好**：纳指、费城半导体 (SOX)、中概金龙、日韩芯片股。
- **$E_2$ 宏观流动性与外汇计价**：富时中国 A50 期指、离岸人民币 (USDCNH)、央行早盘公开市场逆回购。
- **$E_3$ 国内产业政策与突发催化**：部委产业规划、重大政策催化与行业突破。
- **$E_4$ A股内生量价与连板结构**：宽基指数偏离、涨跌比、炸板率、连板梯队（调用 MCP `get_preopen_context`）。

### ⚠️ A 股反身性利好透支审计 (Catalyst Exhaustion Audit)
A 股短线存在极强的“预期兑现 (Priced-in)”与“利好出尽高开低走”反身性。针对隔夜发酵的重磅利好，必须调用 `assess_catalyst_exhaustion` 纯函数进行审计：
- **高透支风险 (exhaustion_risk=high)**：板块前期连续上涨 $\ge 3$ 天或昨日大阳，隔夜利好全网刷屏，次日大幅跳空高开 $\ge 2.0\%$。此时判定为“潜伏盘兑现砸盘陷阱”，下调看涨概率似然比，严禁开盘追高，强制提示防冲高回落大阴线；
- **低透支风险 (exhaustion_risk=low)**：利好属于底部首发突发催化，潜伏盘极少，支持竞价达标后积极跟进。

---

## 三、概率推演、空间点位与纯计算配方

### 1. 7 大 Market Regime 条件先验
| 市场 Regime 状态 | 核心特征定义 | 先验 $P(\text{Up})$ | 先验 $P(\text{Side})$ | 先验 $P(\text{Down})$ |
|:---|:---|:---:|:---:|:---:|
| **S0 恐慌释放** | 连续大幅缩量暴跌 / 跌停家数激增 | 15% | 25% | **60%** |
| **S1 超跌修复** | 情绪冰点后首次首板涌现 / 底部放量阳线 | **40%** | **40%** | 20% |
| **S2 存量震荡** | 成交平量 / 涨跌比接近 1:1 / 板块快速轮动 | 30% | **50%** | 20% |
| **S3 趋势启动** | 指数放量突破 20 日线 / 主线梯队完整共振 | **55%** | 30% | 15% |
| **S4 趋势延续** | 指数依托 5 日线放量主升 / 赚钱效应扩散 | **60%** | 30% | 10% |
| **S5 高位分配** | 放量滞涨 / 龙头连续高位巨量震荡 / 炸板率高 | 25% | **45%** | 30% |
| **S6 退潮出逃** | 主线龙头跌停断板 / 连板大幅负反馈 | 10% | 25% | **65%** |

### 2. 纯计算函数配方 (统一通过 scripts/calculate.py 调用)
- **贝叶斯后验概率**：模型输入似然比，调用 `calculate_bayesian_posterior` 计算归一化后验概率。
- **空间点位引擎**：调用 `calculate_price_range` 输出 R2/R1/Pivot/S1/S2。
- **趋势机会分**：调用 `calculate_opportunity_score`（0–100 分）。
- **情绪机会分**：调用 `calculate_sentiment_opportunity_score`（0–100 分），输入连板健康度、龙头溢价率与情绪周期。
- **利好透支审计**：调用 `assess_catalyst_exhaustion` 评估冲高回落诱多风险。
- **9:25 竞价极速红绿灯**：调用 `calculate_auction_traffic_light`，秒级生成信号灯与剧本匹配结果。

---

## 四、报告输出模版与实战作战卡

### 模式 A：盘前全景作战报告 (08:30–09:15)

按以下结构输出完整报告（缺失维度标注 `N/A`）：

1. **首屏摘要卡（必须置顶）**：
   严格遵循公共 Agent 输出协议：结论、逻辑状态（Regime）、当前位置（指数点位）、置信度、覆盖率、数据状态、最大风险和下一步观察；同时附带 `next_actions`（竞价更新、查看证据、生成报告）。
2. **第一优先级：现有持仓处置作战卡 (Portfolio Defense)**：
   针对用户现有持仓（或前日关注标的），明确盘前防守红线：
   | 标的简称/代码 | 当前盈亏状态 | 开盘冲高止盈线 | 均线强弱防守线 | 破位硬止损线 (9:35前执行) |
   |:---|:---:|:---:|:---:|:---:|
   | 标的 A | 浮盈中 | 突破前高逢高止盈 | 5日均线不破持有 | 跌破开盘价-2%清仓 |
3. **第二优先级：昨日复盘预案与自选池竞价对账 (Yesterday Plan Reconciliation)**：
   强制读取昨日 `daily-review` 或 `sector-rotation` 交接的 `next_triggers` 与自选池，在 9:25 窗口进行基准对账核销，杜绝孤立推演开盲盒：
   | 昨日重点标的 | 昨日预定触发条件 | 今早竞价状态 (9:25后核销) | 状态裁决 | 对应行动 |
   |:---|:---|:---:|:---:|:---|
   | 候选龙头 A | 竞价高开>2.5%且量比>1.5 | 竞价高开+3.8% 量比2.1 | [已达标] | 执行【剧本 A】开盘先锋打板 |
   | 趋势中军 B | 5日均线上方承接 | 低开-2.5% 跌破5日线 | [破位失效] | 放弃开仓，移出自选 |
4. **第三优先级：三套 If-Then 情景作战剧本 (Three Tactical Scenarios)**：
   - **【剧本 A：超预期强攻】**
     - *触发条件*：核心龙头竞价封单/抢筹大幅超预期（GAP>3% 且金额比>1.2），大盘平开/高开无拖累；
     - *执行战法*：打板第一身位先锋，或中军回踩均线低吸；
     - *实操禁忌*：严禁追高无承接的后排杂毛，谨防高开低走大阴线。
   - **【剧本 B：平开分歧震荡】**
     - *触发条件*：大盘在 Pivot 附近平开，两市无极端恶性核按钮，情绪中性；
     - *执行战法*：在 S1 支撑位低吸核心主线品种，等待 9:45 分水岭承接确认；
     - *实操禁忌*：严禁半路追逐脉冲题材。
   - **【剧本 C：核按钮退潮防守】**
     - *触发条件*：昨日高位连板出现 2 只以上跌停核按钮，或第一龙头竞价跳空重挫；
     - *执行战法*：全天停止任何新开仓，持仓开盘冲高立即减仓/止损；
     - *实操禁忌*：严禁盲目接飞刀、加仓摊平或水下抄底。
5. **9:25 集合竞价验证清单 (Auction Checklist)**：
   列出开盘 9:25 核心标的的客观验证数值门槛：
   | 观测标的 | 角色 | 超预期高开门槛 | 竞价量比阈值 | 恶性破位门槛 | 匹配剧本 |
   |:---|:---:|:---:|:---:|:---:|:---:|
   | 龙头 A | 第一主线先锋 | $\ge +3.5\%$ | $\ge 1.5$ | $\le -2.0\%$ | 剧本 A / 剧本 C |
6. **宏观概率分布、空间点位与双轨机会打分**：
   - 三态概率：$P_{	ext{Up}}, P_{	ext{Side}}, P_{	ext{Down}}$；
   - 指数空间：R2 / R1 / Pivot / S1 / S2 及上下盈亏比；
   - 双轨机会：趋势机会分（宽基/机构）与情绪机会分（短线/连板）；
   - 利好透支度：exhaustion_risk 风险等级与冲高回落预警。
7. **主线板块状态机与资金延续研判**：主线生命周期阶段（启动/分歧/强化/加速/衰竭）。
8. **研判基准与覆盖率审计**：披露数据时点、来源链接、覆盖率与参与评分权重。
9. **跨 Skill 交接摘要 (Handoff JSON)**：文末输出下述 JSON，供盘后复盘与个股诊断继承：

```json
{
  "report_type": "prediction",
  "as_of": "YYYY-MM-DD 08:30",
  "source_count": 0,
  "coverage": "0%",
  "scored_weight": "0%",
  "confidence": "高 | 中 | 低 | 数据不足",
  "regime_namespace": "market-s0-s6",
  "market_regime": "S2",
  "primary_sectors": ["候选主线1", "候选主线2"],
  "watchlist": ["先锋龙头代码", "容量中军代码"],
  "risk_flags": ["风险预警"],
  "next_triggers": [
    {
      "id": "TRG-0925-01",
      "trigger_type": "竞价强弱",
      "condition": "核心龙头竞价高开>3%且金额比>1.2",
      "status": "pending",
      "condition_above": "龙头竞价>5%且量比>2.0",
      "action_above": "触发【剧本A超预期强攻】，开盘直接打板第一身位先锋",
      "condition_as_expected": "龙头平开到+2%之间",
      "action_as_expected": "触发【剧本B平开震荡】，等待9:45均线承接在S1低吸",
      "condition_below": "龙头大幅低开<-3%或跌停核按钮",
      "action_below": "触发【剧本C退潮防守】，全天放弃开仓，已有持仓逢高止损",
      "invalidation_condition": "开盘5分钟指数跌破S2或出现2只以上核按钮"
    }
  ]
}
```

---

### 模式 B：9:25–9:30 集合竞价 300 秒极速决策卡 (Auction Fast-Path)

> 🚨 **实战铁律**：9:25–9:30 窗口禁止输出长篇研报与多屏长文，模型必须在 20 秒内输出以下 **极简 5 行红绿灯决策卡**，供交易员 3 秒内扫视完毕并执行挂单：

```text
🚦【竞价红绿灯】[🟢 积极进攻 (绿灯) / 🟡 谨慎分歧 (黄灯) / 🔴 全面防守 (红灯)] ｜ 命中【剧本 X: 名称】
⚡【核心标的定调】龙头A (竞价+4.2% 量比1.8, 超预期抢筹) ｜ 龙头B (平开正常) ｜ 杂毛C (大幅低开-4%, 剔除)
🎯【持仓处置预案】持仓标的X竞价达标，上移保本线继续持有；标的Y不及预期，开盘反抽9:33前减仓止损。
🔘【开盘 5 分钟按键指令】执行剧本 X 对应开仓：9:30盯防龙头A首笔承接打板；若开盘脉冲不追后排。
🛡️【极端熔断条件】若 9:35 前跌停封死超 2 家或指数击穿 S2，全天买入计划自动失效作废。
```

*(注：机器可读 `auction Artifact` 与台账 `eval record --market-phase auction` 在后台静默持久化，不阻塞前台极速交付)*

---

## 五、交付与台账闭环

1. **台账与标准 Artifact 持久化**：
   - 盘前推演后执行：`python scripts/stock_prompt.py eval record --market-phase preopen ...`（自动双写 prediction Artifact）。
   - 9:25 竞价后验执行：`python scripts/stock_prompt.py eval record --market-phase auction ...`（自动双写 auction Artifact）。
2. **可选战报长图**：用户要求生成卡片时，调用 `python scripts/generate_report_card.py --type prediction --json report.json`。
