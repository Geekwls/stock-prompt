"""个股分型、数据模式、结构适用性、相对强度、位置与赔率。"""

from .common import result


ARCHETYPES = ("sentiment_leader", "institutional_trend", "dividend_value", "event_special")
POSITION_STATES = ("watching", "holding_profit", "holding_loss", "unknown")


MODEL_PROFILES = {
    "sentiment_leader": {
        "model_selected": "sentiment-v1",
        "modules": {
            "market_sentiment": 10, "sector_status": 20, "catalyst": 10,
            "ladder_and_position": 15, "auction_and_intraday": 15,
            "turnover_and_seal_quality": 15, "liquidity_risk": 10, "company_red_flags": 5,
        },
    },
    "institutional_trend": {
        "model_selected": "institutional-trend-v1",
        "modules": {
            "market_regime": 10, "industry_cycle": 15, "catalyst_and_earnings": 15,
            "relative_strength": 15, "trend_and_volume": 15, "price_position": 10,
            "risk_reward": 10, "company_quality": 10,
        },
    },
    "dividend_value": {
        "model_selected": "dividend-value-v1",
        "modules": {
            "rate_and_market_regime": 5, "industry_stability": 10, "catalyst": 5,
            "relative_strength": 5, "trend_stability": 10, "valuation_position": 15,
            "dividend_sustainability": 20, "cashflow_and_governance": 30,
        },
    },
    "event_special": {
        "model_selected": "event-special-v1",
        "modules": {
            "market_sentiment": 10, "sector_status": 10, "event_credibility": 25,
            "event_pricing": 15, "turnover_and_intraday": 15, "float_and_liquidity": 10,
            "scenario_asymmetry": 5, "company_and_event_risk": 10,
        },
    },
}


def resolve_stock_data_mode(
        bar_count=None, adjusted=None, benchmark_complete=None, industry_complete=None,
        days_listed=None, event_driven=False, resumed_recently=False, is_suspended=None,
        quote_available=None, timeline_available=None, turnover_available=None,
        input_snapshot_id=None):
    """将个股数据能力分为 full / reduced / event，不再用 120 根 K 线一刀切。"""
    bars = int(bar_count or 0)
    event_hint = bool(event_driven or resumed_recently or (days_listed is not None and days_listed < 120))
    if is_suspended is True:
        return result(
            {
                "mode": "event", "tradable": False,
                "allowed": ["event_facts", "company_risk", "conditional_scenarios"],
                "forbidden": ["intraday_execution", "precise_risk_reward", "composite_score"],
            },
            "stock-data-mode-v1", input_snapshot_id, ["not_suspended"], "partial",
        )

    if bars >= 120 and adjusted is True and benchmark_complete is True and industry_complete is True and not event_hint:
        return result(
            {
                "mode": "full", "tradable": True,
                "allowed": ["dual_benchmark_rs", "long_cycle_structure", "price_position", "risk_reward", "within_model_score"],
                "forbidden": [],
            },
            "stock-data-mode-v1", input_snapshot_id,
        )

    if bars >= 20 and adjusted is True and not event_hint:
        missing = []
        if benchmark_complete is not True:
            missing.append("broad_market_baseline")
        if industry_complete is not True:
            missing.append("industry_baseline")
        if bars < 120:
            missing.append("adjusted_bars>=120")
        return result(
            {
                "mode": "reduced", "tradable": True,
                "allowed": ["short_window_returns", "short_window_volume", "observable_structure", "conditional_scenarios"],
                "forbidden": ["long_cycle_wyckoff_confirmation", "long_window_rs", "cross_model_score", "composite_score"],
            },
            "stock-data-mode-v1", input_snapshot_id, missing, "partial",
        )

    missing = []
    if quote_available is not True:
        missing.append("quote")
    if timeline_available is not True:
        missing.append("timeline")
    if turnover_available is not True:
        missing.append("turnover")
    if adjusted is not True and bars:
        missing.append("adjustment_method")
    status = "complete" if not missing else "partial" if len(missing) < 3 else "unavailable"
    return result(
        {
            "mode": "event", "tradable": status != "unavailable",
            "allowed": ["event_facts", "float_and_liquidity", "turnover", "intraday_observation", "conditional_scenarios"],
            "forbidden": ["long_cycle_wyckoff_confirmation", "long_window_rs", "composite_score"],
        },
        "stock-data-mode-v1", input_snapshot_id, missing, status,
    )


