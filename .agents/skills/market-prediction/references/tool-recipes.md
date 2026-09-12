# market-prediction 工具调用与计算配方 (Tool Recipes)

## 一、数据获取与证据采集配方

### 1. 盘前 8:30–9:15 证据簇采集顺序
1. **优先调用 MCP `get_preopen_context`**：
   - 入参：`{"indices": ["SHCI", "SZCI", "CYB", "CSIALL"], "sectors": ["候选主线A", "候选主线B"]}`
   - 返回标准结构：`indices`（含 ATR14 与 MA5/20/60）、`sentiment`（两市量能/炸板率）、`ladder_summary`（连板天梯）、`breadth`（红盘率）；
   - 检查 `data_status`：`ok` 或 `partial` 时正常提取，缺失项以 `missing` 审计；未注册 MCP 时平滑降级为网络搜索。
2. **隔夜外盘与宏观流动性补数（网络搜索）**：
   - 检索截至 8:30 的美股三指、费城半导体 SOX、中概金龙、亚太日韩股市开盘、离岸人民币 USDCNH 与富时 A50 期指。

### 2. 9:25 集合竞价增量证据
- 调用 MCP `get_stock_timeline(symbol)` 获取第一主线龙头及容量中军的 `morning_call_auction` 字段；
- 计算竞价量比（当日竞价成交额 ÷ 昨日竞价成交额）与开盘涨跌幅，执行增量贝叶斯后验修正。

---

## 二、确定性计算函数配方 (无需模型心算)

模型负责证据判档，精确计算统一调用 `scripts/calculate.py` 纯函数库：

| 计算目标 | 命令行调用入口 | 核心输入参数 |
|---|---|---|
| **ATR 三态归类** | `python scripts/calculate.py calculate_atr_state --json '{"close": 3940, "previous_close": 3932, "atr14": 35}'` | `close`, `previous_close`, `atr14` |
| **贝叶斯后验概率** | `python scripts/calculate.py calculate_bayesian_posterior --json '{"prior": {"up": 0.3, "side": 0.5, "down": 0.2}, "likelihoods": [{"up": 1.25, "side": 1.0, "down": 0.8}]}'` | `prior`, `likelihoods` |
| **空间点位与盈亏比** | `python scripts/calculate.py calculate_price_range --json '{"price": 3940, "atr14": 35}'` | `price`, `atr14` |
| **机会函数得分** | `python scripts/calculate.py calculate_opportunity_score --json '{"probabilities": {"up": 36, "side": 48, "down": 16}, "space_up": 0.70, "space_down": 0.72, "mainline_quality": 80, "capital_continuity": 75, "crowding": 35}'` | `probabilities`, `space_up`, `space_down`, `mainline_quality`, `capital_continuity`, `crowding` |
| **主线资金延续分** | `python scripts/calculate.py calculate_capital_continuity --json '{"amount_ratio": 1.05, "break_rate": 0.34, "trigger_count": 5}'` | `amount_ratio`, `break_rate`, `trigger_count` |

---

## 三、台账与不可变 Artifact 落地

```bash
# 盘前推演记录（写入台账并自动双写 prediction Artifact）
python scripts/stock_prompt.py eval record --date YYYY-MM-DD --market-phase preopen --regime S2 \
    --p-up 36 --p-side 48 --p-down 16 --opportunity 54 \
    --top-sector 农业种植 --top-sectors 农业种植,半导体,城市更新 --r1 3968 --s1 3912 \
    --coverage-band high --volatility-band normal --data-status ok \
    --e1 中性 --e2 中性 --e3 偏多 --e4 中性

# 9:25 竞价后验独立记录（写入台账并自动双写 auction Artifact，强制关联 parent）
python scripts/stock_prompt.py eval record --date YYYY-MM-DD --market-phase auction --regime S2 \
    --p-up 40 --p-side 45 --p-down 15 --top-sector 农业种植
```
