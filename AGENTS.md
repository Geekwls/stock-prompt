# stock-prompt Agent 工作指引

本仓库是 A 股四大研究 Skill（盘前推演 / 每日复盘 / 5 日轮动 / 个股诊断）的母本仓库。Agent 在此仓库内工作或被唤醒技能时，遵循以下时段路由与闭环协议；各 Skill 自身规则以 `.agents/skills/*/SKILL.md` 与公共契约为准，本文件只做总路由，不重复其内容。

## 一、时段感知路由 (Master Router)

| 触发条件 | 默认唤醒 Skill | 说明 |
|---|---|---|
| 交易日 08:30–09:15，或用户提到“盘前 / 竞价 / 9:25” | `market-prediction` | 三态概率、空间点位与机会函数；9:25 竞价证据执行后验更新 |
| 交易日 15:00–21:00，或用户提到“复盘 / 收盘” | `daily-review` | 收盘复盘；完成后执行评估台账 `result` 落盘并 `report` |
| 周五收盘 / 周末 / 月末，或用户提到“近5日 / 轮动” | `sector-rotation` | 5 日资金迁移、主线生命周期与衰竭指数 |
| 任意时段输入股票代码 / 名称，或“诊断 XXXXXX” | `stock-analysis` | 八层个股诊断；继承会话中已有的 L1/L2 交接证据 |

用户意图与多个 Skill 匹配时按上表选择或依次执行；不要在复盘 Skill 里生成盘前概率，也不要在盘前 Skill 里做收盘复盘（各 SKILL.md 的“不适用于”声明优先）。

## 二、跨 Skill 闭环协议

1. **交接摘要**：每份报告末尾输出公共契约定义的交接摘要 JSON（`report_type / as_of / coverage / market_regime / primary_sectors / watchlist / risk_flags / next_triggers`）。后续技能直接继承该摘要，缺失字段用空数组或 `N/A`，不得补造。
2. **板块 → 个股穿透**：daily-review 与 sector-rotation 报告中的标的可通过 `诊断 <代码或名称>` 穿透至 stock-analysis；穿透诊断继承前序报告的 Regime 与主线结论作为 L1/L2 证据，仅增量补采缺失部分。
3. **评估台账**（盘前预测 Brier/校准闭环）：
   - 盘前推演完成后：`python3 scripts/eval_tracker.py record ...`（三态概率 / Opportunity / 主线 Top3 / R1 / S1）。
   - 收盘复盘完成后：`python3 scripts/eval_tracker.py result ...`（Z_ATR / 实际主线 Top3 / 收盘高低点），随后 `report` 输出滚动指标。
   - 台账默认为仓库根 `eval/predictions.jsonl`，盘前与收盘必须写入同一文件。

## 三、修改本仓库时的纪律

- `.agents/skills/*/SKILL.md` 是唯一母本：改动后必须运行 `python3 scripts/sync_prompts.py` 再收尾，`--check` 用于校验漂移。
- 公共契约改动后运行 `python3 scripts/sync_skill_contracts.py`。
- `scripts/generate_report_card.py` 与 `scripts/eval_tracker.py` 以 `scripts/` 为母本，由 `python3 scripts/install_skills.py --target workspace` 同步进各 Skill 目录，用 `--check --target workspace` 校验一致性。
- 任何数据缺失遵循公共契约的覆盖率与降级规则；禁止编造行情、覆盖率或评分。

详细设计见 `README.md` 与 `docs/ROADMAP_CROSS_SKILL_PIPELINE.md`。