def classify_stock_archetype(
        limit_up_streak=None, recent_limit_up_count=None, turnover_rate=None, sector_role=None,
        trend_alignment=None, institutional_net_buy=None, earnings_growth=None,
        dividend_yield=None, payout_stable=None, operating_cashflow_positive=None,
        event_driven=False, resumed_recently=False, days_listed=None, input_snapshot_id=None):
    """基于显式证据选择诊断模型；证据不足时返回 N/A，不猜测股票物种。"""
    scores = {name: 0.0 for name in ARCHETYPES}
    evidence = {name: [] for name in ARCHETYPES}

    def add(name, points, label):
        scores[name] += points
        evidence[name].append(label)

    if event_driven:
        add("event_special", 4, "event_driven")
    if resumed_recently:
        add("event_special", 3, "resumed_recently")
    if days_listed is not None and days_listed < 120:
        add("event_special", 2, "listed_under_120_days")
    if limit_up_streak is not None and limit_up_streak >= 2:
        add("sentiment_leader", 4, "limit_up_streak>=2")
    if recent_limit_up_count is not None and recent_limit_up_count >= 2:
        add("sentiment_leader", 2, "recent_limit_up_count>=2")
    if str(sector_role or "").lower() in {"leader", "龙头", "最高板", "核心龙头"}:
        add("sentiment_leader", 2, "sector_leader_role")
    if turnover_rate is not None and turnover_rate >= 15:
        add("sentiment_leader", 1, "turnover_rate>=15%")
    if str(trend_alignment or "").lower() in {"bullish", "bullish_uptrend", "多头", "多头排列"}:
        add("institutional_trend", 2, "bullish_trend_alignment")
    if institutional_net_buy is not None and institutional_net_buy > 0:
        add("institutional_trend", 2, "institutional_net_buy>0")
    if earnings_growth is not None and earnings_growth > 0:
        add("institutional_trend", 1, "earnings_growth>0")
    if str(sector_role or "").lower() in {"中军", "capacity_anchor", "容量中军"}:
        add("institutional_trend", 2, "capacity_anchor_role")
    if dividend_yield is not None and dividend_yield >= 3:
        add("dividend_value", 3, "dividend_yield>=3%")
    if payout_stable is True:
        add("dividend_value", 2, "payout_stable")
    if operating_cashflow_positive is True:
        add("dividend_value", 1, "operating_cashflow_positive")

    ranked = sorted(scores, key=lambda name: (-scores[name], ARCHETYPES.index(name)))
    top, second = ranked[0], ranked[1]
    if scores[top] <= 0:
        return result("N/A", "stock-archetype-v1", input_snapshot_id, ["archetype_evidence"], "unavailable")
    margin = scores[top] - scores[second]
    confidence = "高" if scores[top] >= 4 and margin >= 2 else "中" if scores[top] >= 2 and margin >= 1 else "低"
    alternatives = [name for name in ranked[1:] if scores[name] > 0 and scores[top] - scores[name] <= 2]
    profile = MODEL_PROFILES[top]
    return result(
        {
            "archetype": top,
            "confidence": confidence,
            "alternatives": alternatives,
            "evidence": evidence[top],
            "scores": scores,
            "model_selected": profile["model_selected"],
        },
        "stock-archetype-v1", input_snapshot_id,
    )


def select_stock_model(archetype, data_mode="full", input_snapshot_id=None):
    """返回分型模型模块；不同模型的分数禁止横向比较。"""
    if archetype not in MODEL_PROFILES:
        return result("N/A", "stock-model-router-v1", input_snapshot_id, ["valid_archetype"], "unavailable")
    if data_mode not in {"full", "reduced", "event"}:
        raise ValueError("data_mode 必须是 full / reduced / event")
    profile = MODEL_PROFILES[archetype]
    score_enabled = data_mode == "full"
    return result(
        {
            "archetype": archetype,
            "model_selected": profile["model_selected"],
            "modules": profile["modules"],
            "score_enabled": score_enabled,
            "score_comparability": "same_model_same_version_only" if score_enabled else "not_applicable",
            "output_mode": "model_score_and_scenarios" if score_enabled else "conditional_scenarios_only",
        },
        "stock-model-router-v1", input_snapshot_id,
        [] if score_enabled else ["full_mode_required_for_score"],
        "complete" if score_enabled else "partial",
    )


