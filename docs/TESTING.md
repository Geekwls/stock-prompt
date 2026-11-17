# stock-prompt 自动化测试套件与质量工程规范

本文档全面梳理 `stock-prompt` 投研系统的测试工程架构、测试金字塔分层、覆盖率标准、执行方法与 CI/CD 质量门禁。

---

## 一、测试工程概览与指标

| 指标项 | 统计值 | 说明 |
|---|---|---|
| **测试模块数** | 35 个测试模块 | 分布于 `tests/` 目录 |
| **测试用例总数** | **339 个单元与集成测试** | 涵盖确定性数学计算、实盘战法门禁、MCP 数据网关、交易日历门禁与并发多线程等 |
| **测试执行耗时** | ~4.5 秒 | 全量纯 Python 本地快速执行，无需外部网络依赖 |
| **测试通过率** | **100% (339/339 OK)** | 零失败、零警告、零退化 |
| **测试环境要求** | Python 3.10+ | 仅依赖标准库 `unittest` + 可选 `Pillow` (用于战报渲染校验) |

---

## 二、测试架构分层 (Test Architecture)

系统遵循严密的四层测试金字塔设计：

```
                    ┌─────────────────────────┐
                    │  5. 跨模块端到端集成测试  │  (E2E & Pipeline)
                    │   Artifact/Handoff/UI   │
                    ├─────────────────────────┤
                    │  4. 实战交易战法与状态机   │  (Skill Tactics & States)
                    │  四大人设/门禁/自选池核销 │
                    ├─────────────────────────┤
                    │  3. MCP 证据聚合与网关   │  (MarketGraph MCP Context)
                    │   21个公开数据工具/信封 │
                    ├─────────────────────────┤
                    │  2. 确定性计算与风控引擎   │  (Deterministic Calculations)
                    │   仓位预算/大面/容量/止盈│
                    ├─────────────────────────┤
                    │  1. 结构与契约基石校验   │  (Schema, Parity, Prompt)
                    │   版本/母本/格式零漂移  │
                    └─────────────────────────┘
```

---

## 三、测试用例分类与清单详解

### 1. 结构一致性与公共契约测试 (Contracts & Parity)
保障多平台（Antigravity / Gemini / Codex / WorkBuddy）Prompt、版本与 Schema 绝对零漂移。

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_agent_output_contract.py`](../tests/test_agent_output_contract.py) | 2 | 验证所有 5 大 Skill 必须在输出中声明公共首屏摘要卡字段（结论、逻辑状态、位置、置信度、覆盖率、数据状态、最大风险、下一步观察） |
| [`test_schema_parity.py`](../tests/test_schema_parity.py) | 1 | 校验 JSON Schema 定义与运行时代码字段完全同构 |
| [`test_version_parity.py`](../tests/test_version_parity.py) | 7 | 校验 `version.json`、`plugin.json`、`registry.json`、`CHANGELOG.md` 与 Git Tag 版本绝对同步 |
| [`test_sync_prompts.py`](../tests/test_sync_prompts.py) | 4 | 校验 Prompt 宏替换 (`PROMPT_INCLUDE`) 解析与母本展开正确性 |
| [`test_registry.py`](../tests/test_registry.py) | 2 | 校验 Skill 注册表路径与捆绑脚本清单 |
| [`test_release_assets.py`](../tests/test_release_assets.py) | 1 | 验证发布打包资产完整性 |

---

### 2. 确定性纯函数计算与风控引擎测试 (Calculations & Tactical Risk)
验证所有金融工程公式、贝叶斯概率更新、ATR 波动率、仓位总控与极端风险指标的数学确定性。

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_calculations.py`](../tests/test_calculations.py) | 8 | ATR 波动率边界、三态划分、贝叶斯后验概率归一化与上限封顶、盘前机会分与收盘机会分解耦、Brier 评分与 NDCG |
| [`test_calculations_extended.py`](../tests/test_calculations_extended.py) | 11 | 机会分权重自适应衰减、低覆盖率抑制精确评分、极端边界值溢出防护 |
| [`test_tactical_position_and_risk.py`](../tests/test_tactical_position_and_risk.py) | 6 | **v8.1.0 重磅风控**：<br>1. `calculate_tactical_position_budget`：S0-S6 基准仓位锚定、二八割裂强制封顶 $\le 30\%$、极端大面扣减归零；<br>2. `calculate_extreme_loss_effect`：跌停封死超 30 亿或大面集中爆发触发 `short_term_veto`；<br>3. `validate_sector_capacity`：按成交额占比划分超级主线、标准主线与小微游击题材；<br>4. `map_capital_seesaw_matrix`：科技退潮对流红利防御等 A 股资金跷跷板推演；<br>5. `calculate_dynamic_trailing_stop`：浮盈 8% 保本线与浮盈 20% 利润锁定线；<br>6. `validate_stock_hard_gate`：空头破位持仓浮亏时一票否决逆势加仓摊平 |
| [`test_sector_advanced.py`](../tests/test_sector_advanced.py) | 7 | 存量吸血极化度 (`siphon_index`)、连板梯队健康度 (`calculate_ladder_health`)、资金延续性评分 |
| [`test_sector_rotation_fixes.py`](../tests/test_sector_rotation_fixes.py) | 18 | **v8.1.2/v8.1.3 核心审计**：去除入参乐观默认值、超级主线容量双门槛判定、SEI 衰竭分与生命周期一致性校验、无参调用报 `missing` |

