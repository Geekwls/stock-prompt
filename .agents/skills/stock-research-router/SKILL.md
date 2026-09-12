---
name: stock-research-router
description: >-
  用于A股跨阶段研究编排、模糊意图分流和已有报告的继续分析。适用于用户要求“按完整流程研究”“结合盘前与收盘继续跟踪”“从板块穿透到个股”等跨 Skill 请求；明确的单次盘前、收盘复盘、近5日轮动或个股诊断应直接交给对应专业 Skill。
---

# A股全流程研究总控路由

本 Skill 只负责判断研究阶段、复用已验证上下文并交接给专业 Skill，不自行替代专业分析，也不假设宿主一定支持程序化调用其他 Skill。

执行前读取并遵循 [A股研究公共契约](references/common-research-contract.md)。

<!-- PROMPT_INCLUDE: references/common-research-contract.md -->

## 路由边界

- 明确提到盘前、8:30–9:15 或 9:25 竞价：选择 `market-prediction`。
- 明确提到今日收盘、盘后或每日复盘：选择 `daily-review`。
- 交易日 09:30–15:00 询问盘中大盘走势或板块异动：选择 `daily-review` 的盘中快照模式；`as_of` 标注盘中时点、`status=partial`，不强制写收盘评估台账，待 15:00 后再确定性回测。
- 交易日 09:30–15:00 询问盘中大盘走势或板块异动：选择 `daily-review` 的盘中快照模式；`as_of` 标注盘中时点、`status=partial`，不强制写收盘评估台账，待 15:00 后再确定性回测。
- 交易日 09:30–15:00 询问盘中大盘走势或板块异动：选择 `daily-review` 的盘中快照模式；`as_of` 标注盘中时点、`status=partial`，不强制写收盘评估台账，待 15:00 后再确定性回测。
- 明确提到近5日、周末复盘、板块轮动：选择 `sector-rotation`。
- 明确给出股票代码、名称或要求诊断个股：选择 `stock-analysis`。
- 只有请求横跨两个以上阶段、要求继续前序研究，或意图无法由单一专业 Skill 完成时，才使用本 Router。

用户明确指定的任务优先于时间规则。不要仅因当前时间位于某个窗口，就覆盖用户清晰表达的意图。

## 编排流程

1. 提取用户要求的研究对象、时间范围、所处阶段和最终交付。
2. **上下文读取（Artifact 优先，Handoff 回退）**：优先执行当前 Router Skill 根目录的 `scripts/artifact_store.py latest --type <prediction|auction|close_actual|daily_score|rotation|stock_diagnostic> --within-trading-days 3`（个股诊断加 `--subject <股票代码>`）读取最新有效 Artifact；输出为 `N/A`、`(expired)` 或文件损坏，以及脚本不可执行时，回退 `scripts/handoff_store.py latest --within-trading-days 3`（个股同样加 `--subject`）；两者都不可用时检查当前会话已有摘要。路由决策必须注明本次上下文来源（artifact / handoff / 会话）与日历精度。
3. 输出简短路由决策：目标 Skill、可继承证据、仍需补采的数据。不得把旧摘要伪装为当前事实。
4. 若宿主支持 Skill 调度，交由目标专业 Skill 执行；不支持时，明确提示用户调用对应 Skill，不在 Router 内复制整套专业框架。
5. 专业报告完成后，用当前目标 Skill 根目录的 `scripts/handoff_store.py write --stdin` 校验并落盘交接摘要（rotation / stock 交接会自动双写为标准 Artifact，`eval_tracker` 的 record / result / record-daily 同理）；任何写入失败必须披露，不能声称闭环完成。
6. daily-review 或 sector-rotation 输出标的池后，提供 `诊断 <代码或名称>` 的个股穿透入口；个股诊断只继承有来源的 L1/L2，继续补采 L3–L8。

## 多阶段任务顺序

- 盘前到收盘：先 `market-prediction`，收盘后由 `daily-review` 读取同日预测摘要并记录实际结果。
- 收盘到个股：先 `daily-review` 或 `sector-rotation`，再将有证据的市场与板块状态交给 `stock-analysis`。
- 周末全流程：先 `sector-rotation` 确定中期板块状态；若用户指定标的，再执行 `stock-analysis`。

每个阶段保持自己的适用边界：不得在盘前生成尚不存在的收盘数据，不得在收盘复盘中伪造盘前预测，也不得因交接存在而跳过数据新鲜度检查。

## 输出格式

```text
首屏摘要卡：
结论：<本次路由要做什么>
逻辑状态：<已识别 / 需澄清 / 无法路由>
当前位置：<当前研究阶段>
置信度：<高 / 中 / 低 / 数据不足>
数据覆盖率：<上下文覆盖率或 N/A>
数据状态：<完整数据 / 部分数据 / 数据不足>
最大风险：<过期、冲突或缺失上下文>
下一步观察：<目标 Skill 的第一项验证>

路由决策：<目标 Skill 或执行顺序>
继承上下文：<交接文件、日期、来源；没有则 N/A>
需补数据：<列表>
执行状态：<已交由宿主调度 / 请用户调用对应 Skill / 已完成>
下一入口：<可选的后续 Skill 或“诊断 代码”>
```

Router 的 `next_actions` 使用 `view_evidence`、`retry_data` 或跳转目标 Skill；不得输出专业评分或买卖结论。

Router 不输出市场评分、涨跌概率、威科夫阶段或买卖建议；这些内容只能由相应专业 Skill 基于完整证据生成。
