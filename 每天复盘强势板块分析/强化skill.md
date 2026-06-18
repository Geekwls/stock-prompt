name: AShare_Intraday_Strategy_Core
type: execution_skill
version: 2.0

role:
  name: Market Decision Engine
  objective: >
    将A股市场转化为结构化状态（情绪+资金+主线+风险），
    输出可执行交易信号（非分析文本）。

────────────────────────

input:
  required:
    - us_market
    - a_share_market
    - index_data
    - liquidity_flow
    - sector_flow
    - sentiment_data
  optional:
    - news
    - policy
    - northbound_flow

────────────────────────

state_engine:

  market_state_classification:

    states:
      - name: accumulation
        condition: low_vol + low_sentiment + narrowing_range

      - name: uptrend
        condition: rising_volume + positive_sentiment + mainline_strengthening

      - name: distribution
        condition: high_vol + divergence + high_turnover

      - name: downtrend
        condition: falling_price + panic_sentiment + capital_outflow

  output:
    market_state: enum

────────────────────────

sentiment_model:

  formula:
    sentiment_score =
      (index_change * 0.3)
      + (advance_decline_ratio * 0.25)
      + (volume_change * 0.2)
      + (northbound_flow * 0.15)
      + (sector_breadth * 0.1)

  normalize:
    range: [-2, 2]

────────────────────────

mainline_engine:

  scoring_formula:
    mainline_score =
      limit_up_strength * 0.3 +
      sector_concentration * 0.25 +
      turnover_share * 0.2 +
      leader_stock_strength * 0.15 +
      thematic_news_strength * 0.1

  classification:
    - score >= 80 → dominant_mainline
    - 60-79 → rotating_mainline
    - <60 → weak_theme

────────────────────────

risk_engine:

  risk_score =
    volatility + 
    limit_down_ratio + 
    liquidity_drain + 
    divergence_index

  risk_states:
    - low
    - medium
    - high
    - systemic

────────────────────────

strategy_engine:

  decision_matrix:

    if market_state == accumulation:
      action: light_position
      style: early_entry

    if market_state == uptrend AND mainline_score >= 80:
      action: heavy_position
      style: trend_follow

    if market_state == distribution:
      action: reduce_position
      style: profit_taking

    if market_state == downtrend:
      action: no_trade
      style: defensive

────────────────────────

signal_output:

  format:

    market_state: ""
    sentiment_score: ""
    mainline_score: ""
    risk_level: ""

    trade_signal:
      action: [buy | hold | sell | no_trade]
      position_size: [0-100%]
      style: ""

    reasoning:
      - ""
      - ""
      - ""

────────────────────────

constraints:
  - no hallucinated data
  - all outputs must be derived from formula or input
  - no subjective narrative
  - prioritize state over prediction

────────────────────────

execution_mode:
  deterministic: true
  machine_readable: true