def assess_wyckoff_applicability(
        data_mode, range_days=None, limit_up_streak=None, event_driven=False,
        one_word_limit_days=None, input_snapshot_id=None):
    """判断威科夫是否适用；不适用不扣分，也不强行生成阶段。"""
    if data_mode not in {"full", "reduced", "event"}:
        raise ValueError("data_mode 必须是 full / reduced / event")
    reasons = []
    if event_driven or data_mode == "event":
        reasons.append("event_mode")
    if limit_up_streak is not None and limit_up_streak >= 2:
        reasons.append("continuous_limit_up_sequence")
    if one_word_limit_days is not None and one_word_limit_days >= 2:
        reasons.append("insufficient_price_discovery")
    if reasons:
        return result(
            {"applicability": "not_applicable", "use_in_score": False, "reasons": reasons},
            "wyckoff-applicability-v1", input_snapshot_id,
        )
    if range_days is None or range_days < 20:
        return result(
            {"applicability": "partial", "use_in_score": False, "reasons": ["range_days<20_or_unknown"]},
            "wyckoff-applicability-v1", input_snapshot_id, ["range_days>=20"], "partial",
        )
    applicability = "applicable" if data_mode == "full" and range_days >= 40 else "partial"
    return result(
        {"applicability": applicability, "use_in_score": applicability == "applicable", "reasons": []},
        "wyckoff-applicability-v1", input_snapshot_id,
        [] if applicability == "applicable" else ["full_mode_and_range_days>=40"],
        "complete" if applicability == "applicable" else "partial",
    )


def validate_position_context(
        position_state="unknown", cost_price=None, position_ratio=None,
        holding_horizon=None, risk_tolerance=None, input_snapshot_id=None):
    """校验用户状态输入，决定输出观察/解套/保护哪类条件方案。"""
    if position_state not in POSITION_STATES:
        raise ValueError("position_state 必须是 watching / holding_profit / holding_loss / unknown")
    if position_ratio is not None and not 0 <= float(position_ratio) <= 100:
        raise ValueError("position_ratio 必须位于 0–100")
    if holding_horizon is not None and holding_horizon not in {"intraday", "short_swing", "trend"}:
        raise ValueError("holding_horizon 必须是 intraday / short_swing / trend")
    if risk_tolerance is not None and risk_tolerance not in {"low", "medium", "high"}:
        raise ValueError("risk_tolerance 必须是 low / medium / high")
    missing = []
    if position_state in {"holding_profit", "holding_loss"} and cost_price is None:
        missing.append("cost_price")
    if position_state != "watching" and position_ratio is None:
        missing.append("position_ratio")
    if holding_horizon is None:
        missing.append("holding_horizon")
    if risk_tolerance is None:
        missing.append("risk_tolerance")
    scenario = {
        "watching": "entry_observation_plan",
        "holding_profit": "profit_protection_plan",
        "holding_loss": "recovery_and_risk_reduction_plan",
        "unknown": "generic_conditional_scenarios",
    }[position_state]
    return result(
        {
            "position_state": position_state, "cost_price": cost_price,
            "position_ratio": position_ratio, "holding_horizon": holding_horizon,
            "risk_tolerance": risk_tolerance, "scenario": scenario,
            "personalized_actions_allowed": not missing and position_state != "unknown",
        },
        "position-context-v1", input_snapshot_id, missing,
        "complete" if not missing else "partial",
    )


def summarize_seat_evidence(entries, input_snapshot_id=None):
    """只识别公开名称可直接证明的席位类型；不凭营业部名称猜测量化或游资身份。"""
    if not isinstance(entries, list) or not entries:
        return result("N/A", "seat-evidence-v1", input_snapshot_id, ["seat_entries"], "unavailable")
    summary = {"institutional": [], "northbound": [], "unclassified": []}
    for entry in entries:
        name = str((entry or {}).get("seat_name") or (entry or {}).get("name") or "").strip()
        item = {"seat_name": name or "N/A", "net_buy": (entry or {}).get("net_buy")}
        if "机构专用" in name:
            summary["institutional"].append(item)
        elif "沪股通" in name or "深股通" in name:
            summary["northbound"].append(item)
        else:
            summary["unclassified"].append(item)
    summary["identity_boundary"] = "unclassified 席位不得自动标记为量化、游资或锁仓席位"
    return result(summary, "seat-evidence-v1", input_snapshot_id)


