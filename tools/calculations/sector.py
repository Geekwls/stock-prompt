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


def _ratio(value, name):
    """接受 0–1 比例或 0–100 百分比，统一为 0–1。"""
    if value is None:
        return None
    require_range(name, value, 0, 100)
    return float(value) / 100.0 if value > 1 else float(value)


def calculate_sector_exhaustion(price_volume_divergence=None, relay_risk=None, capital_spillover=None,
                                input_snapshot_id=None, price_divergence=None, capital_overflow=None,
                                new_high_shrink_days=None, divergence_ratio=None,
                                relay_failed_ratio=None, break_rate=None,
                                sector_turnover_share=None, low_position_spillover=None,
                                auto_derive=False):
    """计算主线衰竭指数；支持旧版直接打分与原始指标客观推导两种模式。

    客观模式的三个子项均为确定性公式：量价背离 = 缩量创新高天数/5×20 + 顶背离占比×20；
    接力风险 = 断板率×15 + 炸板率×15；资金溢出 = 成交占比相对 12% 拥挤阈值×20 +
    (1-低位扩散占比)×10。直接传入的子项优先于推导值，保证旧调用完全兼容。
    """
    if price_volume_divergence is None:
        price_volume_divergence = price_divergence
    if capital_spillover is None:
        capital_spillover = capital_overflow
    derived = {}
    if price_volume_divergence is None and (auto_derive or new_high_shrink_days is not None or divergence_ratio is not None):
        if new_high_shrink_days is not None:
            if isinstance(new_high_shrink_days, bool) or not isinstance(new_high_shrink_days, (int, float)) or new_high_shrink_days < 0:
                raise ValueError("new_high_shrink_days 必须为非负数")
            shrink_score = clamp(float(new_high_shrink_days) / 5.0 * 20.0, 0, 20)
        else:
            shrink_score = None
        ratio = _ratio(divergence_ratio, "divergence_ratio")
        divergence_score = ratio * 20.0 if ratio is not None else None
        if shrink_score is not None or divergence_score is not None:
            price_volume_divergence = (shrink_score or 0) + (divergence_score or 0)
            derived["price_volume_divergence"] = round(price_volume_divergence, 4)
    if relay_risk is None and (auto_derive or relay_failed_ratio is not None or break_rate is not None):
        failed = _ratio(relay_failed_ratio, "relay_failed_ratio")
        broken = _ratio(break_rate, "break_rate")
        if failed is not None or broken is not None:
            relay_risk = (failed or 0) * 15.0 + (broken or 0) * 15.0
            derived["relay_risk"] = round(relay_risk, 4)
    if capital_spillover is None and (auto_derive or sector_turnover_share is not None or low_position_spillover is not None):
        turnover = _ratio(sector_turnover_share, "sector_turnover_share")
        low_position = _ratio(low_position_spillover, "low_position_spillover")
        if turnover is not None or low_position is not None:
            congestion_score = clamp((turnover or 0) / 0.12 * 20.0, 0, 20)
            diffusion_risk = (1 - low_position) * 10.0 if low_position is not None else 0
            capital_spillover = congestion_score + diffusion_risk
            derived["capital_spillover"] = round(capital_spillover, 4)
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
    return result(round(score, 4), "sector-exhaustion-v2" if derived else "sector-exhaustion-v1", input_snapshot_id, state=state,
                  derivation="objective" if derived else "direct", derived_components=derived)


def calculate_ladder_health(ladder_distribution, input_snapshot_id=None):
    """计算连板梯队完整度、断层层数与孤桩龙头风险。"""
    if not isinstance(ladder_distribution, dict) or not ladder_distribution:
        return result("N/A", "ladder-health-v1", input_snapshot_id, ["ladder_distribution"], "unavailable")
    distribution = {}
    for raw_level, raw_count in ladder_distribution.items():
        try:
            level = int(raw_level)
        except (TypeError, ValueError) as exc:
            raise ValueError("ladder_distribution 层级必须为正整数") from exc
        if level < 1 or isinstance(raw_count, bool) or not isinstance(raw_count, (int, float)) or raw_count < 0 or int(raw_count) != raw_count:
            raise ValueError("ladder_distribution 层级必须为正整数，数量必须为非负整数")
        distribution[level] = int(raw_count)
    occupied = sorted(level for level, count in distribution.items() if count > 0)
    if not occupied:
        return result("N/A", "ladder-health-v1", input_snapshot_id, ["occupied_ladder"], "unavailable")
    max_height = max(occupied)
    if len(occupied) == 1:
        max_gap = max_height - 1 if max_height >= 4 else 0
    else:
        max_gap = max(
            upper - lower - 1
            for lower, upper in zip(occupied, occupied[1:])
        )
    occupied_levels = sum(1 for level in range(1, max_height + 1) if distribution.get(level, 0) > 0)
    coverage_score = occupied_levels / max_height * 100.0
    continuity_score = (1 - max_gap / max(1, max_height - 1)) * 100.0
    ladder_score = clamp(0.6 * continuity_score + 0.4 * coverage_score)
    severe = max_height >= 4 and max_gap >= 2
    warning_level = "severe_fault" if severe else "mild_gap" if max_gap == 1 else "healthy"
    risk_flag = (
        "isolated_leader_risk: 孤桩龙头，警惕断板A杀与板块踩踏" if severe else
        "ladder_gap_risk: 梯队存在单层断档，降低接力预期" if warning_level == "mild_gap" else None
    )
    payload = {
        "max_height": max_height,
        "fault_gap": max_gap,
        "ladder_score": round(ladder_score, 4),
        "warning_level": warning_level,
        "risk_flag": risk_flag,
        "occupied_levels": occupied_levels,
    }
    return result(payload, "ladder-health-v1", input_snapshot_id,
                  warning_level=warning_level, fault_gap=max_gap, ladder_score=round(ladder_score, 4),
                  risk_flag=risk_flag)


