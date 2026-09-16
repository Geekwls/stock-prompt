# 个股生态分型与执行场景协议

本协议解决“所有股票使用同一权重”的问题。L1–L8 继续作为证据目录，但先分型、再选模型；不同模型的评分不得横向比较。

## 一、生态分型

| 类型 | 识别证据 | 主模型 | 不得机械套用 |
|---|---|---|---|
| `sentiment_leader` | 连板身位、梯队角色、封板/炸板、换手、竞价和板块情绪 | `sentiment-v1` | 长周期威科夫、以公司质量高低预测次日溢价 |
| `institutional_trend` | 行业景气、业绩、容量中军角色、双基准 RS、机构公开席位、趋势量价 | `institutional-trend-v1` | 只凭单日涨停或单一席位判断长期趋势 |
| `dividend_value` | 股息率、分红稳定性、自由现金流、估值与利率敏感度 | `dividend-value-v1` | 用短线连板身位替代现金流和分红审计 |
| `event_special` | 次新、重组、复牌、控制权变化或重大事件 | `event-special-v1` | 强造长期 RS、完整威科夫阶段或长期综合分 |

执行 `calculate_stock_archetype` 后必须输出：`archetype`、`confidence`、`alternatives`、`evidence` 与 `model_selected`。置信度低或第一、第二类型接近时，保留竞争类型并分别列出下一确认条件，不得强行归类。

量化高参与和高流动性属于横跨多个生态的交易特征标签，不单独作为股票物种。除非公开来源明确证明，不得把普通营业部名称标记为“量化席位”“顶流游资”或“锁仓席位”。

## 二、模型模块

模型权重由 `select_stock_model` 返回。权重仅用于同一 `model_selected + formula_version` 内部比较：

- `sentiment-v1`：市场情绪、板块地位、催化、梯队身位、竞价分时、换手封板、流动性、公司硬风险。
- `institutional-trend-v1`：市场、行业周期、业绩催化、双基准 RS、趋势量价、价格位置、赔率和公司质量。
- `dividend-value-v1`：利率环境、行业稳定性、估值位置、股息可持续性、现金流和治理。
- `event-special-v1`：事件可信度、计价程度、流通盘、换手、分时、可交易性、情景空间和事件风险。

`full` 模式可以输出模型内区间分；`reduced` 和 `event` 模式只能输出条件情景。不同生态模型的 80 分不具有可比性，不得据此跨股票排名。

## 三、威科夫适用性

先调用 `assess_wyckoff_applicability`：

- `applicable`：存在足够交易区间和后续测试，可作为所选模型的一项结构证据。
- `partial`：只描述量价特征和竞争解释，不确认完整阶段，不参与评分。
- `not_applicable`：连续涨停、一字板价格发现不足、突发事件或 event 模式；不输出 Spring/SOS/LPS 阶段，也不因 N/A 扣分。

威科夫永远不是所有股票的强制主模型。

## 四、持仓状态分流

正式输入结构：

```json
{
  "position_state": "watching | holding_profit | holding_loss | unknown",
  "cost_price": null,
  "position_ratio": null,
  "holding_horizon": "intraday | short_swing | trend",
  "risk_tolerance": "low | medium | high"
}
```

调用 `validate_position_context` 后，按场景输出：

- `watching`：观察条件、确认条件、放弃条件和追高/流动性风险；不直接写“立即买入”。
- `holding_loss`：成本附近阻力、反弹弱化条件、结构失效和风险削减情景；不保证解套。
- `holding_profit`：趋势弱化、移动保护、时间退出和事件失效情景；不宣称无风险锁盈。
- `unknown`：通用条件情景，并明确需要补充成本、仓位、周期和风险承受力。

交易计划以“触发条件 → 证据含义 → 条件动作”表达。固定仓位比例、确定性收益承诺或忽略 T+1/涨跌停成交约束的指令均禁止。

## 五、筹码与席位

- 筹码峰、获利盘和集中度只有在数据源、时点和计算口径可追溯时才可进入证据；调用 `calculate_chip_structure` 只记录指标，不自动输出方向。
- 席位调用 `summarize_seat_evidence`；只识别名称直接证明的“机构专用”和沪/深股通，其他席位保留 `unclassified`。
- 龙虎榜只覆盖异常交易日，未上榜不等于没有机构或游资参与；单日净买入不等于锁仓，次日行为必须由竞价和分时重新验证。

