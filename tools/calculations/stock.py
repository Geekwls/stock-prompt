"""个股硬门槛、相对强度、量价特征、位置与赔率。"""

from .common import result


def validate_stock_hard_gate(bar_count=None, adjusted=None, benchmark_complete=None, industry_complete=None,
                             input_snapshot_id=None, is_st=None, days_listed=None,
                             kline_count=None, is_suspended=None):
    missing = []
    shortcut_mode = any(value is not None for value in (is_st, days_listed, kline_count, is_suspended))
    if bar_count is None:
        bar_count = kline_count
    if shortcut_mode:
        if is_st is True:
            missing.append("not_st")
        if days_listed is not None and days_listed < 60:
            missing.append("days_listed>=60")
        if is_suspended is True:
            missing.append("not_suspended")
        if bar_count is None or bar_count < 120:
            missing.append("adjusted_bars>=120")
        return result(not missing, "stock-hard-gate-v1", input_snapshot_id, missing,
                      "complete" if not missing else "failed")
    if bar_count is None:
        missing.append("adjusted_bars>=120")
        bar_count = 0
    if bar_count < 120:
        missing.append("adjusted_bars>=120")
    if not adjusted:
        missing.append("adjustment_method")
    if not benchmark_complete:
        missing.append("broad_market_baseline")
    if not industry_complete:
        missing.append("industry_baseline")
    return result(not missing, "stock-hard-gate-v1", input_snapshot_id, missing, "complete" if not missing else "failed")


def _window_return(series, window):
    if len(series) <= window or series[-window - 1] == 0:
        return None
    return (series[-1] / series[-window - 1] - 1) * 100


def calculate_relative_strength(stock_close=None, benchmark_close=None, industry_close=None,
                                windows=(5, 20), input_snapshot_id=None, **returns):
    value, missing = {}, []
    for window in windows:
        direct = (
            returns.get(f"stock_pct_{window}d"),
            returns.get(f"index_pct_{window}d", returns.get(f"benchmark_pct_{window}d")),
            returns.get(f"sector_pct_{window}d", returns.get(f"industry_pct_{window}d")),
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
    values = {"ma20": ma20, "ma50": ma50, "atr14": atr14, "structure_level": structure_level}
    missing = [name for name, value in values.items() if value is None or (name == "atr14" and value <= 0)]
    if missing:
        return result("N/A", "price-position-v1", input_snapshot_id, missing, "unavailable")
    output = {
        "bias_ma20_pct": round((price / ma20 - 1) * 100, 6),
        "bias_ma50_pct": round((price / ma50 - 1) * 100, 6),
        "distance_to_structure_atr": round((price - structure_level) / atr14, 6),
        "return_5d_pct": recent_5d_return,
    }
    return result(output, "price-position-v1", input_snapshot_id)


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