def calculate_chip_structure(
        profit_ratio=None, concentration_90=None, overhead_density=None,
        data_source=None, as_of=None, input_snapshot_id=None):
    """记录可核验筹码指标，不根据不可追溯数据生成方向结论。"""
    missing = []
    if not data_source:
        missing.append("data_source")
    if not as_of:
        missing.append("as_of")
    values = {
        "profit_ratio": profit_ratio,
        "concentration_90": concentration_90,
        "overhead_density": overhead_density,
        "data_source": data_source,
        "as_of": as_of,
        "interpretation": "requires_model_with_source_methodology",
    }
    if all(value is None for value in (profit_ratio, concentration_90, overhead_density)):
        missing.append("chip_metrics")
    return result(values if "chip_metrics" not in missing else "N/A", "chip-structure-v1", input_snapshot_id,
                  missing, "complete" if not missing else "partial" if "chip_metrics" not in missing else "unavailable")


def validate_stock_hard_gate(bar_count=None, adjusted=None, benchmark_complete=None, industry_complete=None,
                             input_snapshot_id=None, is_st=None, days_listed=None,
                             kline_count=None, is_suspended=None):
    """兼容旧调用：仅 full_mode 返回 True；新流程应直接调用 resolve_stock_data_mode。"""
    shortcut_mode = any(value is not None for value in (is_st, days_listed, kline_count, is_suspended))
    if bar_count is None:
        bar_count = kline_count
    mode = resolve_stock_data_mode(
        bar_count=bar_count, adjusted=adjusted, benchmark_complete=benchmark_complete,
        industry_complete=industry_complete, days_listed=days_listed,
        is_suspended=is_suspended if shortcut_mode else False,
        input_snapshot_id=input_snapshot_id,
    )
    missing = list(mode.get("missing", []))
    if shortcut_mode and is_st is not False:
        missing.append("not_st")
    passed = mode["value"]["mode"] == "full" and not missing
    return result(passed, "stock-hard-gate-v2", input_snapshot_id, missing,
                  "complete" if passed else "failed", data_mode=mode["value"]["mode"])


def _window_return(series, window):
    if len(series) <= window or series[-window - 1] == 0:
        return None
    return (series[-1] / series[-window - 1] - 1) * 100


def calculate_relative_strength(
        stock_close=None, benchmark_close=None, industry_close=None, windows=(5, 20), input_snapshot_id=None,
        stock_pct_5d=None, sector_pct_5d=None, index_pct_5d=None,
        stock_pct_20d=None, sector_pct_20d=None, index_pct_20d=None,
        benchmark_pct_5d=None, industry_pct_5d=None, benchmark_pct_20d=None, industry_pct_20d=None):
    direct_returns = {
        "stock_pct_5d": stock_pct_5d, "sector_pct_5d": sector_pct_5d, "index_pct_5d": index_pct_5d,
        "stock_pct_20d": stock_pct_20d, "sector_pct_20d": sector_pct_20d, "index_pct_20d": index_pct_20d,
        "benchmark_pct_5d": benchmark_pct_5d, "industry_pct_5d": industry_pct_5d,
        "benchmark_pct_20d": benchmark_pct_20d, "industry_pct_20d": industry_pct_20d,
    }
    value, missing = {}, []
    for window in windows:
        direct = (
            direct_returns.get(f"stock_pct_{window}d"),
            direct_returns.get(f"index_pct_{window}d") if direct_returns.get(f"index_pct_{window}d") is not None else direct_returns.get(f"benchmark_pct_{window}d"),
            direct_returns.get(f"sector_pct_{window}d") if direct_returns.get(f"sector_pct_{window}d") is not None else direct_returns.get(f"industry_pct_{window}d"),
        )
        if all(item is not None for item in direct):
            window_returns = [float(item) for item in direct]
        elif all(series is not None for series in (stock_close, benchmark_close, industry_close)):
            window_returns = [_window_return(series, window) for series in (stock_close, benchmark_close, industry_close)]
        else:
            window_returns = [None, None, None]
        if any(item is None for item in window_returns):
            missing.append(f"window_{window}")
            continue
        stock_return, benchmark_return, industry_return = window_returns
        value[str(window)] = {
            "stock_return": round(stock_return, 6),
            "vs_benchmark": round(stock_return - benchmark_return, 6),
            "vs_industry": round(stock_return - industry_return, 6),
        }
    return result(value if value else "N/A", "relative-strength-v1", input_snapshot_id, missing, "partial" if value and missing else "unavailable" if not value else "complete")