def calculate_sector_cannibalization(leader_sector_turnover_share=None, market_amount_ratio=None,
                                     outflow_sectors_loss_rate=None, input_snapshot_id=None,
                                     outflow_sectors=None, flow_to_leader=None):
    """量化存量吸血、增量共生、电风扇轮动与普跌退潮，并输出失血板块。"""
    values = {
        "leader_sector_turnover_share": leader_sector_turnover_share,
        "market_amount_ratio": market_amount_ratio,
        "outflow_sectors_loss_rate": outflow_sectors_loss_rate,
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        return result("N/A", "sector-cannibalization-v1", input_snapshot_id, missing, "unavailable")
    require_range("leader_sector_turnover_share", leader_sector_turnover_share, 0, 100)
    require_range("market_amount_ratio", market_amount_ratio, 0, 10)
    require_range("outflow_sectors_loss_rate", outflow_sectors_loss_rate, 0, 100)
    leader_share = float(leader_sector_turnover_share)
    amount_ratio = float(market_amount_ratio)
    loss_rate = float(outflow_sectors_loss_rate)
    share_score = clamp(leader_share / 12.0 * 50.0, 0, 50)
    contraction_score = clamp((1.05 - amount_ratio) / 0.25 * 30.0, 0, 30)
    loss_score = clamp(loss_rate / 3.0 * 20.0, 0, 20)
    siphon_index = round(share_score + contraction_score + loss_score, 4)
    if amount_ratio <= 1.05 and leader_share >= 8 and loss_rate > 1.5:
        market_dynamic = "siphon_extreme"
    elif amount_ratio > 1.05 and loss_rate <= 1.5:
        market_dynamic = "balanced_growth"
    elif amount_ratio <= 1.05 and leader_share < 8 and loss_rate <= 1.5:
        market_dynamic = "diffuse_rotation"
    elif loss_rate >= 2.0 and amount_ratio < 1.0:
        market_dynamic = "broad_retreat"
    else:
        market_dynamic = "diffuse_rotation"
    affected = []
    redirected = None
    if isinstance(outflow_sectors, list):
        ranked = [item for item in outflow_sectors if isinstance(item, dict)]
        ranked.sort(key=lambda item: (float(item.get("loss_rate", 0) or 0), float(item.get("net_outflow", 0) or 0)), reverse=True)
        affected = [str(item.get("name") or item.get("id") or "N/A") for item in ranked[:3]]
        total_outflow = sum(max(0.0, float(item.get("net_outflow", 0) or 0)) for item in ranked)
        redirected_amount = sum(max(0.0, float(item.get("flow_to_leader", 0) or 0)) for item in ranked)
        if total_outflow > 0:
            redirected = round(min(1.0, redirected_amount / total_outflow) * 100, 4)
    if flow_to_leader is not None:
        require_range("flow_to_leader", flow_to_leader, 0, 100)
        redirected = float(flow_to_leader)
    if market_dynamic == "siphon_extreme" and not affected:
        affected = [f"流出排名前三板块（平均跌幅 {loss_rate:.2f}%）"]
    payload = {
        "siphon_index": siphon_index,
        "market_dynamic": market_dynamic,
        "affected_sectors": affected,
        "redirected_flow_ratio": redirected,
        "leader_sector_turnover_share": leader_share,
        "market_amount_ratio": amount_ratio,
        "outflow_sectors_loss_rate": loss_rate,
    }
    return result(payload, "sector-cannibalization-v1", input_snapshot_id,
                  siphon_index=siphon_index, market_dynamic=market_dynamic,
                  affected_sectors=affected, redirected_flow_ratio=redirected)


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

