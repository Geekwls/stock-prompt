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


def calculate_market_sentiment_score(
        breadth_score=None, limit_score=None, ladder_score=None, blown_score=None,
        amount_score=None, shrinking_rise=False, amount_ratio=None,
        breadth_ratio=None, volume_dev=None, up_ratio=None, coverage=None, input_snapshot_id=None):
    """计算收盘五项情绪分，并对缩量上涨执行 60 分封顶。"""
    weights = {
        "breadth_score": 0.25,
        "limit_score": 0.20,
        "ladder_score": 0.20,
        "blown_score": 0.20,
        "amount_score": 0.15,
    }
    values = {
        "breadth_score": breadth_score,
        "limit_score": limit_score,
        "ladder_score": ladder_score,
        "blown_score": blown_score,
        "amount_score": amount_score,
    }
    missing = [name for name, value in values.items() if value is None]
    available = {name: value for name, value in values.items() if value is not None}
    if not available:
        return result("N/A", "market-sentiment-v1", input_snapshot_id, missing, "unavailable")
    for name, value in available.items():
        require_range(name, value)
    scored_weight = sum(weights[name] for name in available)
    effective_coverage = scored_weight * 100
    if coverage is not None:
        require_range("coverage", coverage)
        effective_coverage = min(effective_coverage, float(coverage))
    if effective_coverage < 70:
        return result("N/A", "market-sentiment-v1", input_snapshot_id,
                      missing + ["coverage>=70"], "unavailable",
                      scored_weight=round(scored_weight * 100, 2), coverage=round(effective_coverage, 2))
    score = sum(float(value) * weights[name] for name, value in available.items()) / scored_weight
    shrinking_rise = bool(shrinking_rise) or (
        amount_ratio is not None and float(amount_ratio) < 1
        and breadth_ratio is not None and float(breadth_ratio) > 50
    ) or (
        volume_dev is not None and float(volume_dev) < 0
        and up_ratio is not None and float(up_ratio) > 50
    )
    cap_applied = shrinking_rise and score > 60
    if cap_applied:
        score = 60.0
    return result(
        round(score, 4), "market-sentiment-v1", input_snapshot_id, missing,
        scored_weight=round(scored_weight * 100, 2),
        coverage=round(effective_coverage, 2),
        shrinking_rise=shrinking_rise, cap_applied=cap_applied,
    )


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
                                input_snapshot_id=None, p_up=None, p_side=None, p_down=None,
                                sentiment_score=None):
    if probabilities is None and any(value is not None for value in (p_up, p_side, p_down)):
        probabilities = {"up": p_up, "side": p_side, "down": p_down}
    if mode == "close" and probabilities is None:
        probabilities = sentiment_score
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
    if isinstance(probabilities, dict):
        for state in ("up", "side", "down"):
            if probabilities.get(state) is not None:
                require_range(f"probabilities.{state}", probabilities[state])
        up = probabilities.get("up")
        side = probabilities.get("side")
        down = probabilities.get("down")
        non_null = [v for v in (up, side, down) if v is not None]
        if len(non_null) == 2:
            val1, val2 = float(non_null[0]), float(non_null[1])
            if val1 + val2 > 100.05:
                raise ValueError("三态概率合计必须为 100")
            if down is None and up is not None and side is not None:
                probabilities = dict(probabilities)
                probabilities["down"] = round(100.0 - float(up) - float(side), 4)
            elif side is None and up is not None and down is not None:
                probabilities = dict(probabilities)
                probabilities["side"] = round(100.0 - float(up) - float(down), 4)
            elif up is None and side is not None and down is not None:
                probabilities = dict(probabilities)
                probabilities["up"] = round(100.0 - float(side) - float(down), 4)
        elif len(non_null) == 3:
            if abs(sum(float(v) for v in (up, side, down)) - 100.0) > 0.05:
                raise ValueError("三态概率合计必须为 100")

    if isinstance(probabilities, dict) and all(probabilities.get(key) is not None for key in ("up", "side", "down")):
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