def calculate_wyckoff_features(bars, lookback=20, input_snapshot_id=None):
    if len(bars) < lookback:
        return result("N/A", "wyckoff-features-v1", input_snapshot_id, [f"bars>={lookback}"], "unavailable")
    sample = bars[-lookback:]
    highs = [float(item["high"]) for item in sample]
    lows = [float(item["low"]) for item in sample]
    closes = [float(item["close"]) for item in sample]
    volumes = [float(item["volume"]) for item in sample]
    average_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)
    high, low = max(highs), min(lows)
    value = {
        "range_high": high,
        "range_low": low,
        "range_position": None if high == low else round((closes[-1] - low) / (high - low), 6),
        "latest_volume_ratio": None if average_volume == 0 else round(volumes[-1] / average_volume, 6),
        "latest_spread": round(highs[-1] - lows[-1], 6),
    }
    return result(value, "wyckoff-features-v1", input_snapshot_id, note="只提供特征，不自动确认威科夫阶段")



def calculate_price_position(price=None, ma20=None, ma50=None, atr14=None, structure_level=None,
                             recent_5d_return=None, input_snapshot_id=None, close=None):
    if price is None:
        price = close
    if price is None:
        return result("N/A", "price-position-v1", input_snapshot_id, ["price"], "unavailable")
    missing = []
    if ma20 is None or ma20 <= 0:
        missing.append("ma20")
    if ma50 is None or ma50 <= 0:
        missing.append("ma50")
    bias_ma20 = round((price / ma20 - 1) * 100, 6) if ma20 and ma20 > 0 else None
    bias_ma50 = round((price / ma50 - 1) * 100, 6) if ma50 and ma50 > 0 else None

    distance_structure = None
    if structure_level is None:
        missing.append("structure_level")
    elif atr14 is None or atr14 <= 0:
        missing.append("atr14")
    else:
        distance_structure = round((price - structure_level) / atr14, 6)

    if bias_ma20 is None and bias_ma50 is None and distance_structure is None:
        return result("N/A", "price-position-v1", input_snapshot_id, missing, "unavailable")

    output = {
        "bias_ma20_pct": bias_ma20,
        "bias_ma50_pct": bias_ma50,
        "distance_to_structure_atr": distance_structure,
        "return_5d_pct": recent_5d_return,
    }
    status = "complete" if not missing else "partial"
    return result(output, "price-position-v1", input_snapshot_id, missing, status)


def calculate_risk_reward(entry=None, stop=None, targets=None, friction=0.0, input_snapshot_id=None,
                          current_price=None, stop_loss=None, target_conservative=None):
    if entry is None:
        entry = current_price
    if stop is None:
        stop = stop_loss
    if targets is None and target_conservative is not None:
        targets = [target_conservative]
    if entry is None or stop is None or not targets:
        return result("N/A", "risk-reward-v1", input_snapshot_id, ["entry_stop_targets"], "unavailable")
    if friction < 0:
        raise ValueError("friction 不得为负数")
    risk = float(entry) - float(stop) + float(friction)
    valid_targets = [float(target) for target in targets if target is not None and float(target) > float(entry)]
    if risk <= 0 or not valid_targets:
        return result("N/A", "risk-reward-v1", input_snapshot_id, ["positive_risk_and_target"], "unavailable")
    conservative = min(valid_targets)
    reward = conservative - float(entry) - float(friction)
    if reward <= 0:
        return result("N/A", "risk-reward-v1", input_snapshot_id, ["positive_net_reward"], "unavailable")
    return result(round(reward / risk, 6), "risk-reward-v1", input_snapshot_id, entry=entry, stop=stop, conservative_target=conservative, risk=round(risk, 6), reward=round(reward, 6))
