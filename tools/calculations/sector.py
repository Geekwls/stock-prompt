"""板块资金延续、衰竭、轮动、排名和生命周期。"""

from .common import clamp, require_range, result


def calculate_5d_sentiment_score(daily_scores, weights=None, input_snapshot_id=None):
    if weights is None:
        weights = [0.05, 0.05, 0.20, 0.30, 0.40]
    if not isinstance(daily_scores, (list, tuple)) or not isinstance(weights, (list, tuple)):
        raise ValueError("daily_scores 与 weights 必须为数组")
    if len(daily_scores) != 5 or len(weights) != 5:
        raise ValueError("daily_scores 与 weights 必须各含 5 个按 T-4 至 T 排列的元素")
    if any(isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1 for weight in weights):
        raise ValueError("weights 每项必须在 0–1 之间")
    if abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("weights 合计必须为 1")
    available = []
    missing = []
    for index, (score, weight) in enumerate(zip(daily_scores, weights)):
        if score is None:
            missing.append(f"day_{index + 1}")
            continue
        require_range(f"daily_scores[{index}]", score)
        available.append((float(score), float(weight)))
    available_weight = sum(weight for _, weight in available)
    if len(available) < 3 or available_weight < 0.70:
        gates = []
        if len(available) < 3:
            gates.append("available_days>=3")
        if available_weight < 0.70:
            gates.append("scored_weight>=70%")
        return result("N/A", "sentiment-5d-v1", input_snapshot_id,
                      missing + gates, "unavailable",
                      available_days=len(available), scored_weight=round(available_weight * 100, 2))
    weight_sum = available_weight
    score = sum(score * weight for score, weight in available) / weight_sum
    return result(round(score, 4), "sentiment-5d-v1", input_snapshot_id, missing,
                  available_days=len(available), scored_weight=round(weight_sum * 100, 2))


def calculate_capital_continuity(amount_ratio=None, break_rate=None, trigger_count=None, auction_adjustment=0,
                                 input_snapshot_id=None, turnover_ratio=None, blown_ratio=None):
    if amount_ratio is None:
        amount_ratio = turnover_ratio
    if break_rate is None:
        break_rate = blown_ratio
    missing = []
    volume = clamp(amount_ratio, 0, 1) * 100 if amount_ratio is not None else None
    quality = None
    if break_rate is not None and (trigger_count is None or trigger_count >= 3):
        if 1 < break_rate <= 100:
            break_rate = break_rate / 100.0
        require_range("break_rate", break_rate, 0, 1)
        quality = (1 - break_rate) * 100
    else:
        missing.append("sector_break_rate_sample>=3")
    if volume is None:
        missing.append("amount_ratio")
    if volume is None and quality is None:
        return result("N/A", "capital-continuity-v1", input_snapshot_id, missing, "unavailable")
    if volume is None:
        score = quality
    elif quality is None:
        score = volume
    else:
        score = 0.6 * volume + 0.4 * quality
    score = clamp(score + auction_adjustment, 0, 95 if auction_adjustment > 0 else 100)
    return result(round(score, 4), "capital-continuity-v1", input_snapshot_id, missing, volume_score=volume, quality_score=quality)


def calculate_sector_exhaustion(price_volume_divergence=None, relay_risk=None, capital_spillover=None,
                                input_snapshot_id=None, price_divergence=None, capital_overflow=None):
    if price_volume_divergence is None:
        price_volume_divergence = price_divergence
    if capital_spillover is None:
        capital_spillover = capital_overflow
    values = {
        "price_volume_divergence": price_volume_divergence,
        "relay_risk": relay_risk,
        "capital_spillover": capital_spillover,
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        return result("N/A", "sector-exhaustion-v1", input_snapshot_id, missing, "unavailable")
    require_range("price_volume_divergence", price_volume_divergence, 0, 40)
    require_range("relay_risk", relay_risk, 0, 30)
    require_range("capital_spillover", capital_spillover, 0, 30)
    score = price_volume_divergence + relay_risk + capital_spillover
    state = "healthy" if score <= 30 else "divergence" if score <= 60 else "exhausted" if score <= 80 else "retreat"
    return result(round(score, 4), "sector-exhaustion-v1", input_snapshot_id, state=state)


def calculate_rotation_state(core_share=None, positive_days=None, limit_up_count=None, defensive_flow=False,
                             high_level_selloff=False, input_snapshot_id=None):
    if limit_up_count is not None and limit_up_count < 20 and high_level_selloff:
        state, rule = "state_4", "ice_point"
    elif defensive_flow and high_level_selloff:
        state, rule = "state_3", "defensive_rotation"
    elif high_level_selloff:
        state, rule = "state_2", "high_to_low"
    elif core_share is not None and positive_days is not None and core_share >= 8 and positive_days >= 3:
        state, rule = "state_1", "mainline_advance"
    else:
        return result("N/A", "rotation-state-rules-v1", input_snapshot_id, ["decisive_rotation_evidence"], "unavailable")
    return result(state, "rotation-state-rules-v1", input_snapshot_id, matched_rule=rule)


def calculate_sector_ranking(sectors, weights=None, input_snapshot_id=None):
    weights = weights or {"strength": 0.35, "flow": 0.30, "breadth": 0.20, "continuity": 0.15}
    if not sectors:
        return result([], "sector-ranking-v1", input_snapshot_id, ["sectors"], "unavailable")
    ranked = []
    for item in sectors:
        available = [(name, value, weights[name]) for name, value in item.items() if name in weights and value is not None]
        if not available:
            ranked.append({"id": item.get("id", "N/A"), "score": None, "missing": sorted(weights)})
            continue
        for name, value, _ in available:
            require_range(name, value)
        total_weight = sum(weight for _, _, weight in available)
        score = sum(value * weight for _, value, weight in available) / total_weight
        ranked.append({"id": item.get("id", "N/A"), "score": round(score, 4), "missing": sorted(set(weights) - {name for name, _, _ in available})})
    ranked.sort(key=lambda item: (-1 if item["score"] is None else -item["score"], str(item["id"])))
    return result(ranked, "sector-ranking-v1", input_snapshot_id)


def calculate_lifecycle_state(current_state, capital_continuity=None, accepted=False, acceleration=False,
                              distribution=False, retreat=False, new_catalyst=False, input_snapshot_id=None):
    if retreat:
        next_state, rule = "退潮期", "retreat"
    elif current_state == "弱化期" and new_catalyst:
        next_state, rule = "启动期", "restart"
    elif current_state == "高位分歧" and accepted:
        next_state, rule = "强化期", "reacceptance"
    elif distribution:
        next_state, rule = "高位分歧", "distribution"
    elif acceleration:
        next_state, rule = "加速期", "acceleration"
    elif current_state == "启动期" and accepted and (capital_continuity or 0) >= 80:
        next_state, rule = "强化期", "confirmation"
    else:
        next_state, rule = current_state, "hold"
    return result(next_state, "lifecycle-rules-v1", input_snapshot_id, transition_rule=rule)