def calculate_price_range(price=None, atr14=None, regular_multiplier=0.8, extreme_multiplier=1.5,
                          input_snapshot_id=None, current_price=None, ma5=None, ma20=None):
    if price is None:
        price = current_price
    if price is None:
        return result("N/A", "price-range-atr-v1", input_snapshot_id, ["price"], "unavailable")
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


def calculate_auction_traffic_light(
    index_gap=0.0,
    index_amount_ratio=1.0,
    leader_gap=0.0,
    leader_amount_ratio=1.0,
    nuclear_count=0,
    limit_up_seal_ratio=0.0,
    input_snapshot_id=None,
):
    """
    9:25 集合竞价极速红绿灯与剧本匹配纯函数。
    规则遵循 A 股开盘竞价实战盘口：
    - 红灯 (red) / 剧本 C (核按钮退潮):
      * 昨日连板核按钮 (nuclear_count >= 2) 或核心龙头惨遭重挫 (nuclear_count >= 1 且 leader_gap <= -5.0)；
      * 或指数大幅低开重挫 (index_gap <= -1.0)。
    - 绿灯 (green) / 剧本 A (超预期强攻):
      * 无核按钮 (nuclear_count == 0)；
      * 且龙头超预期抢筹 (leader_gap >= 3.0 或 limit_up_seal_ratio >= 0.05) 且竞价放量 (leader_amount_ratio >= 1.2)；
      * 且指数未大幅低开拖累 (index_gap >= -0.2)。
    - 黄灯 (yellow) / 剧本 B (平开分歧震荡):
      * 其余常态情况。
    """
    try:
        idx_gap = float(index_gap) if index_gap is not None else 0.0
        idx_amt = float(index_amount_ratio) if index_amount_ratio is not None else 1.0
        ldr_gap = float(leader_gap) if leader_gap is not None else 0.0
        ldr_amt = float(leader_amount_ratio) if leader_amount_ratio is not None else 1.0
        nuc_cnt = int(nuclear_count) if nuclear_count is not None else 0
        seal_rt = float(limit_up_seal_ratio) if limit_up_seal_ratio is not None else 0.0
    except (TypeError, ValueError):
        return result("N/A", "auction-traffic-light-v1", input_snapshot_id, ["numeric_parameters"], "unavailable")

    if nuc_cnt >= 2 or (nuc_cnt >= 1 and ldr_gap <= -5.0) or idx_gap <= -1.0:
        light = "red"
        scenario = "C"
        sentiment = "bearish"
        action = "恶性退潮确认，严禁开新仓/低吸，持仓若冲高不及预期在9:35前果断止损或减仓防守。"
    elif nuc_cnt == 0 and (ldr_gap >= 3.0 or seal_rt >= 0.05) and ldr_amt >= 1.2 and idx_gap >= -0.2:
        light = "green"
        scenario = "A"
        sentiment = "bullish"
        action = "主线超预期强开，允许打板第一身位先锋，持仓享受溢价，切勿盲目追高无承接的后排跟风。"
    else:
        light = "yellow"
        scenario = "B"
        sentiment = "neutral"
        action = "平开震荡分歧格局，等待9:45分时均线确认承接，仅在支撑位S1低吸核心，禁止半路追高。"

    value = {
        "traffic_light": light,
        "matched_scenario": scenario,
        "auction_sentiment": sentiment,
        "action_guidance": action,
        "metrics": {
            "index_gap": round(idx_gap, 2),
            "leader_gap": round(ldr_gap, 2),
            "leader_amount_ratio": round(ldr_amt, 2),
            "nuclear_count": nuc_cnt,
        },
    }
    return result(value, "auction-traffic-light-v1", input_snapshot_id)


