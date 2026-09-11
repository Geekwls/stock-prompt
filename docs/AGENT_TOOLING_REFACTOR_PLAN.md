# Agent 工具化与 Skill 解耦实施计划

> **文档状态**：Accepted / 分阶段实施中
>
> **规范边界**：本文是 Tool、Artifact、Router 与 Evaluator 的工程实施主计划；具体机器字段以 `contracts/artifacts/*.schema.json` 和 `registry.json` 为准，研究纪律以 `contracts/common-research-contract.md` 为准。
> **与 UI 文档关系**：`UI_MODEL_SEPARATION_DESIGN.md` 只定义交互层如何消费本计划产出的 Artifact，不重复定义 Artifact 业务语义。

## 当前实施状态（v7.1.1 基线）

| 能力 | 状态 | 当前证据 / 下一缺口 |
|---|---|---|
| 四个专业 Skill 独立运行 | 已完成 | 公共契约允许无 Handoff/MCP 时独立补采或降级 |
| PREOPEN / AUCTION 不可变分离 | 已完成 | `eval_tracker.py` 按 `market_phase` 与 revision 管理 |
| Handoff / Thesis / 评估持久化 | 已完成 | 已有独立脚本和统一 CLI 兼容入口 |
| 通用 Artifact Schema 与存储 | 已完成（P0） | 8 类 Schema、7 组 fixture、不可变快照存储与统一 CLI 已接入注册表和安装器 |
| 确定性计算工具化 | 已完成（首批） | `tools/calculations/` 已覆盖市场、板块、个股与评估的 21 个纯函数；后续只扩展口径，不回填模型手算 |
| 上下文型 MCP 工具 | 未完成 | 当前为 13 个细粒度数据工具 |
| Skill 主文件压缩 | 待兼容期验证 | 等 Artifact/计算结果与旧路径对照稳定后执行，避免一次性迁移 |
| UI 工程 | 不在本仓库当前交付内 | 本仓库先提供事件与 Artifact 接口契约 |

## 目标

将项目从“长提示词研究框架”升级为可执行、可测试、可审计的 Agent 研究系统：

```text
Skill      = 指导模型何时做、调用什么、如何判断、何时停止、输出什么
Tool       = 获取数据、计算指标、校验 Schema、持久化状态、渲染结果
Artifact   = 传递结构化事实、预测、结果和状态
Router     = 判断意图、编排阶段、处理降级
Evaluator  = 衡量预测质量和模型校准
```

## 设计原则

1. 四个专业 Skill 必须能独立运行；前序 Skill、Handoff、台账、本地脚本或 MCP 不得成为硬前置条件。
2. Skill 依赖公共契约和工具接口，不直接依赖另一个 Skill 的执行成功。
3. 共享自然语言结论改为共享结构化 Artifact，并保留 `as_of`、来源、口径、覆盖率和版本。
4. 精确计算由工具完成，模型负责工具选择、证据解释、风险识别和报告组织。
5. 报告生成、状态持久化、评估和渲染互相解耦；附属流程失败不应否定专业分析结果。
6. 盘前 `PREOPEN_V1`、竞价 `AUCTION_V2`、收盘 `CLOSE_ACTUAL` 必须不可变并分别评价。

## 阶段 0：建立基线

### 工作项

- 为四个专业 Skill、Handoff、评估器建立固定输入和输出样例。
- 记录当前 13 个 MarketGraph MCP 工具、脚本和 Schema 的行为基线。
- 建立单元测试、集成测试和 Artifact fixtures。
- 固定现有指标口径，避免重构过程中无意改变结果。

### 验收标准

- 当前测试全部通过。
- 每个主要流程至少有一组可复现样例。
- 重构前后相同输入的指标差异可解释。

## 阶段 1：明确目录与接口边界

建议新增或整理为：

```text
contracts/artifacts/
  evidence.schema.json
  prediction.schema.json
  auction.schema.json
  close_actual.schema.json
  daily_score.schema.json
  rotation.schema.json
  stock_diagnostic.schema.json

tools/
  calculations/
  artifacts/
  orchestration/

tests/
  fixtures/
  unit/
  integration/
```

