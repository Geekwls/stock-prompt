"""个股硬门槛、相对强度、量价特征、位置与赔率。"""

from .common import result


def validate_stock_hard_gate(bar_count, adjusted, benchmark_complete, industry_complete, input_snapshot_id=None):
    missing = []
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


def calculate_relative_strength(stock_close, benchmark_close, industry_close, windows=(5, 20), input_snapshot_id=None):
    value, missing = {}, []
    for window in windows:
        returns = [_window_return(series, window) for series in (stock_close, benchmark_close, industry_close)]
        if any(item is None for item in returns):
            missing.append(f"window_{window}")
            continue
        stock_return, benchmark_return, industry_return = returns
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


def calculate_price_position(price, ma20, ma50, atr14, structure_level, recent_5d_return=None, input_snapshot_id=None):
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


def calculate_risk_reward(entry, stop, targets, friction=0.0, input_snapshot_id=None):
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