def calculate_sentiment_opportunity_score(
    ladder_health_score=None,
    leader_premium=None,
    limit_up_count=None,
    nuclear_count=0,
    emotion_cycle="ferment",
    coverage=100.0,
    input_snapshot_id=None,
):
    """
    计算 A 股超短情绪与连板妖股机会分 (0–100)。
    独立于大盘指数，专门服务于短线打板、龙头接力与弱市妖股抱团穿越。
    """
    require_range("coverage", coverage)
    if coverage < 70:
        return result("N/A", "opportunity-sentiment-v1", input_snapshot_id, ["coverage>=70"], "unavailable", coverage=coverage)

    values = {
        "ladder_health_score": ladder_health_score,
        "leader_premium": leader_premium,
        "limit_up_count": limit_up_count,
    }
    missing = [k for k, v in values.items() if v is None]
    if missing:
        return result("N/A", "opportunity-sentiment-v1", input_snapshot_id, missing, "unavailable")

    ladder = float(ladder_health_score)
    leader = float(leader_premium)
    limit_cnt = float(limit_up_count)
    nuc_cnt = int(nuclear_count) if nuclear_count is not None else 0

    require_range("ladder_health_score", ladder)
    require_range("leader_premium", leader)

    limit_score = clamp(limit_cnt * 1.25, 0.0, 100.0)
    base_score = 0.35 * ladder + 0.35 * leader + 0.30 * limit_score

    cycle = str(emotion_cycle).lower()
    cycle_bonus = {
        "ice_breaking": 15.0,
        "ferment": 5.0,
        "climax": -5.0,
        "divergence": 0.0,
        "retreat": -25.0,
    }.get(cycle, 0.0)

    nuclear_penalty = nuc_cnt * 10.0
    final_score = clamp(base_score + cycle_bonus - nuclear_penalty, 0.0, 100.0)

    return result(
        round(final_score, 4),
        "opportunity-sentiment-v1",
        input_snapshot_id,
        ladder_health=ladder,
        leader_premium=leader,
        emotion_cycle=cycle,
        nuclear_penalty=nuclear_penalty,
    )


def assess_catalyst_exhaustion(
    catalyst_level="medium",
    yesterday_gain=0.0,
    expected_gap=0.0,
    consecutive_up_days=1,
    cumulative_gain=0.0,
    input_snapshot_id=None,
):
    """
    审计隔夜突发/重磅利好的一致性透支与利好出尽高开低走风险。
    """
    try:
        yest_gain = float(yesterday_gain) if yesterday_gain is not None else 0.0
        exp_gap = float(expected_gap) if expected_gap is not None else 0.0
        up_days = int(consecutive_up_days) if consecutive_up_days is not None else 1
        cum_gain = float(cumulative_gain) if cumulative_gain is not None else 0.0
    except (TypeError, ValueError):
        return result("N/A", "catalyst-exhaustion-v1", input_snapshot_id, ["numeric_parameters"], "unavailable")

    cat_lvl = str(catalyst_level).lower()

    is_high_exhaustion = (
        (yest_gain >= 3.5 or up_days >= 3 or cum_gain >= 10.0)
        and exp_gap >= 2.0
        and cat_lvl in ("heavy", "major", "high")
    )
    is_low_exhaustion = (
        up_days <= 1 and cum_gain < 3.0 and yest_gain < 2.0
    )

    if is_high_exhaustion:
        risk = "high"
        fade_warning = True
        fade_probability = 75.0
        advice = "利好全网发酵且前期已有显著获利盘，大幅高开极易遭遇潜伏盘兑现砸盘，严禁开盘追高，防冲高回落大阴线。"
        adjustment = {"up_likelihood_penalty": 0.4, "suggested_action": "avoid_chasing"}
    elif is_low_exhaustion:
        risk = "low"
        fade_warning = False
        fade_probability = 20.0
        advice = "利好属于底部首发催化，潜伏盘较少，支持竞价超预期或分时站稳均线后积极跟进。"
        adjustment = {"up_likelihood_bonus": 0.2, "suggested_action": "follow_opportunity"}
    else:
        risk = "medium"
        fade_warning = False
        fade_probability = 45.0
        advice = "利好存在一定预期差，但需观察开盘后5分钟分时均线承接，确认非脉冲后方可介入。"
        adjustment = {"neutral_bias": 1.0, "suggested_action": "wait_for_confirmation"}

    value = {
        "exhaustion_risk": risk,
        "fade_warning": fade_warning,
        "fade_probability": fade_probability,
        "tactical_advice": advice,
        "bayesian_adjustment": adjustment,
    }
    return result(value, "catalyst-exhaustion-v1", input_snapshot_id)


calculate_catalyst_exhaustion = assess_catalyst_exhaustion