---

### 3. 专业 Skill 实战战法与决策门禁测试 (Skill Tactics)
模拟实操盘口，验证四大专业技能的核心交易逻辑。

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_market_prediction_tactics.py`](../tests/test_market_prediction_tactics.py) | 6 | 9:25 竞价极速红绿灯卡、三大情景作战剧本匹配、利好透支冲高回落审计 (`assess_catalyst_exhaustion`)、昨日预案与自选池竞价对账核销 (`reconcile_watchlist_triggers`) |
| [`test_daily_review_tactics.py`](../tests/test_daily_review_tactics.py) | 6 | 二八极端撕裂与假阳线诱多审计 (`calculate_market_divergence_index`)、盘中 10:00 分水岭真假脉冲拦截 (`filter_intraday_impulse`)、次日实战候选作战池结构校验 |
| [`test_sector_rotation_tactics.py`](../tests/test_sector_rotation_tactics.py) | 7 | 电风扇无效轮动过滤器 (`assess_rotation_effectiveness`)、中军 vs 龙头假繁荣背离出货审计 (`calculate_leader_core_divergence`)、多周期时间尺度识别 (`resolve_rotation_timeframe`) |
| [`test_stock_archetype_modes.py`](../tests/test_stock_archetype_modes.py) | 8 | 识别情绪连板、机构趋势、红利价值、次新事件四大生态；全量/减水/事件数据模式适配，次新股不再被粗暴放弃 |
| [`test_stock_report_validation.py`](../tests/test_stock_report_validation.py) | 6 | 校验个股诊断三轴独立裁决输出，减水模式禁用跨模型综合打分 |
| [`test_router_skill.py`](../tests/test_router_skill.py) | 2 | 总控路由聚焦时序调度，禁止替代专业分析，保证 `handoff_store` 程序化调用 |

---

### 4. 数据流水线、持久化与回测台账测试 (Pipeline, Stores & Evaluation)
测试跨交易日的数据流转、防篡改机制与回测打脸复盘。

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_artifact_store.py`](../tests/test_artifact_store.py) | 6 | 标准不可变 Artifact 格式校验、防篡改快照写入、按股票代码主体过滤 |
| [`test_artifact_pipeline.py`](../tests/test_artifact_pipeline.py) | 7 | 竞价快照不可覆盖盘前快照、双写失败平滑降级仅告警、低覆盖率强制移除精确概率与分值 |
| [`test_handoff_store.py`](../tests/test_handoff_store.py) | 12 | 跨 Skill 交接摘要的校验、读写、原子落盘、交易日窗口过滤与安全回滚 |
| [`test_thesis_store.py`](../tests/test_thesis_store.py) | 4 | 个股长期投资逻辑 (Thesis Ledger) 写入、更新历史保留、触发器结构化核验 |
| [`test_eval_tracker.py`](../tests/test_eval_tracker.py) | 29 | 预测评估台账：record (盘前记录)、result (收盘对账)、record-daily (情绪与主线记录)、replay (滚动回放)、misses (漏判主线复盘)、report (Brier与命中率报告)、换行缺失保护与安全落盘 |
| [`test_eval_tracker_versioning.py`](../tests/test_eval_tracker_versioning.py) | 3 | 台账数据 Schema、模型与公式版本自动迁移机制 |
| [`test_review_insights.py`](../tests/test_review_insights.py) | 13 | 周度/月度复盘洞察摘要生成器与多主线迁移矩阵 |
| [`test_trading_calendar.py`](../tests/test_trading_calendar.py) | 17 | 交易日历确定性工具与时间门禁：假期与周末判定、交易日窗口推导、落盘时点合法性门禁 |
| [`test_stock_prompt_cli.py`](../tests/test_stock_prompt_cli.py) | 6 | `scripts/stock_prompt.py` 统一 CLI 子命令转发与调用 |
| [`test_stock_prompt_home.py`](../tests/test_stock_prompt_home.py) | 3 | 环境变量 `STOCK_PROMPT_HOME` 路径解析与状态目录隔离 |

