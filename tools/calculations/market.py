"""市场状态、概率、空间与机会函数。"""

import math

from .common import clamp, require_range, result


REGIME_PRIORS = {
    "S0": {"up": 15.0, "side": 25.0, "down": 60.0},
    "S1": {"up": 40.0, "side": 40.0, "down": 20.0},
    "S2": {"up": 30.0, "side": 50.0, "down": 20.0},
    "S3": {"up": 55.0, "side": 30.0, "down": 15.0},
    "S4": {"up": 60.0, "side": 30.0, "down": 10.0},
    "S5": {"up": 25.0, "side": 45.0, "down": 30.0},
    "S6": {"up": 10.0, "side": 25.0, "down": 65.0},
}


def calculate_atr_state(close, previous_close, atr14, input_snapshot_id=None):
    if atr14 is None or atr14 <= 0:
        return result("N/A", "atr-state-v1", input_snapshot_id, ["atr14"], "unavailable", z_atr=None)
    # 阈值属于十进制业务口径，先抑制二进制浮点在 ±0.3 边界的噪声。
    z_atr = round((float(close) - float(previous_close)) / float(atr14), 12)
    five_state = "strong_up" if z_atr > 0.8 else "up" if z_atr >= 0.3 else "side" if z_atr > -0.3 else "down" if z_atr >= -0.8 else "strong_down"
    three_state = "up" if z_atr >= 0.3 else "down" if z_atr <= -0.3 else "side"
    return result(three_state, "atr-state-v1", input_snapshot_id, z_atr=round(z_atr, 6), five_state=five_state)


def calculate_market_regime(features, input_snapshot_id=None):
    """按明确事实标志判定 Regime；不从单一情绪分猜趋势阶段。"""
    priority = (
        ("retreat", "S6"), ("panic", "S0"), ("distribution", "S5"),
        ("trend_continuation", "S4"), ("breakout", "S3"), ("recovery", "S1"),
    )
    for flag, regime in priority:
        if features.get(flag) is True:
            return result(regime, "market-regime-rules-v1", input_snapshot_id, matched_rule=flag, prior=REGIME_PRIORS[regime])
    required = ("volume_flat", "breadth_balanced", "rapid_rotation")
    if all(features.get(name) is True for name in required):
        return result("S2", "market-regime-rules-v1", input_snapshot_id, matched_rule="range_rotation", prior=REGIME_PRIORS["S2"])
    expected = [flag for flag, _ in priority] + list(required)
    missing = [name for name in expected if name not in features]
    if not missing:
        missing = ["decisive_regime_evidence"]
    return result("N/A", "market-regime-rules-v1", input_snapshot_id, missing, "unavailable")


def calculate_bayesian_posterior(prior, likelihoods, input_snapshot_id=None, strong_aligned_clusters=0):
    states = ("up", "side", "down")
    if any(state not in prior for state in states):
        return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["prior"], "unavailable")
    try:
        raw = {state: float(prior[state]) for state in states}
    except (TypeError, ValueError):
        return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["numeric_prior"], "unavailable")
    if any(value < 0 for value in raw.values()):
        return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["nonnegative_prior"], "unavailable")
    for likelihood in likelihoods:
        if any(state not in likelihood for state in states):
            return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["likelihood"], "unavailable")
        try:
            factors = {state: float(likelihood[state]) for state in states}
        except (TypeError, ValueError):
            return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["numeric_likelihood"], "unavailable")
        if any(value < 0 for value in factors.values()):
            return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["nonnegative_likelihood"], "unavailable")
        for state in states:
            raw[state] *= factors[state]
    total = sum(raw.values())
    if total <= 0:
        return result("N/A", "bayesian-posterior-v1", input_snapshot_id, ["positive_likelihood"], "unavailable")
    posterior = {state: 100.0 * raw[state] / total for state in states}
    cap = 90.0 if strong_aligned_clusters >= 3 else 80.0
    leader = max(states, key=posterior.get)
    if posterior[leader] > cap:
        overflow = posterior[leader] - cap
        others = [state for state in states if state != leader]
        other_total = sum(posterior[state] for state in others)
        posterior[leader] = cap
        for state in others:
            posterior[state] += overflow * (posterior[state] / other_total if other_total else 0.5)
    rounded = {state: round(posterior[state], 4) for state in states}
    rounded["side"] = round(100.0 - rounded["up"] - rounded["down"], 4)
    return result(rounded, "bayesian-posterior-v1", input_snapshot_id, cap=cap)