def calculate_market_divergence_index(
    index_pct=0.0,
    breadth_ratio=50.0,
    median_pct=0.0,
    high_low_spread=0.0,
    is_fake_positive=False,
    input_snapshot_id=None,
):
    """
    量化全市场二八撕裂与假阳线诱多指数。
    - 严重二八撕裂 (extreme_polarization): 指数上涨 (index_pct >= 0.2) 但全市场红盘率极低 (breadth_ratio <= 35.0 或 median_pct <= -1.0)；
    - 假阳线诱多 (fake_positive_trap): 指数收红但日内高开低走大阴线 (is_fake_positive=True 或 high_low_spread >= 1.5)；
    - 健康普涨 (healthy_broad_rise): 指数收红且红盘率 >= 60.0% 且中位数良好 (median_pct >= 0.5)；
    - 中性分化 (neutral): 常态震荡。
    """
    try:
        idx_p = float(index_pct) if index_pct is not None else 0.0
        brd_r = float(breadth_ratio) if breadth_ratio is not None else 50.0
        med_p = float(median_pct) if median_pct is not None else 0.0
        hl_spd = float(high_low_spread) if high_low_spread is not None else 0.0
        fake_p = bool(is_fake_positive)
    except (TypeError, ValueError):
        return result("N/A", "market-divergence-v1", input_snapshot_id, ["numeric_parameters"], "unavailable")

    require_range("breadth_ratio", brd_r, 0, 100)

    polarization_base = clamp((idx_p - med_p) * 20.0, 0, 80)
    breadth_penalty = clamp((50.0 - brd_r) * 0.8, 0, 40) if brd_r < 50.0 else 0.0
    polarization_index = clamp(polarization_base + breadth_penalty, 0, 100)

    is_extreme = idx_p >= 0.2 and (brd_r <= 35.0 or med_p <= -1.0)
    is_trap = idx_p > 0 and (fake_p or hl_spd >= 1.5)

    if is_extreme:
        div_type = "extreme_polarization"
        penalty = 20.0
        advice = "大盘指数被权重中字头护盘虚拉，全市场超六成个股阴跌崩盘，呈现极端二八撕裂；触发【权重掩护出货警示】，严禁盲目参考指数点位做多，控制仓位防守。"
        cap_60 = True
    elif is_trap:
        div_type = "fake_positive_trap"
        penalty = 15.0
        advice = "指数全天高开低走收假阳大阴线，盘中冲高资金借利好兑现抛压沉重；触发【假阳线诱多警示】，防次日惯性低开杀跌。"
        cap_60 = True
    elif idx_p > 0 and brd_r >= 60.0 and med_p >= 0.5:
        div_type = "healthy_broad_rise"
        penalty = 0.0
        advice = "指数与全市场个股形成健康普涨共振，赚钱效应扩散，量价配合良好。"
        cap_60 = False
    else:
        div_type = "neutral"
        penalty = 0.0
        advice = "市场涨跌结构中性均衡，按主线板块节奏操作。"
        cap_60 = False

    value = {
        "divergence_type": div_type,
        "polarization_index": round(polarization_index, 2),
        "score_penalty": penalty,
        "cap_applied": cap_60,
        "tactical_guidance": advice,
        "metrics": {
            "index_pct": round(idx_p, 2),
            "breadth_ratio": round(brd_r, 2),
            "median_pct": round(med_p, 2),
            "is_fake_positive": fake_p,
        },
    }
    return result(value, "market-divergence-v1", input_snapshot_id)