---

### 5. MarketGraph MCP 结构化数据网关测试 (MCP Tools & Aggregation)
针对内置的 21 个 MCP 结构化数据工具与多源聚合网关提供高仿真实测。

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_mcp_server.py`](../tests/test_mcp_server.py) | 74 | 21 个 MCP 原生工具的 Mock 网络传输与解析；内存缓存 LRU 淘汰与主动清扫；HTTP 退避重试与断路器半开自愈探测 |
| [`test_mcp_context_tools.py`](../tests/test_mcp_context_tools.py) | 29 | 核心上下文聚合网关：收盘复盘证据包 (`get_close_review_context`)、轮动证据包 (`get_rotation_context`)、盘前证据包 (`get_prediction_context`)、个股诊断证据包 (`get_stock_diagnostic_context`) 的并发抓取、聚合与降级逻辑 |

---

### 6. 交互驱动与系统管理测试 (UI & Lifecycle)

| 测试文件 | 用例数 | 核心验证内容 |
|---|:---:|---|
| [`test_agent_tool_events_e2e.py`](../tests/test_agent_tool_events_e2e.py) | 3 | 按钮驱动投研分析、证据查看与战报渲染端到端闭环 |
| [`test_ui_event_router.py`](../tests/test_ui_event_router.py) | 5 | UI 事件分发路由、日内 5 大时序守卫、确定性事件免 LLM 介入机制 |
| [`test_install_skills.py`](../tests/test_install_skills.py) | 6 | 工作区捆绑脚本同步、全平台宿主安装器、dry-run 演练 |
| [`test_update_manager.py`](../tests/test_update_manager.py) | 8 | 自动更新管理器：语义化版本比较、校验和比对、防路径遍历与静默缓存 |
| [`test_doctor.py`](../tests/test_doctor.py) | 2 | `stock_prompt.py doctor` 健康诊断与权限检查 |
| [`test_report_card_examples.py`](../tests/test_report_card_examples.py) | 3 | 战报长图 Pillow 渲染管道校验 |

---

## 四、测试运行与质量门禁指南

### 1. 本地快速运行全部测试
在项目根目录下执行：
```bash
# 静默全量运行（推荐日常使用，耗时约 3.5 秒）
python3 -m unittest discover -s tests -q

# 详细输出每个测试用例状态
python3 -m unittest discover -s tests -v

# 仅运行某一类专项测试（以战术风控为例）
python3 -m unittest tests/test_tactical_position_and_risk.py
```

### 2. 发布前五大强制门禁 (Pre-flight Gate Checks)
在每次修改代码或准备提交前，必须顺序执行以下检查：

```bash
# 门禁 1：Prompt 母本一致性检查（严禁手动修改 prompts/ 副本导致漂移）
python3 scripts/sync_prompts.py --check

# 门禁 2：公共契约一致性检查
python3 scripts/sync_skill_contracts.py --check

# 门禁 3：版本与 MCP 清单一致性检查
python3 scripts/check_version_parity.py

# 门禁 4：运行全量 312 项单元测试
python3 -m unittest discover -s tests -q

# 门禁 5：系统健康诊断
python3 scripts/stock_prompt.py doctor
```
全部返回 `[SUCCESS]` 或 `OK` 方可提交 Git。
