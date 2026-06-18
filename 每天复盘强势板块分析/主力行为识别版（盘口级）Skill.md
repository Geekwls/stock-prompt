name: AShare_Whale_Behavior_Skill
type: execution_skill
version: 4.0

role:
  name: Market Microstructure Analyst
  objective: >
    识别主力资金在盘口中的真实行为（吸筹/试盘/拉升/派发/砸盘），
    通过成交结构+盘口语言+量价关系还原资金意图。

────────────────────────

input:
  required:
    - tick_data
    - order_book_data
    - volume_profile
    - limit_up_structure
    - sector_flow
    - index_context
  optional:
    - news_flow
    - northbound_flow

────────────────────────

microstructure_model:

  ① 吸筹识别（Accumulation）

    signals:
      - 缩量横盘但逐步抬高低点
      - 主动买单稳定出现（小单密集）
      - 大单拆分成交（拆单吸筹）
      - 上涨无明显放量

    interpretation:
      - 主力低成本建仓
      - 控盘初期

    score: 0~100

────────────────────────

  ② 试盘行为（Testing）

    signals:
      - 瞬间拉升后快速回落
      - 小幅放量试压力位
      - 上影线频繁出现
      - 涨跌反复

    interpretation:
      - 测试上方抛压
      - 判断市场承接力

    score: 0~100

────────────────────────

  ③ 拉升行为（Markup）

    signals:
      - 连续主动买单扫货
      - 成交量阶梯式放大
      - 涨停前逐步锁单
      - 分时不回撤

    interpretation:
      - 主升浪启动
      - 资金共识形成

    score: 0~100

────────────────────────

  ④ 派发行为（Distribution）

    signals:
      - 高位放量滞涨
      - 上冲无力反复炸板
      - 主动卖单增加
      - 分时震荡加剧

    interpretation:
      - 主力逐步出货
      - 接盘资金承接

    score: 0~100

────────────────────────

  ⑤ 砸盘行为（Markdown）

    signals:
      - 连续大单卖出
      - 跌停封单出现
      - 流动性快速下降
      - 无承接直接下跌

    interpretation:
      - 主力撤退
      - 流动性崩塌

    score: 0~100

────────────────────────

order_book_analysis:

  key_metrics:

    - bid_ask_imbalance
    - large_order_ratio
    - cancel_order_frequency
    - hidden_order_probability

  interpretation:

    imbalance > 1.5 → 买盘主导
    imbalance < 0.7 → 卖盘主导

────────────────────────

volume_structure:

  patterns:

    - 放量上涨 = 主动拉升
    - 放量滞涨 = 派发
    - 缩量上涨 = 控盘
    - 放量下跌 = 出货

────────────────────────

limit_up_behavior:

  patterns:

    - 一字板：强控盘
    - 烂板回封：承接强
    - 炸板频繁：分歧
    - 封单递减：派发前兆

────────────────────────

fund_intent_inference:

  classify:

    - accumulation_phase
    - manipulation_phase
    - distribution_phase
    - exit_phase

────────────────────────

whale_state_machine:

  state_logic:

    accumulation:
      - low_vol
      - rising_support
      - hidden_buying

    markup:
      - volume_expansion
      - strong_buy_pressure
      - breakout_continuation

    distribution:
      - high_vol_no_price_increase
      - repeated rejection

    exit:
      - aggressive_sell_orders
      - liquidity_drop

────────────────────────

final_output:

  format:

    whale_state: ""
    phase: ""

    key_signals:
      - ""
      - ""
      - ""

    intent_inference:
      - "吸筹 / 拉升 / 出货 / 砸盘"

    strength_score: 0-100

    trade_implication:
      action: [buy | hold | reduce | exit | no_trade]
      position: [0-100%]

    reasoning_chain:
      - "盘口行为"
      - "成交结构"
      - "量价关系"
      - "订单流变化"

────────────────────────

constraints:
  - only infer from observable market structure
  - no subjective storytelling
  - no news-driven override unless confirmed by flow
  - priority: order flow > price > sentiment

────────────────────────

execution_mode:
  deterministic: true
  microstructure_based: true