def filter_intraday_impulse(
    current_time="10:05",
    sector_gain=2.5,
    is_above_vwap=True,
    turnover_increasing=True,
    pullback_broken=False,
    input_snapshot_id=None,
):
    """
    盘中快照模式（09:30–15:00）10:00 分水岭真伪脉冲拦截纯函数。
    - 早盘诱多陷阱 (early_morning_trap): 10:00 前冲高但在回踩时跌破分时黄线 (is_above_vwap=False 或 pullback_broken=True)；
    - 缩量脉冲废票 (volume_exhaustion): 冲高但成交量急剧萎缩，后续无大单承接 (turnover_increasing=False)；
    - 日内确认强势 (confirmed_intraday_strength): 回踩分时均线站稳不破，且放量持续换手。
    """
    try:
        time_text = str(current_time).strip()
        hour, minute = (int(part) for part in time_text.split(":", 1))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        gain = float(sector_gain) if sector_gain is not None else 0.0
        above_vwap = bool(is_above_vwap)
        increasing = bool(turnover_increasing)
        broken = bool(pullback_broken)
    except (TypeError, ValueError):
        return result("N/A", "intraday-impulse-v1", input_snapshot_id, ["current_time_HH:MM"], "unavailable")

    minutes = hour * 60 + minute
    if minutes < 10 * 60 and not (broken or not above_vwap):
        return result({
            "impulse_quality": "pre_10am_observation", "is_valid": False,
            "gate_status": "pre_threshold", "current_time": time_text,
            "tactical_guidance": "尚未到 10:00 分水岭，仅记录脉冲，不确认强弱或允许追价。",
        }, "intraday-impulse-v2", input_snapshot_id, ["10:00_threshold"], "partial")

    if broken or not above_vwap:
        quality = "early_morning_trap"
        is_valid = False
        guidance = "早盘脉冲拉升后回踩跌破分时均价线（分时黄线），确认为【诱多出货陷阱】；禁止追高，已有持仓反抽果断离场。"
    elif not increasing and gain >= 2.0:
        quality = "volume_exhaustion"
        is_valid = False
        guidance = "拉升缺乏成交量持续放大支撑，量能衰竭无承接，判定为【脉冲冲高回落废票】；等待回踩确认，严禁半路追高。"
    elif above_vwap and increasing and gain >= 1.5:
        quality = "confirmed_intraday_strength"
        is_valid = True
        guidance = "放量突破且回踩分时均线稳稳站稳，大单承接良好，确认为【日内真实强势主线】；支持沿分时均线逢低试仓。"
    else:
        quality = "neutral_observation"
        is_valid = False
        guidance = "分时结构中性，尚需观察 10:00 分水岭换手确认。"

    value = {
        "impulse_quality": quality,
        "is_valid": is_valid,
        "gate_status": "post_threshold",
        "current_time": str(current_time),
        "tactical_guidance": guidance,
        "metrics": {
            "sector_gain": round(gain, 2),
            "is_above_vwap": above_vwap,
            "turnover_increasing": increasing,
            "pullback_broken": broken,
        },
    }
    return result(value, "intraday-impulse-v2", input_snapshot_id)


def reconcile_watchlist_triggers(triggers, observations, input_snapshot_id=None):
    """按昨日触发器与 9:25 观测值逐条核销，禁止模型凭空推断状态。"""
    if not isinstance(triggers, list) or not isinstance(observations, dict):
        return result("N/A", "watchlist-reconcile-v1", input_snapshot_id, ["triggers_and_observations"], "unavailable")
    rows = []
    for index, trigger in enumerate(triggers):
        if not isinstance(trigger, dict) or not trigger.get("id"):
            rows.append({"id": f"unknown-{index + 1}", "status": "unverifiable", "reason": "invalid_trigger"})
            continue
        trigger_id = str(trigger["id"])
        observed = observations.get(trigger_id)
        row = {"id": trigger_id, "status": "unverifiable", "observed_value": None, "evidence_id": None}
        if isinstance(observed, dict):
            row["observed_value"] = observed.get("observed_value")
            row["evidence_id"] = observed.get("evidence_id")
            if observed.get("broken") is True or observed.get("status") in {"stop_loss", "破位止损"}:
                row["status"] = "stop_loss"
            elif observed.get("met") is True or observed.get("status") in {"confirmed", "达标执行"}:
                row["status"] = "confirmed"
            elif observed.get("met") is False or observed.get("status") in {"failed", "失效放弃"}:
                row["status"] = "abandoned"
        rows.append(row)
    counts = {status: sum(row["status"] == status for row in rows) for status in ("confirmed", "abandoned", "stop_loss", "unverifiable")}
    return result({"items": rows, "counts": counts, "decision": "actionable" if rows and counts["unverifiable"] == 0 else "conditional"},
                  "watchlist-reconcile-v1", input_snapshot_id, [] if rows else ["non_empty_triggers"], "complete" if rows else "unavailable")