现有 `scripts/` 保留兼容入口，但逐步变成薄封装，调用 `tools/` 中的实现。

当前已提供：

```text
scripts/artifact_store.py  -> tools/artifacts/store.py
scripts/calculate.py       -> tools/calculations/*
scripts/eval_tracker.py    -> 复用统一 ATR 三态与 Brier 函数
```

## 阶段 2：建立 Artifact 层

### 必要 Artifact

#### Prediction Artifact

包含交易日、阶段、`as_of`、市场 Regime、三态概率、R1/S1、机会分、主线、证据编号、覆盖率和版本。

#### Auction Artifact

引用 `PREOPEN_V1`，记录竞价证据、后验概率和信息增量，不覆盖盘前版本。

#### Close Actual Artifact

记录实际三态、Z_ATR、最高/最低点、实际主线和收盘数据状态。

#### Stock Diagnostic Artifact

记录标的、L1–L8、逻辑健康度、结构位置、置信度、确认条件、失效条件和证据编号。

### 验收标准

- 所有 Artifact 通过 JSON Schema 校验。
- 所有 Artifact 带 `as_of`、来源、覆盖率和版本。
- 缺失字段使用 `N/A`、空数组或明确状态，不使用示例值填充。

## 阶段 3：将计算逻辑下沉到工具

### 市场计算

实现：

```text
calculate_atr_state
calculate_market_regime
calculate_bayesian_posterior
calculate_opportunity_score
calculate_price_range
```

### 板块计算

实现：

```text
calculate_capital_continuity
calculate_sector_exhaustion
calculate_rotation_state
calculate_sector_ranking
calculate_lifecycle_state
```

### 个股计算

实现：

```text
validate_stock_hard_gate
calculate_relative_strength
calculate_wyckoff_features
calculate_price_position
calculate_risk_reward
```

### 评估计算

实现：

```text
calculate_multiclass_brier
calculate_interval_score
calculate_topk_metrics
calculate_ndcg
calculate_lifecycle_accuracy
calculate_calibration_curve
```

每个计算结果必须包含 `formula_version`、输入快照 ID、缺失字段和计算状态。

首批实现已落在 `tools/calculations/`，并由 `scripts/calculate.py` 暴露统一 JSON CLI。威科夫工具仅生成可审计量价特征，不替模型确认阶段；生命周期与 Regime 工具仅在明确规则命中时给出状态，否则返回 `N/A`，避免把不完整事实伪装成确定分类。

## 阶段 4：升级 MarketGraph MCP

在现有细粒度工具之外，增加少量上下文型工具：

```text
get_preopen_context
get_close_review_context
get_rotation_context
get_stock_diagnostic_context
```

这些工具只返回标准化证据，不直接输出买卖结论。统一返回：

```json
{
  "data_status": "ok",
  "source": "...",
  "source_family": "...",
  "independence_group": "...",
  "data_date": "...",
  "as_of": "...",
  "payload": {},
  "missing": [],
  "conflicts": []
}
```

上下文型工具不能变成不可审计的 `analyze_market()` 黑箱；数据获取、计算和结论仍需可拆解。

## 阶段 5：压缩 Skill 主文件

目标行数：

| Skill | 当前规模 | 目标规模 |
|---|---:|---:|
| `market-prediction` | 449 行 | 100–140 行 |
| `daily-review` | 335 行 | 100–130 行 |
| `sector-rotation` | 247 行 | 90–120 行 |
| `stock-analysis` | 247 行 | 120–160 行 |
| `stock-research-router` | 52 行 | 50–80 行 |

主文件只保留：适用场景、工具顺序、关键禁止事项、硬门槛、降级规则、输出字段和 Artifact 交接。

以下内容下沉到代码或参考文件：公式、指标计算、台账实现、报告卡模板、重复的公共契约和 CLI 细节。

## 阶段 6：增加工具调用配方

为每个 Skill 增加 `references/tool-recipes.md`，明确：