def calculate_opportunity_score(probabilities=None, space_up=None, space_down=None, mainline_quality=None,
                                capital_continuity=None, crowding=None, coverage=100.0,
                                mode="preopen", divergence_penalty=0.0, brake_flags=0,
                                input_snapshot_id=None):
    require_range("coverage", coverage)
    if coverage < 70:
        return result("N/A", f"opportunity-{mode}-v1", input_snapshot_id, ["coverage>=70"], "unavailable", coverage=coverage)
    if mode == "close":
        values = {"sentiment": probabilities, "resonance": mainline_quality, "continuity": capital_continuity}
        missing = [name for name, value in values.items() if value is None]
        if missing:
            return result("N/A", "opportunity-close-v1", input_snapshot_id, missing, "unavailable")
        for name, value in values.items():
            require_range(name, value)
        require_range("divergence_penalty", divergence_penalty, 0, 20)
        score = clamp(0.3 * probabilities + 0.4 * mainline_quality + 0.3 * capital_continuity - divergence_penalty)
        if brake_flags >= 4:
            score = min(score, 35.0)
        return result(round(score, 4), "opportunity-close-v1", input_snapshot_id, brake_applied=brake_flags >= 4)

    components = {}
    if isinstance(probabilities, dict) and all(key in probabilities for key in ("up", "side", "down")):
        for state in ("up", "side", "down"):
            require_range(f"probabilities.{state}", probabilities[state])
        if abs(sum(probabilities[state] for state in ("up", "side", "down")) - 100.0) > 0.05:
            raise ValueError("三态概率合计必须为 100")
        components["direction"] = (clamp((probabilities["up"] + 0.5 * probabilities["side"]) / 100, 0, 1), 0.30)
    if (space_up is not None and space_up < 0) or (space_down is not None and space_down < 0):
        raise ValueError("space_up 与 space_down 必须为非负距离")
    if space_up is not None and space_down is not None and space_up >= 0 and space_down >= 0 and space_up + space_down > 0:
        components["space"] = (space_up / (space_up + space_down), 0.20)
    for name, value, weight in (
        ("quality", mainline_quality, 0.25), ("continuity", capital_continuity, 0.25),
    ):
        if value is not None:
            require_range(name, value)
            components[name] = (value / 100.0, weight)
    if crowding is not None:
        require_range("crowding", crowding)
        components["crowding"] = (1.0 - 0.5 * crowding / 100.0, 0.0)
    missing = [name for name in ("direction", "space", "quality", "continuity", "crowding") if name not in components]
    weighted = [(value, weight) for name, (value, weight) in components.items() if name != "crowding"]
    weight_sum = sum(weight for _, weight in weighted)
    if not weighted or weight_sum <= 0:
        return result("N/A", "opportunity-preopen-v1", input_snapshot_id, missing, "unavailable")
    product = math.prod(max(value, 0.0) ** (weight / weight_sum) for value, weight in weighted)
    product *= components.get("crowding", (1.0, 0.0))[0]
    return result(round(100.0 * product, 4), "opportunity-preopen-v1", input_snapshot_id, missing, factors=sorted(components))


def calculate_price_range(price, atr14, regular_multiplier=0.8, extreme_multiplier=1.5, input_snapshot_id=None):
    if atr14 is None or atr14 <= 0:
        return result("N/A", "price-range-atr-v1", input_snapshot_id, ["atr14"], "unavailable")
    price, atr14 = float(price), float(atr14)
    value = {
        "r1": round(price + regular_multiplier * atr14, 6),
        "s1": round(price - regular_multiplier * atr14, 6),
        "r2": round(price + extreme_multiplier * atr14, 6),
        "s2": round(price - extreme_multiplier * atr14, 6),
    }
    return result(value, "price-range-atr-v1", input_snapshot_id)
