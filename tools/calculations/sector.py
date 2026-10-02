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
    if any(weights[index] > weights[index + 1] for index in range(len(weights) - 1)):
        raise ValueError(
            "weights 必须按 T-4 至 T 非递减排列（近期权重不得低于远期权重），"
            "否则会得出「远期主导」的反向结论；请检查权重顺序"
        )
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
        break_rate = _ratio(break_rate, "break_rate")
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
    """接受 0–1 比例或带 % 字符串，统一归一化为 0–1。

    支持：
    - 字符串百分比（如 '1%', '12%', '0.5%', '100%'），无歧义解析；
    - 0–1 标准小数比例（如 0.01 表示 1%，0.4 表示 40%）；
    - > 1 的百分比数值（如 1.5 表示 1.5%，12 表示 12%，100 表示 100%）。
    若恰好传入未带单位的裸数值 1 或 1.0，存在 1% 与 100% 的 100 倍严重比例歧义，
    系统拒绝隐式猜测并抛出 ValueError，强制显式指定。
    """
    if value is None:
        return None
    if isinstance(value, str):
        val_str = value.strip()
        if val_str.endswith("%"):
            try:
                num = float(val_str[:-1].strip())
            except ValueError as exc:
                raise ValueError(f"{name} 必须为合法的百分比或数值") from exc
            require_range(name, num, 0, 100)
            return num / 100.0
        try:
            value = float(val_str)
        except ValueError as exc:
            raise ValueError(f"{name} 必须为合法的百分比或数值") from exc
    require_range(name, value, 0, 100)
    num = float(value)
    if num == 1.0:
        raise ValueError(
            f"{name} 传入了数值 1（或 1.0），存在 1% 与 100% 的 100 倍比例歧义。"
            f"若表示 1% 请传 0.01 或 '1%'；若表示 100% 请传 100 或 '100%'"
        )
    return num / 100.0 if num > 1.0 else num


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
                  derivation="objective" if derived else "direct", derived_components=derived,
                  components={
                      "price_volume_divergence": round(price_volume_divergence, 4),
                      "relay_risk": round(relay_risk, 4),
                      "capital_spillover": round(capital_spillover, 4),
                  },
                  calibration_status="uncalibrated",
                  calibration_note="子项权重 (40/30/30) 与分档阈值 (30/60/80) 为经验设定，未经历史样本校准；"
                                   "请结合 eval_tracker 主线状态台账累积 >=30 日后复核，报告不得将其表述为已验证阈值。")


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
    """量化存量吸血、增量共生、主线聚焦、电风扇轮动与普跌退潮，并输出失血板块。

    分类按语义严重度自上而下判定（互斥且有序，修复历史误判与死分支）：
    - broad_retreat         普跌退潮：失血严重 (loss_rate >= 2.0)、缩量且无强主线承接 (leader_share < 8)；
    - siphon_extreme        存量吸血极化：缩量 + 强主线 + 明显失血；
    - concentrated_mainline 缩量主线聚焦：缩量 + 强主线 + 失血轻微（最健康形态）；
    - balanced_growth       增量共生：量能放大且无明显失血；
    - diffuse_rotation      电风扇扩散：缩量、无强主线且无明显失血；
    - transitional          过渡分歧：其余组合（如放量但明显失血）。
    """
    values = {
        "leader_sector_turnover_share": leader_sector_turnover_share,
        "market_amount_ratio": market_amount_ratio,
        "outflow_sectors_loss_rate": outflow_sectors_loss_rate,
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        return result("N/A", "sector-cannibalization-v2", input_snapshot_id, missing, "unavailable")
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
    if loss_rate >= 2.0 and leader_share < 8.0 and amount_ratio < 1.0:
        market_dynamic = "broad_retreat"
    elif amount_ratio <= 1.05 and leader_share >= 8.0 and loss_rate > 1.5:
        market_dynamic = "siphon_extreme"
    elif amount_ratio <= 1.05 and leader_share >= 8.0:
        market_dynamic = "concentrated_mainline"
    elif amount_ratio > 1.05 and loss_rate <= 1.5:
        market_dynamic = "balanced_growth"
    elif amount_ratio <= 1.05 and loss_rate <= 1.5:
        market_dynamic = "diffuse_rotation"
    else:
        market_dynamic = "transitional"
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
    return result(payload, "sector-cannibalization-v2", input_snapshot_id,
                  siphon_index=siphon_index, market_dynamic=market_dynamic,
                  affected_sectors=affected, redirected_flow_ratio=redirected)


def calculate_rotation_state(core_share=None, positive_days=None, limit_up_count=None, defensive_flow=False,
                             high_level_selloff=False, low_position_inflow=None, input_snapshot_id=None):
    """按 4 状态转移规则判定资金轮动状态。

    - state_1 主线主升：核心板块成交占比 >= 8% 且连续 >= 3 日阳线；
    - state_2 畏高切低/补涨：高位股杀跌但资金未转向防御；
    - state_3 避险防御：高位杀跌且资金流向防御红利；
    - state_4 冰点衰退：涨停 < 20 家且高位股杀跌。

    `low_position_inflow`（可选布尔）用于补足 state_2 缺失的证据：历史实现仅凭
    `high_level_selloff` 即判定「畏高切低」，无法区分「切低成功」与「切低失败后直接退潮」。
    传入 True 记为 confirmed、False 记为 failed、缺省为 unverified。
    该字段只补充证据状态，不改变 state 枚举，保证既有消费方兼容。
    """
    if limit_up_count is not None and limit_up_count < 20 and high_level_selloff:
        state, rule = "state_4", "ice_point"
    elif defensive_flow and high_level_selloff:
        state, rule = "state_3", "defensive_rotation"
    elif high_level_selloff:
        state, rule = "state_2", "high_to_low"
    elif core_share is not None and positive_days is not None and core_share >= 8 and positive_days >= 3:
        state, rule = "state_1", "mainline_advance"
    else:
        return result("N/A", "rotation-state-rules-v2", input_snapshot_id, ["decisive_rotation_evidence"], "unavailable")
    high_to_low_status = None
    if state == "state_2":
        if low_position_inflow is None:
            high_to_low_status = "unverified"
        else:
            high_to_low_status = "confirmed" if bool(low_position_inflow) else "failed"
    return result(state, "rotation-state-rules-v2", input_snapshot_id, matched_rule=rule,
                  high_to_low_status=high_to_low_status)


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
    ranked.sort(key=lambda item: (item["score"] is None, -(item["score"] or 0.0), str(item["id"])))
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


def assess_rotation_effectiveness(
    active_sectors_count=None,
    leader_turnover_share=None,
    limit_up_clusters=None,
    market_amount_ratio=None,
    input_snapshot_id=None,
):
    """
    量化评估日内板块轮动是有效的主线聚焦行情，还是容易套人的电风扇一日游行情。
    规则遵循 A 股存量博弈盘口：
    - 电风扇无效轮动 (electric_fan):
      * 活跃异动板块过多 (active_sectors_count >= 4) 且领涨板块成交占比偏低 (leader_turnover_share < 6.0)；
      * 或领涨板块涨停家数孤木难支 (limit_up_clusters <= 2) 且成交额占比不足 6.0 且两市量能未放大；
      * 输出 is_effective=False，提示严禁追高日内脉冲。
    - 主线聚焦有效轮动 (mainline_focused):
      * 领涨板块成交占比高 (leader_turnover_share >= 8.0) 且涨停梯队完整 (limit_up_clusters >= 3)；
      * 或成交占比 >= 10.0 且涨停梯队 >= 2；
      * 输出 is_effective=True，支持做主线分歧低吸与接力。
    - 过渡分歧态 (transitional):
      * 其余中性态。

    重要：本函数**不设乐观默认值**。任一输入缺失即返回 N/A 并列出 missing。
    历史版本曾为四个参数设置偏乐观的默认值（1 / 8.0 / 3 / 1.0），恰好落在
    mainline_focused 判定区间内，导致漏传参时静默输出「主线聚焦 / 有效 / 低风险」
    的假阳性结论；现已移除，缺失输入一律返回 unavailable。
    """
    raw = {
        "active_sectors_count": active_sectors_count,
        "leader_turnover_share": leader_turnover_share,
        "limit_up_clusters": limit_up_clusters,
        "market_amount_ratio": market_amount_ratio,
    }
    missing = [name for name, value in raw.items() if value is None]
    if missing:
        return result("N/A", "rotation-effectiveness-v2", input_snapshot_id, missing, "unavailable")
    try:
        sec_cnt = int(active_sectors_count)
        ldr_share = float(leader_turnover_share)
        lim_cnt = int(limit_up_clusters)
        mkt_ratio = float(market_amount_ratio)
    except (TypeError, ValueError):
        return result("N/A", "rotation-effectiveness-v2", input_snapshot_id, ["numeric_parameters"], "unavailable")

    require_range("active_sectors_count", sec_cnt, 0, 100)
    require_range("leader_turnover_share", ldr_share, 0, 100)
    require_range("limit_up_clusters", lim_cnt, 0, 1000)
    require_range("market_amount_ratio", mkt_ratio, 0, 10)

    is_fan = (sec_cnt >= 4 and ldr_share < 6.0) or (lim_cnt <= 2 and ldr_share < 6.0 and mkt_ratio < 1.05)
    is_mainline = (ldr_share >= 8.0 and lim_cnt >= 3) or (ldr_share >= 10.0 and lim_cnt >= 2)

    if is_fan:
        rot_type = "electric_fan"
        is_eff = False
        advice = "当前日内板块无序轮动，成交量能分散，缺乏具有容量与梯队的核心主线，追高次日被套概率极高；触发【无效轮动防诱多预警】，实操策略：管住手，严禁追逐盘中脉冲。"
        risk = "high"
    elif is_mainline:
        rot_type = "mainline_focused"
        is_eff = True
        advice = "核心主线成交额占比与梯队效应达标，资金聚焦度高，具备板块持续性，支持围绕核心主线分歧回踩低吸或打板前排先锋。"
        risk = "low"
    else:
        rot_type = "transitional"
        is_eff = True
        advice = "轮动处于中性过渡阶段，需密切关注领涨板块次日开盘 9:25 是否具备金额比溢价与承接持续性。"
        risk = "medium"

    value = {
        "rotation_type": rot_type,
        "is_effective": is_eff,
        "risk_level": risk,
        "tactical_guidance": advice,
        "metrics": {
            "active_sectors_count": sec_cnt,
            "leader_turnover_share": round(ldr_share, 2),
            "limit_up_clusters": lim_cnt,
            "market_amount_ratio": round(mkt_ratio, 2),
        },
    }
    return result(value, "rotation-effectiveness-v2", input_snapshot_id)


def calculate_leader_core_divergence(
    core_trend="above_ma20",
    core_net_flow=0.0,
    leader_state="limit_up",
    leader_height=3,
    inner_up_ratio=50.0,
    input_snapshot_id=None,
):
    """
    审计板块内部‘百亿容量中军’与‘高标连板龙头’的分化与背离风险。
    - 中军背离出货 (core_desertion): 中军跌破均线 (break_ma5 / break_ma20) 且资金流出，而龙头依旧涨停硬顶 -> 警示主力造势诱多出货；
    - 龙头溃退反弹 (leader_collapse): 龙头已跌停 A 杀，后排或杂毛小票冲高 -> 警示假补涨掩护出逃；
    - 健康共振 (healthy_resonance): 中军均线上方且资金流入，龙头连板开拓高度，内部上涨占比 > 60%。
    """
    c_trend = str(core_trend).lower()
    l_state = str(leader_state).lower()
    try:
        c_flow = float(core_net_flow) if core_net_flow is not None else 0.0
        l_height = int(leader_height) if leader_height is not None else 1
        up_ratio = float(inner_up_ratio) if inner_up_ratio is not None else 50.0
    except (TypeError, ValueError):
        return result("N/A", "leader-core-divergence-v1", input_snapshot_id, ["numeric_parameters"], "unavailable")

    require_range("inner_up_ratio", up_ratio, 0, 100)

    is_core_desertion = ("break" in c_trend or c_flow < -5.0) and ("limit_up" in l_state or l_height >= 3) and up_ratio < 45.0
    is_leader_collapse = ("limit_down" in l_state or "collapsed" in l_state) and up_ratio > 30.0

    if is_core_desertion:
        div_type = "core_desertion"
        risk_lvl = "severe_divergence"
        advice = "百亿中军破位走弱且资金净流出，仅剩小盘龙头硬顶连板，主线已进入【假繁荣出货尾声】；严禁以‘龙头未倒’为由加仓中军或后排跟风，谨防突发天地板通杀。"
    elif is_leader_collapse:
        div_type = "leader_collapse"
        risk_lvl = "high_risk"
        advice = "第一核心龙头已出现跌停 A 杀恶性负反馈，低位个股拉板仅为掩护出货的弱抽血，持续性极差，禁止追入任何所谓补涨标的。"
    elif ("above" in c_trend or c_flow >= 0) and ("limit_up" in l_state or l_height >= 2) and up_ratio >= 55.0:
        div_type = "healthy_resonance"
        risk_lvl = "healthy"
        advice = "中军大容量与先锋龙头形成良性量价共振，板块内部涨多跌少，梯队健康，支持中线持股或分歧加仓。"
    else:
        div_type = "neutral_divergence"
        risk_lvl = "normal"
        advice = "板块内部中军与龙头表现分歧中性，需观察明日开盘中军能否重回 5 日均线。"

    value = {
        "divergence_type": div_type,
        "risk_level": risk_lvl,
        "tactical_advice": advice,
        "metrics": {
            "core_trend": c_trend,
            "core_net_flow": c_flow,
            "leader_state": l_state,
            "leader_height": l_height,
            "inner_up_ratio": round(up_ratio, 2),
        },
    }
    return result(value, "leader-core-divergence-v1", input_snapshot_id)


def resolve_rotation_timeframe(
    catalyst_scope="macro_trend",
    duration_days=5,
    trend_ma20_slope="up",
    input_snapshot_id=None,
):
    """
    识别板块的实际行情生命周期级别，破除固定 5 日机械尺度的周期错配：
    - 超短脉冲 (short_term, 1–3日)：突发短命消息，次日开盘 9:35 决断，破开盘价坚决离场；
    - 题材波段 (swing_rotation, 5–10日)：行业政策或周期性催化，依托 5 日/10 日均线滚动操作；
    - 季度趋势主线 (major_trend, 20–60日)：产业革命与宏观大逻辑，缩量回踩 20 日线属黄金加仓点，不以单周资金流出误判为衰竭。
    """
    scope = str(catalyst_scope).lower()
    slope = str(trend_ma20_slope).lower()
    try:
        days = int(duration_days) if duration_days is not None else 5
    except (TypeError, ValueError):
        return result("N/A", "rotation-timeframe-v1", input_snapshot_id, ["numeric_parameters"], "unavailable")

    if scope in ("macro_trend", "industry_revolution", "major") and (days >= 15 or slope == "up"):
        cycle_lvl = "major_trend"
        cycle_name = "季度趋势大主线 (20–60日)"
        defense = "依托 10 日与 20 日均线防守，日内与周度正常分歧不轻易下车，回踩缩量企稳为加仓买点。"
    elif scope in ("pulsed", "event_pulsed", "news_flash", "rumor") or days <= 3:
        cycle_lvl = "short_term"
        cycle_name = "超短脉冲题材 (1–3日)"
        defense = "严禁恋战与格局，次日开盘 9:35 确认强弱，不及预期或破分时均线坚决离场。"
    else:
        cycle_lvl = "swing_rotation"
        cycle_name = "题材轮动波段 (5–10日)"
        defense = "依托 5 日均线防守，高位滞涨出现 SEI 衰竭时果断止盈切出。"

    value = {
        "cycle_level": cycle_lvl,
        "cycle_name": cycle_name,
        "duration_days": days,
        "appropriate_defense_line": defense,
    }
    return result(value, "rotation-timeframe-v1", input_snapshot_id)


REFERENCE_MARKET_AMOUNT_YI = 10000.0
MEGA_AMOUNT_YI = 350.0
STANDARD_AMOUNT_YI = 180.0


def validate_sector_capacity(
    sector_amount_yi=None,
    market_total_amount_yi=None,
    market_amount_baseline_yi=None,
    input_snapshot_id=None,
):
    """
    判定板块资金容量，杜绝小微题材伪装主线。
    - sector_amount_yi: 板块日成交额(亿元)
    - market_total_amount_yi: 两市总成交额(亿元)
    - market_amount_baseline_yi: 可选，两市成交额基准（如近 20 日成交额中位数，亿元）。
      提供后按 baseline / 10000 同比缩放绝对额门槛，避免固定 350/180 亿阈值在放量市
      失去区分度；未提供时按固定参考基准计算，并在输出中标注 threshold_basis。

    判定规则（修复历史 OR 后门）：
    - mega_mainline 需**同时**满足「份额达标 (>=4%)」与「绝对容量达标 (>= 标准额门槛)」，
      杜绝「放量市里 1.75% 份额靠 350 亿绝对值混入超级主线」；
    - standard_mainline 只需份额或绝对额之一达标；
    - 其余为 micro_niche。
    """
    raw = {"sector_amount_yi": sector_amount_yi, "market_total_amount_yi": market_total_amount_yi}
    missing = [name for name, value in raw.items() if value is None]
    if missing:
        return result("N/A", "sector-capacity-v2", input_snapshot_id, missing, "unavailable")
    try:
        sec_amt = float(sector_amount_yi)
        mkt_amt = max(float(market_total_amount_yi), 1.0)
    except (TypeError, ValueError):
        return result("N/A", "sector-capacity-v2", input_snapshot_id, ["numeric_parameters"], "unavailable")

    if market_amount_baseline_yi is None:
        threshold_scale = 1.0
        threshold_basis = "fixed_reference_10000yi"
    else:
        try:
            baseline = float(market_amount_baseline_yi)
        except (TypeError, ValueError):
            return result("N/A", "sector-capacity-v2", input_snapshot_id, ["market_amount_baseline_yi"], "unavailable")
        if baseline <= 0:
            return result("N/A", "sector-capacity-v2", input_snapshot_id, ["market_amount_baseline_yi"], "unavailable")
        threshold_scale = baseline / REFERENCE_MARKET_AMOUNT_YI
        threshold_basis = f"normalized_to_baseline_{round(baseline, 2)}yi"

    mega_amount_threshold = MEGA_AMOUNT_YI * threshold_scale
    standard_amount_threshold = STANDARD_AMOUNT_YI * threshold_scale
    amount_share = (sec_amt / mkt_amt) * 100.0

    share_mega = amount_share >= 4.0
    share_standard = amount_share >= 2.0
    amount_mega = sec_amt >= mega_amount_threshold
    amount_standard = sec_amt >= standard_amount_threshold

    if share_mega and amount_standard:
        capacity_type = "mega_mainline"
        tradable_scale = "超级大容量主线，支持百亿中军趋势重仓配置与机构大资金进出"
        is_mainline = True
    elif share_standard or amount_standard:
        capacity_type = "standard_mainline"
        tradable_scale = "标准主力题材，支持龙头接力与容量中军波段配置"
        is_mainline = True
    else:
        capacity_type = "micro_niche"
        tradable_scale = "小微游击题材，日成交额严重不足，无法容纳中大资金，仅适宜轻仓快进快出，严禁配置中军趋势仓位"
        is_mainline = False

    value = {
        "capacity_type": capacity_type,
        "amount_share_pct": round(amount_share, 2),
        "sector_amount_yi": round(sec_amt, 2),
        "market_total_amount_yi": round(mkt_amt, 2),
        "tradable_scale": tradable_scale,
        "is_mainline_eligible": is_mainline,
        "mega_amount_threshold_yi": round(mega_amount_threshold, 2),
        "standard_amount_threshold_yi": round(standard_amount_threshold, 2),
        "amount_mega_by_absolute": amount_mega,
        "threshold_basis": threshold_basis,
    }
    return result(value, "sector-capacity-v2", input_snapshot_id)


def map_capital_seesaw_matrix(
    current_mainline="",
    current_lifecycle="divergence",
    counterpart_change_pct=None,
    counterpart_net_flow_yi=None,
    input_snapshot_id=None,
):
    """
    A 股存量博弈资金跷跷板（Seesaw Effect）对立外溢矩阵。
    当主线分歧退潮时，推演最可能的对立防御或补涨承接板块。

    边界说明：本矩阵是**基于关键词的规则推演，不是证据**。默认只输出「最可能」的
    对流承接板块，报告侧不得表述为已发生事实。仅当显式传入对手板块当日实际表现
    （`counterpart_change_pct` / `counterpart_net_flow_yi`）时，才标记
    `evidence_status=verified` 并附实测证据；否则标记 `unverified_rule_only`。
    `matched_keywords` 用于披露本次命中的关键词，便于审计映射是否合理。
    """
    mainline_str = str(current_mainline).lower()
    lifecycle = str(current_lifecycle).lower()

    # 经典资金跷跷板对立映射
    seesaw_rules = [
        # 科技成长 vs 避险防御红利
        (
            ("科技", "ai", "算力", "半导体", "通信", "cpo", "芯片", "软件"),
            {
                "counterpart_name": "红利防御与高股息 (银行/煤炭/公用事业/石油)",
                "logic": "成长科技高位分歧杀跌，避险资金往往涌入低估值高股息与大金融板块抱团防守避风。",
                "alternative": "超跌新能源或医药低位超跌反弹",
            },
        ),
        # 顺周期资源 vs 新能源成长
        (
            ("资源", "有色", "黄金", "铜", "化工", "钢铁", "煤炭", "稀土"),
            {
                "counterpart_name": "新能源与高端制造 (光伏/储能/锂电/风电/电池)",
                "logic": "大宗商品与周期资源分歧休整时，往往激发中游制造与新能源赛道成长股的估值修复。",
                "alternative": "科技算力或大金融护盘",
            },
        ),
        # 新能源 vs 顺周期/科技
        (
            ("光伏", "锂电", "电池", "储能", "新能源"),
            {
                "counterpart_name": "顺周期资源或科技成长 (AI/半导体)",
                "logic": "赛道成长内部资金轮动，易在新能源与硬科技/周期资源间形成跷跷板效应。",
                "alternative": "大消费或大金融防守",
            },
        ),
        # 微盘妖股题材 vs 核心资产中字头权重
        (
            ("微盘", "超短", "重组", "壳资源", "低价", "妖股"),
            {
                "counterpart_name": "中字头与沪深300大盘蓝筹 (核心资产/央国企/白酒)",
                "logic": "超短高标退潮天地板多发时，监管与机构资金主导拉升大盘权重中字头稳定指数，风格发生剧烈大小盘高低切换。",
                "alternative": "红利防御避险",
            },
        ),
        # 大金融 (证券/保险) 强行拉升
        (
            ("证券", "券商", "保险", "大金融"),
            {
                "counterpart_name": "题材失血预警 (全市场中小创题材易遭遇抽血分歧)",
                "logic": "证券大阳线拉升常伴随巨大吸血效应，中小创题材往往逆势回落，须防冲高回落踩踏。",
                "alternative": "次日题材回血修复",
            },
        ),
    ]

    matched_pair = None
    matched_keywords = []
    for keywords, config in seesaw_rules:
        hits = [keyword for keyword in keywords if keyword in mainline_str]
        if hits:
            matched_pair = config
            matched_keywords = hits
            break

    if not matched_pair:
        matched_pair = {
            "counterpart_name": "红利高股息防御或大盘中字头蓝筹",
            "logic": "当前主线出现分歧，资金外溢通常流向低估值防御属性板块或全市场低位滞涨板块。",
            "alternative": "次日全市场无序电风扇轮动",
        }
        matched_keywords = []

    is_active_outflow = lifecycle in ("divergence", "exhausted", "retreat", "declining", "fade")
    tactical_instruction = (
        f"主线正处【{lifecycle}】阶段，资金外溢效应强烈，次日重点盯防向【{matched_pair['counterpart_name']}】的对流承接，切忌死守退潮高位股！"
        if is_active_outflow
        else f"主线当前处健康主升阶段，资金虹吸聚集，对立板块暂时承压，保持聚焦核心主线龙头。"
    )

    if counterpart_change_pct is None and counterpart_net_flow_yi is None:
        evidence_status = "unverified_rule_only"
        counterpart_evidence = None
    else:
        evidence_status = "verified"
        counterpart_evidence = {
            "change_pct": counterpart_change_pct,
            "net_flow_yi": counterpart_net_flow_yi,
        }

    value = {
        "current_mainline": str(current_mainline),
        "lifecycle_state": lifecycle,
        "is_active_outflow": is_active_outflow,
        "seesaw_counterpart": matched_pair["counterpart_name"],
        "rotation_logic": matched_pair["logic"],
        "secondary_target": matched_pair["alternative"],
        "tactical_instruction": tactical_instruction,
        "matched_keywords": matched_keywords,
        "evidence_status": evidence_status,
        "counterpart_evidence": counterpart_evidence,
        "evidence_note": (
            "对手板块表现已核验，可作为外溢承接的实测依据。"
            if evidence_status == "verified"
            else "尚未核验对手板块当日表现，本结论仅为规则推演，报告不得表述为已发生事实。"
        ),
    }
    return result(value, "capital-seesaw-matrix-v2", input_snapshot_id)


def calculate_rotation_migration(daily_rankings=None, top_n=5, input_snapshot_id=None):
    """构建板块资金净流入排名的逐日迁移矩阵，区分「持续流入」与「单日爆量」。

    历史缺口：`get_sector_fund_flow` 只返回区间累计净额排名，无法回答「这几天是持续
    流入还是某一天一次性爆量」。本函数接收逐日排名序列，输出可审计的迁移矩阵。

    - daily_rankings: 按 T-4 至 T 排列的数组，每项为该日净流入排行（高到低）；
      元素可为板块名字符串，或 {"name": ...} 对象；缺失日传 null。
      要求至少 3 个非空日，与 5 日轮动的覆盖率门槛一致。
    - top_n: 定义「进入前列」的名次门槛，默认 5。

    输出：
    - migration_matrix: 每个板块的逐日名次（缺失日为 null）；
    - persistence_ratio: 板块进入前 top_n 的天数 / 有效观测天数；
    - sustained_sectors: 持续度 >= 0.6 的板块（真正的资金主线）；
    - one_day_spike_sectors: 持续度 <= 0.2 却出现在最新一日前 top_n 的板块（疑似单日脉冲）；
    - entrants_vs_first_day / exits_vs_first_day: 相对首个观测日的新进入 / 掉出名单。
    """
    if not isinstance(daily_rankings, (list, tuple)):
        return result("N/A", "rotation-migration-v1", input_snapshot_id, ["daily_rankings"], "unavailable")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        return result("N/A", "rotation-migration-v1", input_snapshot_id, ["top_n"], "unavailable")

    normalized = []
    for index, day in enumerate(daily_rankings):
        if day is None:
            normalized.append([])
            continue
        if not isinstance(day, (list, tuple)):
            raise ValueError(f"daily_rankings[{index}] 必须为数组或 null")
        names = []
        for item in day:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id")
                if name is None:
                    raise ValueError(f"daily_rankings[{index}] 对象元素必须包含 name 或 id")
                names.append(str(name))
            else:
                raise ValueError(f"daily_rankings[{index}] 元素必须为字符串或对象")
        normalized.append(names)

    observed_days = [day for day in normalized if day]
    if len(observed_days) < 3:
        return result("N/A", "rotation-migration-v1", input_snapshot_id,
                      ["observed_days>=3"], "unavailable",
                      days_observed=len(observed_days))

    migration_matrix = {}
    for day_index, names in enumerate(normalized):
        for position, name in enumerate(names, start=1):
            migration_matrix.setdefault(name, [None] * len(normalized))[day_index] = position

    top_n_sets = [set(day[:top_n]) for day in normalized if day]
    first_entry = top_n_sets[0]
    last_entry = top_n_sets[-1]

    persistence_ratio = {}
    for name, ranks in migration_matrix.items():
        in_top = sum(1 for rank in ranks if rank is not None and rank <= top_n)
        persistence_ratio[name] = round(in_top / len(observed_days), 4)

    sustained_sectors = sorted(
        (name for name, ratio in persistence_ratio.items() if ratio >= 0.6),
        key=lambda name: (-persistence_ratio[name], name),
    )
    one_day_spike_sectors = sorted(
        (name for name, ratio in persistence_ratio.items() if ratio <= 0.2 and name in last_entry),
        key=lambda name: (persistence_ratio[name], name),
    )

    value = {
        "days_observed": len(observed_days),
        "top_n": top_n,
        "migration_matrix": migration_matrix,
        "persistence_ratio": persistence_ratio,
        "sustained_sectors": sustained_sectors,
        "one_day_spike_sectors": one_day_spike_sectors,
        "entrants_vs_first_day": sorted(last_entry - first_entry),
        "exits_vs_first_day": sorted(first_entry - last_entry),
    }
    return result(value, "rotation-migration-v1", input_snapshot_id)


EXHAUSTION_BANDS = (
    (0, 30, "动能充沛", ("启动期", "强化期"), "动能充沛，可持有核心仓位并等待分歧低吸。"),
    (31, 60, "良性分歧", ("强化期", "加速期", "高位分歧"), "良性分歧，降低追高频率，以均线防守滚动操作。"),
    (61, 80, "严重衰竭", ("高位分歧", "弱化期", "退潮期"), "动能严重衰竭，高低切已确立，逢反弹减仓。"),
    (81, 100, "全面退潮", ("退潮期",), "全面退潮踩踏，仓位清零，严禁接飞刀。"),
)


def map_exhaustion_to_lifecycle(sei=None, lifecycle_state=None, input_snapshot_id=None):
    """把主线衰竭指数 (SEI) 分档与板块生命周期对齐，消除两套体系的口径冲突。

    历史缺口：SEI 分档（0-30/31-60/61-80/81-100）与生命周期（启动/强化/加速/分歧/退潮）
    是两套独立体系，报告可能同时出现「SEI=55 良性分歧」与「高位分歧」，自相矛盾。

    - 传入 sei：返回所属分档、该分档允许的生命周期集合与战法提示；
    - 传入 lifecycle_state：返回该生命周期可能对应的 SEI 分档集合；
    - 同时传入：额外输出 consistent 一致性校验，不一致时给出 conflict_note。
    """
    if sei is None and lifecycle_state is None:
        return result("N/A", "exhaustion-lifecycle-map-v1", input_snapshot_id,
                      ["sei_or_lifecycle_state"], "unavailable")

    lifecycle = str(lifecycle_state) if lifecycle_state is not None else None
    band_info = None
    if sei is not None:
        require_range("sei", sei, 0, 100)
        for lower, upper, label, allowed, guidance in EXHAUSTION_BANDS:
            if lower <= float(sei) <= upper:
                band_info = {
                    "band": f"{lower}-{upper}",
                    "band_label": label,
                    "allowed_lifecycles": list(allowed),
                    "guidance": guidance,
                }
                break

    if band_info is None:
        candidate_bands = [
            {"band": f"{lower}-{upper}", "band_label": label}
            for lower, upper, label, _allowed, _guidance in EXHAUSTION_BANDS
            if lifecycle in _allowed
        ]
        return result({
            "lifecycle_state": lifecycle,
            "candidate_sei_bands": candidate_bands,
        }, "exhaustion-lifecycle-map-v1", input_snapshot_id)

    consistent = None
    if lifecycle is not None:
        consistent = lifecycle in band_info["allowed_lifecycles"]
    payload = {
        "sei": round(float(sei), 2),
        "lifecycle_state": lifecycle,
        "band": band_info["band"],
        "band_label": band_info["band_label"],
        "allowed_lifecycles": band_info["allowed_lifecycles"],
        "consistent": consistent,
        "guidance": band_info["guidance"],
    }
    if consistent is False:
        payload["conflict_note"] = (
            f"SEI {round(float(sei), 2)} 属于「{band_info['band_label']}」档，"
            f"与生命周期「{lifecycle}」不自洽；报告需披露该冲突并以证据更充分的一方为准。"
        )
    return result(payload, "exhaustion-lifecycle-map-v1", input_snapshot_id)