- 调用条件和顺序；
- 必填参数；
- 成功与失败判定；
- 重试和降级策略；
- 返回字段可支持的结论；
- 不可由该工具证明的结论。

示例：

```text
盘前 → get_preopen_context
检查 data_status 和 coverage
覆盖率 < 70% → 禁止精确概率和机会分
调用计算工具
输出 Prediction Artifact
```

## 阶段 7：统一 Agent 工具入口

保留现有 CLI 兼容性，同时提供统一入口：

```text
python scripts/stock_prompt.py artifact ...
python scripts/stock_prompt.py calculate ...
python scripts/stock_prompt.py calibration ...
python scripts/stock_prompt.py diagnose ...
```

优先将下列能力暴露为 Agent 可直接调用的 MCP 工具：

```text
save_artifact
load_artifact
calculate_metrics
evaluate_prediction
render_report
```

CLI 作为人工、CI 和故障排查入口；MCP 作为 Agent 入口。

## 阶段 8：统一失败与降级策略

| 失败类型 | 当前分析 | 后续闭环 |
|---|---|---|
| 单个数据源失败 | 继续并标记缺失 | 降低覆盖率 |
| MCP 不可用 | 网络检索或 N/A | 关闭精确评分 |
| Handoff 不可写 | 报告仍完成 | `handoff_status=emitted_only` |
| 台账不可写 | 报告仍完成 | `evaluation_status=failed` |
| 行情硬门槛失败 | 保留事实 | 禁止综合评分 |
| 来源冲突 | 并列披露 | 降低置信度 |
| Schema 失败 | 不发布 Artifact | 返回修复错误 |

## 阶段 9：测试体系

### 单元测试

覆盖 ATR、三态归类、Brier、区间评分、SEI、资金延续、RS、覆盖率、日期边界、冲突处理和 Schema。

### 集成测试

模拟 MCP 正常、部分失败、完全不可用、Handoff 不可写、台账不可写、Artifact 过期和来源冲突。

### Agent 行为测试

验证模型是否：

- 调用正确工具；
- 避免重复调用；
- 不使用过期 Artifact；
- 低覆盖率时停止精确评分；
- 不将 P3 数据表述为官方事实；
- 不把盘后数据带入盘前；
- 没有前序 Skill 时仍能独立完成任务。

## 阶段 10：兼容迁移

采用两阶段迁移：

### 兼容模式

- 新旧工具并行；
- 新旧 Artifact 并行生成；
- 对比指标结果；
- 保留旧 CLI 入口；
- 记录口径变化。

### 精简模式

- 删除 Skill 中重复公式；
- 删除重复 CLI 说明；
- 将报告卡模板移出 Skill；
- 更新 README、安装器和同步检查。

## 优先级

### P0

- Artifact Schema；
- 计算逻辑工具化；
- Skill 独立运行；
- 失败降级；
- PREOPEN_V1/AUCTION_V2 分离；
- 统一证据对象。

### P1

- 四个上下文型 MCP 工具；
- CLI 统一封装；
- Calibration Engine 独立化；
- 工具调用配方；
- 集成测试。

### P2

- Skill 主文件压缩；
- 报告模板移出 Skill；
- 自动化调度；
- 展示层；
- 工具耗时和调用成本监控。

## 最终验收标准

```text
四个专业 Skill 可单独运行
无 Handoff 也能完成首次分析
无 MCP 时按规则降级
关键指标全部由工具计算
报告与 Artifact 分离
Handoff 写入失败不阻断分析
评估台账独立于 daily-review
PREOPEN_V1 不被 AUCTION_V2 覆盖
所有 Artifact 可 Schema 校验
所有指标带 formula_version
结论可回溯 evidence_id
模型无需手写复杂 CLI 命令
```

## 成功指标

重构后持续跟踪：

- 工具调用成功率；
- 计算结果复现率；
- 错误数据拦截率；
- 无前序依赖独立完成率；
- 单任务平均 Token 消耗；
- 跨 Skill 结论一致性；
- MCP 和 Artifact 失败恢复率。
