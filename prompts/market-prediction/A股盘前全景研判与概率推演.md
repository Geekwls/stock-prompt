# A股盘前全景研判与概率推演引擎

> 基于“市场Regime先验 ➡️ 去重证据簇启发式贝叶斯更新 ➡️ ATR空间盈亏比 ➡️ 归一化机会函数 ➡️ 9:25竞价后验更新 ➡️ 评估闭环”的盘前研判系统。

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

兼容读取历史交接时，将 `report_type=close_review` 归一化为 `daily`，并将 `regime_namespace=daily-s0-s6|preopen-s0-s6` 归一化为 `market-s0-s6`；新写入和新报告只使用标准值。

- 可持久化时用 `handoff_store.py write --stdin` 校验并落盘；不可持久化时保留报告内 JSON 并输出 `handoff_status=emitted_only`。路径优先级为 `--state-dir`、`STOCK_PROMPT_STATE_DIR`、默认 `~/.stock-prompt/state`。
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

## 一、核心哲学与意图映射

系统彻底解耦为两层核心认知，严禁混淆：
1. **Layer 1 市场状态预测 (Market Forecast)**：研判今日三态分布（$P_{\text{Up}}, P_{\text{Side}}, P_{\text{Down}}$）。
2. **Layer 2 交易机会函数 (Opportunity Detection)**：评估今日是否具备可验证的结构性机会。

### 🗣️ 口语化自然语言意图映射 (Natural Language Intent Mapping)
当用户输入以下非标准化口语提问时，自动路由并激活本 Skill 执行盘前与竞价推演：
- **盘前方向**：“明天大盘怎么走”、“明天大盘会跌吗/会涨吗”、“早盘看多还是看空”、“明天能不能买/要不要减仓”
- **竞价窗口**：“9:25 竞价怎么看”、“今天开盘强不强”、“竞价超预期了吗”、“今天早盘开盘策略”
- **推演指令**：“盘前预测”、“今日推演”、“早盘研判”、“大盘概率推演”

---

## 二、证据采集与独立证据簇

采集截至 8:30 的客观数据，归入 **4 大独立证据簇**，权重为 $E_1$(25%)、$E_2$(25%)、$E_3$(20%)、$E_4$(30%)：
- **$E_1$ 全球与亚太科技偏好**：纳指、费城半导体 (SOX)、中概金龙、日韩及亚太芯片股（网络搜索）。
- **$E_2$ 宏观流动性与外汇计价**：富时中国 A50 期指、离岸人民币 (USDCNH)、央行早盘公开市场（网络搜索）。
- **$E_3$ 国内产业政策与突发催化**：部委产业规划、官方公告与产业重大突破（网络搜索）。
- **$E_4$ A股内生量价与连板结构**：宽基指数、成交额偏离度、涨跌比、炸板率与连板梯队。
- **工具调用路由**：优先调用 MCP `get_preopen_context` 获取结构化数据；覆盖率低于 70% 时只输出条件情景，不输出精确评分。具体采集细节见 `references/tool-recipes.md`。

---

## 三、概率推演、空间点位与机会函数

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

### 2. 纯计算与后验更新
模型负责判定定性证据等级，数值计算统一调用 `scripts/calculate.py` 纯函数（参见 `references/tool-recipes.md`）：
- **贝叶斯后验**：由模型评估 4 大证据簇在三态下的似然比，调用 `calculate_bayesian_posterior` 生成归一化后验概率。
- **空间点位引擎**：调用 `calculate_price_range` 结合 ATR14、MA5 与 MA20 输出 R2/R1/Pivot/S1/S2 及上下剩余空间。
- **机会函数 Opportunity (0–100)**：调用 `calculate_opportunity_score`，综合后验概率、盈亏比空间、主线质量与拥挤度。
- **9:25 竞价增量更新**：开盘量比与幅度超预期时执行增量贝叶斯修正；若主线龙头低开核按钮，强制下调机会分。

---

## 四、报告输出模版与术语白话化

按以下结构输出完整报告（缺失维度标注 `N/A`）：
1. **首屏摘要卡（必须置顶）**：按公共 Agent 输出协议输出结论、逻辑状态（市场 Regime）、当前位置（指数空间）、置信度、覆盖率、数据状态、最大风险和下一步观察；同时给出 `next_actions`（竞价更新、查看证据、生成报告）。
2. **白话速览（第一屏，无行话）**：解答“今天大盘大概率怎么走”、“为什么这么看”、“什么信号说明看错了”。
3. **三态概率分布与 Market Regime 定调**：披露先验状态、似然修正过程与归一化概率。
4. **空间点位与盈亏比不对称性**：清晰展示 R2/R1/Pivot/S1/S2、上下剩余空间比。
5. **交易机会函数 Opportunity 评分**：0–100 机会分、风险暴露定级（积极/中性/防守）。
6. **主线板块状态机与资金延续研判**：主线生命周期阶段（启动/分歧/强化/加速/衰竭）。
7. **9:25 集合竞价验证坐标**：次日 9:25 开盘幅度、竞价量比与确认/证伪观测阈值。
8. **研判基准与覆盖率审计**：披露数据时点、来源链接、覆盖率与参与评分权重。
9. **跨 Skill 交接摘要**：文末输出下述 JSON，供盘后复盘与个股诊断继承：

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
  "next_triggers": [{"id": "TRG-0925-01", "condition": "竞价高开>1.5%且金额比>1.2", "status": "pending"}]
}
```

### 术语白话化规则（强制）
专业术语首次出现时必须附不超过一句话的白话解释（白话速览内禁止未解释术语）：
- **概率与空间**：$P_{\text{Up}}$（看涨概率）、ATR（平均真实波幅，衡量日常震荡宽度）、Pivot（日内强弱平衡基准价）。
- **状态与指标**：Market Regime（市场所处的温湿度大环境）、Opportunity（综合胜率与盈亏比的整体交易吸引力得分）。

---

## 五、交付与台账闭环

1. **台账与标准 Artifact 持久化**：
   - 盘前推演后执行：`python scripts/stock_prompt.py eval record --market-phase preopen ...`（自动双写 prediction Artifact）。
   - 9:25 竞价后验执行：`python scripts/stock_prompt.py eval record --market-phase auction ...`（自动双写 auction Artifact）。
2. **可选战报长图**：用户要求生成卡片时，调用 `python scripts/generate_report_card.py --type prediction --json report.json`（可参考 `references/report-card-example.json` 数据结构填入）。
