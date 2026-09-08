#!/usr/bin/env python3
"""
MarketGraph Financial MCP Server (Zero-Config, Protocol 1.0 Ready)
==================================================================
跨智能体通用 A 股金融数据 MCP 服务端 (Agent Plugins 1.0 标准)
- 零注册、免 Token、零第三方重依赖 (基于 Python 3.8+ 标准库)
- 主干直连腾讯证券 CDN (毫秒级实时盘口、估值、750日前复权K线、指数日K与ATR)
- 短线直连东方财富打板网关 (涨停池、连板天梯、炸板池与真实炸板率)
- 支持标准 JSON-RPC 2.0 stdio 协议 (兼容 Cursor / VS Code / Gemini / Claude)
"""

import sys
import json
import time
import math
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketgraph_mcp.cache import (
    CACHE_STORE, CACHE_TTL_SECONDS, HISTORICAL_CACHE_TTL_SECONDS,
    get_cached, set_cached, ttl_for_history,
)
from marketgraph_mcp.symbols import (
    INDEX_ALIASES, INDEX_NAME_TO_KEY, normalize_date_str, normalize_symbol,
    resolve_index_keys, resolve_symbol_by_name,
)
from marketgraph_mcp.schemas import AVAILABLE_TOOLS
from marketgraph_mcp.transport import (
    ALLOWED_HTTP_HOSTS, BREAKER_COOLDOWN_SECONDS, BREAKER_FAILURE_THRESHOLD,
    HOST_MIN_INTERVAL_SECONDS, MAX_HTTP_RESPONSE_BYTES, USER_AGENT,
    _HOST_FAILURE_STATE, _HOST_LAST_REQUEST, _breaker_check,
    _breaker_record_failure, _breaker_record_success, _throttle_host, http_get,
)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# -----------------------------------------------------------------------------
# 1. 基础配置与轻量内存缓存 (TTL Cache，防止频繁请求)
# -----------------------------------------------------------------------------
def safe_float(val: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if val is None or str(val).strip() == "":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


# -----------------------------------------------------------------------------
# 2. 核心量化数据抓取与指标引擎 (腾讯证券 + 东方财富公开网关)
# -----------------------------------------------------------------------------
def fetch_stock_quote(symbol: str) -> Dict[str, Any]:
    """获取个股实时行情与估值指标"""
    ts_code = normalize_symbol(symbol)
    cache_key = f"quote_{ts_code}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = f"https://qt.gtimg.cn/q={ts_code}"
    try:
        raw = http_get(url)
    except Exception as exc:
        return {"error": f"行情上游不可用: {type(exc).__name__}", "data_status": "unavailable"}
    if "~" not in raw:
        return {"error": f"未找到证券代码数据: {symbol}"}

    parts = raw.split("=")[1].strip('";\n').split("~")
    if len(parts) < 40:
        return {"error": f"行情数据格式不完整: {symbol}"}

    try:
        current_price = safe_float(parts[3], 0.0)
        yesterday_close = safe_float(parts[4], 0.0)
        open_price = safe_float(parts[5], 0.0)
        high_price = safe_float(parts[33], current_price) if len(parts) > 33 else current_price
        low_price = safe_float(parts[34], current_price) if len(parts) > 34 else current_price
        change_pct = safe_float(parts[32], 0.0) if len(parts) > 32 else 0.0
        turnover_rate = safe_float(parts[38], 0.0) if len(parts) > 38 else 0.0
        pe_ttm = safe_float(parts[39], None) if len(parts) > 39 else None
        pb = safe_float(parts[46], None) if len(parts) > 46 else None
        total_market_cap = safe_float(parts[45], None) if len(parts) > 45 else None  # 亿元
        float_market_cap = safe_float(parts[44], None) if len(parts) > 44 else None  # 亿元
        volume_hand = safe_float(parts[6], 0.0)  # 手
        turnover_amount = safe_float(parts[37], 0.0) if len(parts) > 37 else 0.0  # 万元
        amplitude = safe_float(parts[43], 0.0) if len(parts) > 43 else 0.0

        res = {
            "source": "P3_Tencent_Public_Gateway",
            "data_status": "ok",
            "symbol": symbol,
            "ts_code": ts_code,
            "name": parts[1] if len(parts) > 1 else symbol,
            "price": current_price,
            "change_pct": f"{change_pct:+.2f}%",
            "open": open_price,
            "close": current_price,
            "high": high_price,
            "low": low_price,
            "prev_close": yesterday_close,
            "turnover_rate": f"{turnover_rate:.2f}%",
            "amplitude": f"{amplitude:.2f}%",
            "volume_hand": volume_hand,
            "turnover_cny_wan": turnover_amount,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "total_market_cap_billion": total_market_cap,
            "float_market_cap_billion": float_market_cap,
            "as_of": parts[30] if len(parts) > 30 and len(parts[30]) >= 8 else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        set_cached(cache_key, res)
        return res
    except Exception as e:
        return {"error": f"解析个股行情出错: {str(e)}"}


def fetch_index_daily_bars(ts_code: str, count: int) -> List[Dict[str, Any]]:
    """
    拉取指数日K原始序列 (多取1根用于计算首日涨跌幅)
    指数无复权概念，腾讯网关对指数代码返回 day 键 (个股才是 qfqday)
    """
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={ts_code},day,,,{count + 1},qfq"
    raw = http_get(url)
    data = json.loads(raw)
    root = data.get("data", {}).get(ts_code, {})
    bars_raw = root.get("day") or []
    bars = []
    for row in bars_raw[-(count + 1):]:
        if len(row) >= 6:
            bars.append({
                "date": str(row[0]),
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5]),
            })
    return bars


def fetch_index_kline(indices: Optional[List[str]] = None, count: int = 5) -> Dict[str, Any]:
    """
    获取核心指数 (上证指数/深证成指/创业板指/中证全指/沪深300) 最近 N 个交易日的收盘与逐日涨跌幅
    直供 sector-rotation 全窗口指数强弱判别、daily-review 大盘定调与 stock-analysis L4 宽基基准
    (count 支持 130, 覆盖 L4 的 120 日相对强度窗口),
    弥补个股K线网关无法解析指数代码 (000001 会被解析为平安银行) 的确定性缺口
    """
    if not isinstance(count, int) or not 2 <= count <= 130:
        return {"error": "count 必须是 2 至 130 的整数", "data_status": "unavailable"}
    keys = resolve_index_keys(indices)
    if not keys:
        return {"error": "未识别到有效指数 (支持 SHCI/SZCI/CYB/CSIALL/HS300 或中文别名)", "data_status": "unavailable"}

    result: Dict[str, Any] = {}
    failures: List[str] = []
    for key in keys:
        ts_code, name = INDEX_ALIASES[key]
        cache_key = f"index_kline_{ts_code}_{count}"
        cached = get_cached(cache_key)
        if cached:
            result[key] = cached
            continue
        try:
            bars = fetch_index_daily_bars(ts_code, count)
            if len(bars) < 2:
                raise ValueError("K线根数不足")
            days = []
            for i in range(1, len(bars)):
                prev_close = bars[i - 1]["close"]
                cur = bars[i]
                if prev_close <= 0:
                    continue
                days.append({
                    "date": cur["date"],
                    "close": cur["close"],
                    "change_pct": f"{((cur['close'] - prev_close) / prev_close * 100):+.2f}%",
                })
            if not days:
                raise ValueError("涨跌幅序列为空")

            # 指数技术指标: ATR14 (Z_ATR 判档)、均线体系与 20 日高低 (空间点位候补)
            closes_full = [b["close"] for b in bars]
            highs_full = [b["high"] for b in bars]
            lows_full = [b["low"] for b in bars]
            n_bars = len(bars)
            atr14 = None
            if n_bars >= 15:
                trs = []
                for i in range(n_bars - 14, n_bars):
                    prev_close = closes_full[i - 1]
                    trs.append(max(highs_full[i] - lows_full[i], abs(highs_full[i] - prev_close), abs(lows_full[i] - prev_close)))
                atr14 = round(sum(trs) / 14.0, 2)
            latest_close = closes_full[-1]

            def index_ma(window: int) -> Optional[float]:
                return round(sum(closes_full[-window:]) / window, 2) if n_bars >= window else None

            payload = {
                "name": name,
                "ts_code": ts_code,
                "days": days[-count:],
                "latest_close": latest_close,
                "atr14": atr14,
                "atr14_pct": f"{(atr14 / latest_close * 100):.2f}%" if atr14 and latest_close > 0 else None,
                "ma5": index_ma(5),
                "ma20": index_ma(20),
                "ma60": index_ma(60),
                "high_20d": max(highs_full[-min(20, n_bars):]),
                "low_20d": min(lows_full[-min(20, n_bars):]),
            }
            set_cached(cache_key, payload, ttl=600)
            result[key] = payload
        except Exception:
            failures.append(name)

    if not result:
        return {
            "source": "P3_Tencent_Index_Kline",
            "data_status": "unavailable",
            "error": f"指数日K全部获取失败: {', '.join(failures) or '未知'}",
        }
    res = {
        "source": "P3_Tencent_Index_Kline",
        "data_status": "ok" if not failures else "partial",
        "indices": result,
        "summary": "；".join(
            f"{v['name']} 最新 {v['days'][-1]['date']} {v['days'][-1]['change_pct']}"
            for v in result.values()
        ),
    }
    if failures:
        res["unavailable_indices"] = failures
    return res


def aggregate_daily_to_weekly(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    在内存中将前复权日K线无损聚合成周K线（0ms网络开销），计算周线均线系统与多周期共振趋势
    """
    if not bars:
        return {"data_status": "insufficient_data"}

    from collections import OrderedDict
    weeks_dict = OrderedDict()

    for bar in bars:
        date_str = bar.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            iso_year, iso_week, _ = dt.isocalendar()
            key = (iso_year, iso_week)
        except Exception:
            key = date_str[:7]

        if key not in weeks_dict:
            weeks_dict[key] = []
        weeks_dict[key].append(bar)

    weekly_bars = []
    for key, day_list in weeks_dict.items():
        w_open = day_list[0]["open"]
        w_close = day_list[-1]["close"]
        w_high = max(d["high"] for d in day_list)
        w_low = min(d["low"] for d in day_list)
        w_vol = sum(d["volume"] for d in day_list)
        w_date = day_list[-1]["date"]
        weekly_bars.append({
            "date": w_date,
            "open": round(w_open, 2),
            "close": round(w_close, 2),
            "high": round(w_high, 2),
            "low": round(w_low, 2),
            "volume": round(w_vol, 2),
        })

    num_weeks = len(weekly_bars)
    if num_weeks == 0:
        return {"data_status": "insufficient_data"}

    w_closes = [wb["close"] for wb in weekly_bars]
    latest_w_close = w_closes[-1]

    # 周均线: MA10 (约50日线，中期波段趋势) / MA30 (约150日线，大级别牛熊分水岭)
    weekly_ma10 = round(sum(w_closes[-10:]) / 10.0, 2) if num_weeks >= 10 else None
    weekly_ma30 = round(sum(w_closes[-30:]) / 30.0, 2) if num_weeks >= 30 else None

    # 周线趋势状态判定
    if weekly_ma10 and weekly_ma30:
        if latest_w_close >= weekly_ma10 and weekly_ma10 >= weekly_ma30:
            weekly_alignment = "BULLISH_UPTREND"  # 周线多头排列，主升大趋势
        elif latest_w_close <= weekly_ma10 and weekly_ma10 <= weekly_ma30:
            weekly_alignment = "BEARISH_DOWNTREND"  # 周线空头排列，下行大趋势
        elif latest_w_close >= weekly_ma10 and weekly_ma10 < weekly_ma30:
            weekly_alignment = "REBOUND_TESTING_RESISTANCE"  # 周线超跌反弹，测试长期均线阻力
        else:
            weekly_alignment = "CONSOLIDATION"  # 周线震荡整理
    else:
        weekly_alignment = "NEUTRAL"

    # 周线高低区间 (近52周 / 约1年)
    w52_high = max([wb["high"] for wb in weekly_bars[-min(52, num_weeks):]])
    w52_low = min([wb["low"] for wb in weekly_bars[-min(52, num_weeks):]])

    return {
        "total_weeks": num_weeks,
        "latest_week_date": weekly_bars[-1]["date"],
        "latest_week_close": latest_w_close,
        "weekly_ma10": weekly_ma10,
        "weekly_ma30": weekly_ma30,
        "weekly_alignment": weekly_alignment,
        "bias_weekly_ma10": f"{((latest_w_close - weekly_ma10) / weekly_ma10 * 100):+.2f}%" if weekly_ma10 else "N/A",
        "bias_weekly_ma30": f"{((latest_w_close - weekly_ma30) / weekly_ma30 * 100):+.2f}%" if weekly_ma30 else "N/A",
        "high_52_weeks": w52_high,
        "low_52_weeks": w52_low,
        "summary": f"周线共振: 覆盖 {num_weeks} 周; 趋势定调: {weekly_alignment}; MA10: {weekly_ma10}, MA30: {weekly_ma30}",
    }


def compute_wyckoff_signals(
    bars: List[Dict[str, Any]],
    ma20: float,
    ma50: float,
    ma120: Optional[float],
    ma250: Optional[float],
    ma500: Optional[float],
    atr14: float,
    latest_close: float,
    bias_ma20: float,
    high_year: float,
    low_year: float,
    high_3y: float,
    low_3y: float,
    weekly_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """预计算三层威科夫时空模型（3年宏观大周期 + 周线共振大势 + 60日微观交易区间与量价触发），消除大模型数值对比幻觉"""
    valid_count = len(bars)
    if valid_count < 20:
        return {"data_status": "insufficient_bars"}

    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]

    vol_ma20 = sum(volumes[-20:]) / 20.0
    latest_vol = volumes[-1]
    latest_high = highs[-1]
    latest_low = lows[-1]
    bar_range = latest_high - latest_low if latest_high > latest_low else 0.01

    # 1. 宏观威科夫大周期定调 (Macro Wyckoff Phase, 结合 3年大时空坐标与 MA250/MA500)
    range_3y = high_3y - low_3y if high_3y > low_3y else 1.0
    percentile_3y = round((latest_close - low_3y) / range_3y * 100, 1)

    year_range = high_year - low_year if high_year > low_year else 1.0
    year_percentile = round((latest_close - low_year) / year_range * 100, 1)

    bias_ma250 = round((latest_close - ma250) / ma250 * 100, 2) if ma250 else None
    bias_ma120 = round((latest_close - ma120) / ma120 * 100, 2) if ma120 else None
    bias_ma500 = round((latest_close - ma500) / ma500 * 100, 2) if ma500 else None

    if ma250 and ma500:
        if latest_close >= ma250 and ma250 >= ma500 * 0.98 and percentile_3y >= 50.0:
            macro_phase = "STAGE_2_MACRO_MARKUP_BULLISH"  # 站稳年线与两年线之上，3年大级别牛市主升
        elif latest_close <= ma250 and ma250 <= ma500 * 1.02 and percentile_3y <= 40.0:
            if percentile_3y <= 20.0:
                macro_phase = "STAGE_1_MACRO_ACCUMULATION"  # 3年历史大底部吸筹区 (铁底沉淀蓄势)
            else:
                macro_phase = "STAGE_4_MACRO_MARKDOWN_BEARISH"  # 3年大级别空头阴跌通道 (年线/两年线强压)
        elif percentile_3y <= 25.0:
            macro_phase = "STAGE_1_MACRO_ACCUMULATION"  # 3年周期极度低估与大吸筹区
        elif percentile_3y >= 85.0:
            macro_phase = "STAGE_3_MACRO_DISTRIBUTION"  # 3年高位筹码派发区 (天花板筑顶风险)
        else:
            macro_phase = "STAGE_REACCUMULATION_OR_CONSOLIDATION"  # 3年中继箱体震荡整理
    elif ma250:
        if latest_close >= ma250 and year_percentile >= 50.0:
            macro_phase = "STAGE_2_MARKUP_BULLISH"
        elif latest_close <= ma250 and year_percentile <= 40.0:
            macro_phase = "STAGE_1_MACRO_ACCUMULATION" if percentile_3y <= 25.0 else "STAGE_4_MARKDOWN_BEARISH"
        elif percentile_3y <= 25.0:
            macro_phase = "STAGE_1_MACRO_ACCUMULATION"
        elif percentile_3y >= 80.0:
            macro_phase = "STAGE_3_MACRO_DISTRIBUTION"
        else:
            macro_phase = "STAGE_REACCUMULATION_OR_CONSOLIDATION"
    else:
        macro_phase = "STAGE_1_MACRO_ACCUMULATION" if percentile_3y <= 30.0 else "STAGE_2_MARKUP_BULLISH"

    # 2. 中微观局部交易区间 (Trading Range, 观察近 60 日震荡箱体)
    tr_window = min(60, valid_count)
    tr_high = max(highs[-tr_window:])
    tr_low = min(lows[-tr_window:])
    tr_span = tr_high - tr_low if tr_high > tr_low else 1.0
    tr_position_pct = round((latest_close - tr_low) / tr_span * 100, 1)

    if tr_position_pct <= 20.0:
        tr_location = "AT_SUPPORT_ICE"  # 紧贴近 60 日支撑冰线
    elif tr_position_pct >= 80.0:
        tr_location = "AT_RESISTANCE_CREEK"  # 紧贴近 60 日阻力跨溪线
    else:
        tr_location = "MID_RANGE"  # 处于交易区间中轴震荡

    # 3. 量价微观触发 (Spring / UT / 地量 / 放量)
    volume_dry_up = latest_vol < (vol_ma20 * 0.60)  # 地量：低于20日均量60%
    volume_expansion = latest_vol > (vol_ma20 * 1.80)  # 放量：高于20日均量1.8倍
    vol_ratio_to_ma20 = round(latest_vol / vol_ma20, 2) if vol_ma20 > 0 else 1.0

    min_prev_10_low = min(lows[-11:-1]) if len(lows) >= 11 else min(lows)
    lower_shadow = min(latest_close, bars[-1]["open"]) - latest_low
    spring_detected = bool(
        (latest_low < min_prev_10_low)
        and (lower_shadow / bar_range >= 0.50)
        and (latest_close > latest_low + bar_range * 0.40)
    )

    max_prev_10_high = max(highs[-11:-1]) if len(highs) >= 11 else max(highs)
    upper_shadow = latest_high - max(latest_close, bars[-1]["open"])
    upthrust_detected = bool(
        (latest_high >= max_prev_10_high)
        and (upper_shadow / bar_range >= 0.50)
        and (latest_close < latest_high - bar_range * 0.40)
    )

    recent_10_high = max(highs[-10:])
    recent_10_low = min(lows[-10:])
    range_10 = recent_10_high - recent_10_low
    absorption_detected = bool((range_10 <= 3.0 * atr14) and (latest_close >= ma20 * 0.97))

    # 4. 均线乖离状态
    if bias_ma20 > 12.0:
        bias_status = "OVERHEAT_OVERBOUGHT"  # 严重正乖离过热
    elif bias_ma20 < -12.0:
        bias_status = "DEEP_OVERSOLD"  # 严重负乖离超跌
    else:
        bias_status = "NORMAL_RANGE"

    weekly_summary_str = weekly_info.get("summary", "") if weekly_info else ""

    return {
        "macro_wyckoff_phase": macro_phase,
        "percentile_3y": f"{percentile_3y}%",
        "year_price_percentile": f"{year_percentile}%",
        "bias_ma500": f"{bias_ma500:+.2f}%" if bias_ma500 is not None else "N/A",
        "bias_ma250": f"{bias_ma250:+.2f}%" if bias_ma250 is not None else "N/A",
        "bias_ma120": f"{bias_ma120:+.2f}%" if bias_ma120 is not None else "N/A",
        "trading_range_60d": {
            "tr_high": tr_high,
            "tr_low": tr_low,
            "tr_position": f"{tr_position_pct}%",
            "tr_location": tr_location,
        },
        "micro_signals": {
            "volume_dry_up": volume_dry_up,
            "volume_expansion": volume_expansion,
            "vol_ratio_to_ma20": vol_ratio_to_ma20,
            "spring_detected": spring_detected,
            "upthrust_detected": upthrust_detected,
            "absorption_detected": absorption_detected,
            "bias_status": bias_status,
        },
        "summary": (
            f"宏观阶段: {macro_phase} (3年分位: {percentile_3y}%, 1年分位: {year_percentile}%, 年线乖离: {bias_ma250 if bias_ma250 is not None else 'N/A'}%, 两年线乖离: {bias_ma500 if bias_ma500 is not None else 'N/A'}%); "
            f"60日箱体: {tr_location} ({tr_position_pct}%位置); "
            f"量能: {'地量萎缩' if volume_dry_up else ('放量异动' if volume_expansion else '量能平稳')}({vol_ratio_to_ma20}x MA20); "
            f"形态: {'[Spring测试]' if spring_detected else ''}{'[UT假突破风险]' if upthrust_detected else ''}{'[筹码紧凑吸收]' if absorption_detected else ''}{'无异常形态' if not (spring_detected or upthrust_detected or absorption_detected) else ''}"
            + (f"; {weekly_summary_str}" if weekly_summary_str else "")
        ),
    }


def fetch_stock_kline(symbol: str, count: int = 750, compact: bool = True) -> Dict[str, Any]:
    """
    获取 750 日 (约3年) 前复权日K线、全套均线矩阵 (MA20/50/120/250/500)、3年宏观时空坐标、内存周线共振与双层威科夫模型
    默认开启 compact=True 瘦身模式（保留3年宏观全景指标、周线共振趋势与最近30日微观K线），直接完美满足行情硬门槛
    """
    ts_code = normalize_symbol(symbol)
    cache_key = f"kline_{ts_code}_{count}_{compact}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    if not isinstance(count, int) or not 20 <= count <= 800:
        return {"error": "count 必须是 20 至 800 的整数", "data_status": "unavailable"}
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={ts_code},day,,,{count},qfq"
    try:
        raw = http_get(url)
        data = json.loads(raw)
        root = data.get("data", {}).get(ts_code, {})
        # 仅接受明确返回的前复权序列，不能以未复权序列伪装通过硬门槛。
        bars_raw = root.get("qfqday") or []
        if not bars_raw:
            return {"error": f"未获取到前复权 K 线序列: {symbol}", "data_status": "unavailable"}

        # 格式化每根 K 线: [日期, 开盘, 收盘, 最高, 最低, 成交量]
        bars = []
        for row in bars_raw[-count:]:
            if len(row) >= 6:
                bars.append({
                    "date": str(row[0]),
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]),
                })

        valid_count = len(bars)
        if valid_count == 0:
            return {"error": "有效 K 线数量为 0"}

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        # 计算全周期均线矩阵: MA20 / MA50 / MA120 (半年线) / MA250 (年线) / MA500 (两年线)
        ma20 = sum(closes[-20:]) / min(20, valid_count) if valid_count >= 5 else closes[-1]
        ma50 = sum(closes[-50:]) / min(50, valid_count) if valid_count >= 10 else closes[-1]
        ma120 = round(sum(closes[-120:]) / 120.0, 2) if valid_count >= 100 else None
        ma250 = round(sum(closes[-250:]) / 250.0, 2) if valid_count >= 200 else None
        ma500 = round(sum(closes[-500:]) / 500.0, 2) if valid_count >= 400 else None

        latest_close = closes[-1]
        bias_ma20 = (latest_close - ma20) / ma20 * 100 if ma20 else 0.0
        bias_ma50 = (latest_close - ma50) / ma50 * 100 if ma50 else 0.0

        # 计算 ATR(14) 真实波幅
        trs = []
        for i in range(1, valid_count):
            h = highs[i]
            l = lows[i]
            prev_c = closes[i - 1]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
        atr14 = sum(trs[-14:]) / min(14, len(trs)) if trs else (highs[-1] - lows[-1])

        # 3年历史高低区间 (750根日线) 与 1年高低区间 (250根)
        high_3y = max(highs[-min(750, valid_count):])
        low_3y = min(lows[-min(750, valid_count):])
        high_year = max(highs[-min(250, valid_count):])
        low_year = min(lows[-min(250, valid_count):])

        # 内存无损聚合周线多周期共振体系
        weekly_analysis = aggregate_daily_to_weekly(bars)

        # 量能结构: 20日量比与120日量能分位 (盘中时当日成交量为未完成值)
        volumes = [b["volume"] for b in bars]
        latest_vol = volumes[-1]
        vol_20_mean = sum(volumes[-20:]) / min(20, valid_count) if valid_count >= 5 else latest_vol
        volume_ratio_20d = round(latest_vol / vol_20_mean, 2) if vol_20_mean and vol_20_mean > 0 else None
        vol_window = volumes[-min(120, valid_count):]
        if latest_vol and latest_vol > 0 and vol_window:
            volume_percentile_120d = round(sum(1 for v in vol_window if v <= latest_vol) / len(vol_window) * 100.0, 1)
        else:
            volume_percentile_120d = None

        # 预计算三层威科夫宏观与微观信号
        wyckoff_signals = compute_wyckoff_signals(
            bars, ma20, ma50, ma120, ma250, ma500, atr14, latest_close, bias_ma20,
            high_year, low_year, high_3y, low_3y, weekly_analysis
        )

        res = {
            "source": "P3_Tencent_QFQ_KLine",
            "data_status": "ok",
            "adjustment": "qfq",
            "symbol": symbol,
            "ts_code": ts_code,
            "valid_bars": valid_count,
            "hard_gate_passed": valid_count >= 120,
            "compact_mode": compact,
            "latest_date": bars[-1]["date"],
            "latest_close": latest_close,
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "ma120_half_year": ma120,
            "ma250_year_line": ma250,
            "ma500_2year_line": ma500,
            "bias_ma20": f"{bias_ma20:+.2f}%",
            "bias_ma50": f"{bias_ma50:+.2f}%",
            "bias_ma250_year": wyckoff_signals["bias_ma250"],
            "bias_ma500_2year": wyckoff_signals["bias_ma500"],
            "atr14": round(atr14, 2),
            "atr14_pct": f"{(atr14 / latest_close * 100):.2f}%",
            "high_120": max(highs[-min(120, valid_count):]),
            "low_120": min(lows[-min(120, valid_count):]),
            "high_year": high_year,
            "low_year": low_year,
            "high_3y": high_3y,
            "low_3y": low_3y,
            "percentile_3y": wyckoff_signals["percentile_3y"],
            "recent_5d_return": f"{((closes[-1] - closes[-min(5, valid_count)]) / closes[-min(5, valid_count)] * 100):+.2f}%",
            "recent_20d_return": f"{((closes[-1] - closes[-min(20, valid_count)]) / closes[-min(20, valid_count)] * 100):+.2f}%",
            "volume_ratio_20d": volume_ratio_20d,
            "volume_percentile_120d": volume_percentile_120d,
            "weekly_timeframe": weekly_analysis,
            "wyckoff_multi_timeframe": wyckoff_signals,
            "bars_summary": f"已检验 {valid_count} 根前复权日K线 (覆盖3年宏观时空，含MA120/MA250/MA500均线矩阵及周线共振)，完全通过行情硬门槛" + (" [精简视图：附最近30日K线]" if compact else " [完整视图：附全量K线]"),
        }

        # Token 瘦身模式：精简模式下返回最近 30 根 K 线 (约6周，完整展现局部 TR 结构)
        if compact:
            res["recent_30_bars"] = bars[-min(30, valid_count):]
        else:
            res["bars"] = bars

        set_cached(cache_key, res, ttl=CACHE_TTL_SECONDS * 2)
        return res
    except Exception as exc:
        return {"error": f"获取或解析前复权日K线出错: {type(exc).__name__}", "data_status": "unavailable"}


EM_UT = "7eea3edcaed734bea9cbfc24409ed989"
EM_DPT = "wz.ztzt"


def fetch_em_index_daily(secid: str, n: int) -> List[Dict[str, Any]]:
    """
    拉取东财指数日K序列 (含成交额，用于历史交易日的指数涨跌幅与两市成交额回补)
    fields2 顺序: f51日期, f52开, f53收, f54高, f55低, f56量, f57成交额(元)
    """
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid
        + f"&klt=101&fqt=0&lmt={n}&end=20500101"
        + "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    )
    raw = http_get(url, timeout=5)
    klines = (json.loads(raw).get("data") or {}).get("klines") or []
    out = []
    for line in klines[-n:]:
        parts = line.split(",")
        if len(parts) >= 7:
            out.append({
                "date": parts[0],
                "close": safe_float(parts[2], 0.0),
                "amount_yuan": safe_float(parts[6], 0.0),
            })
    return out


def fetch_market_sentiment(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    获取全市场情绪与量能总定调 (涨停数、炸板数、精确全市场炸板率、两市总成交额)
    直供 daily-review L1 情绪引擎与 market-prediction E4 量价簇
    历史日期的指数涨跌幅与成交额取自指数日K，不再混入实时快照
    """
    norm_date = normalize_date_str(date_str) if date_str else None
    if date_str and not norm_date:
        return {"error": "date_str 必须为 YYYYMMDD 或 YYYY-MM-DD", "data_status": "unavailable"}
    compact_date = norm_date.replace("-", "") if norm_date else datetime.now().strftime("%Y%m%d")
    is_today = compact_date == datetime.now().strftime("%Y%m%d")

    cache_key = f"sentiment_{compact_date}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    # 1. 抓取东方财富公开打板专题池 (免密 CDN)
    zt_count = 0
    zb_count = 0
    dt_count = 0
    max_height = 0
    unavailable_sources: List[str] = []

    try:
        # 涨停池
        zt_url = f"https://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={compact_date}"
        zt_data = json.loads(http_get(zt_url, timeout=4)).get("data", {}).get("pool", [])
        zt_count = len(zt_data)
        if zt_data:
            max_height = max([int(x.get("lbc", 1)) for x in zt_data])
    except Exception as exc:
        unavailable_sources = [f"涨停池: {type(exc).__name__}"]

    try:
        # 炸板池
        zb_url = f"https://push2ex.eastmoney.com/getTopicZBPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={compact_date}"
        zb_data = json.loads(http_get(zb_url, timeout=4)).get("data", {}).get("pool", [])
        zb_count = len(zb_data)
    except Exception as exc:
        unavailable_sources.append(f"炸板池: {type(exc).__name__}")

    try:
        # 跌停池
        dt_url = f"https://push2ex.eastmoney.com/getTopicDTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fund:asc&date={compact_date}"
        dt_data = json.loads(http_get(dt_url, timeout=4)).get("data", {}).get("pool", [])
        dt_count = len(dt_data)
    except Exception as exc:
        unavailable_sources.append(f"跌停池: {type(exc).__name__}")

    # 2. 指数涨跌幅与两市成交额: 当日用腾讯实时快照, 历史日期用东财指数日K回补 (不混用实时数据)
    sh_amount = 0.0
    sz_amount = 0.0
    sh_change = "0.00%"
    if is_today:
        try:
            idx_url = "https://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006"
            idx_raw = http_get(idx_url)
            lines = [line for line in idx_raw.split(";") if line.strip()]
            for line in lines:
                if "s_sh000001" in line:
                    p = line.split("~")
                    sh_change_raw = p[5].strip('\\"')
                    sh_change = f"{float(sh_change_raw):+.2f}%"
                    sh_amount = float(p[9].strip('\\\"')) / 10000.0  # 亿元
                elif "s_sz399001" in line:
                    p = line.split("~")
                    sz_amount = float(p[9].strip('\\\"')) / 10000.0  # 亿元
        except Exception as exc:
            unavailable_sources.append(f"指数成交额: {type(exc).__name__}")
    else:
        lookback = 30  # 容忍长假后的历史回看窗口
        sh_close: Optional[float] = None
        sh_prev_close: Optional[float] = None
        date_found = False

        # 指数涨跌幅主源: 腾讯指数日K (独立通道, 限流概率低); 东财日K为备源
        try:
            sh_bars = fetch_index_daily_bars(INDEX_ALIASES["SHCI"][0], lookback)
            for i, bar in enumerate(sh_bars):
                if bar["date"] == norm_date:
                    date_found = True
                    if i > 0 and sh_bars[i - 1]["close"] > 0:
                        sh_prev_close = sh_bars[i - 1]["close"]
                        sh_close = bar["close"]
                    break
        except Exception:
            pass

        # 东财指数日K: 兜底涨跌幅, 且是历史成交额的唯一来源 (腾讯指数日K无成交额字段)
        em_sh_rows: List[Dict[str, Any]] = []
        em_ok = True
        try:
            em_sh_rows = fetch_em_index_daily("1.000001", lookback)
            if not date_found:
                for i, r in enumerate(em_sh_rows):
                    if r["date"] == norm_date:
                        date_found = True
                        if i > 0 and em_sh_rows[i - 1]["close"] > 0:
                            sh_prev_close = em_sh_rows[i - 1]["close"]
                            sh_close = r["close"]
                        break
        except Exception:
            em_ok = False

        if not date_found:
            return {
                "source": "P3_Public_Financial_Gateways",
                "data_status": "unavailable",
                "date": compact_date,
                "error": f"{norm_date} 非交易日或指数日K未覆盖该日期",
            }
        if sh_close is not None and sh_prev_close:
            sh_change = f"{((sh_close - sh_prev_close) / sh_prev_close * 100):+.2f}%"

        # 历史两市成交额: 沪市取上证指数、深市用深证综指 (覆盖全部深市股票) 的成交额口径
        if not em_ok:
            unavailable_sources.append("历史成交额: 东财指数日K不可用")
        else:
            sh_amount_row = next((r for r in em_sh_rows if r["date"] == norm_date), None)
            if sh_amount_row:
                sh_amount = sh_amount_row["amount_yuan"] / 100000000.0
            else:
                unavailable_sources.append("沪市历史成交额: 指数日K未覆盖该日期")
            try:
                sz_rows = fetch_em_index_daily("0.399106", lookback)
                sz_row = next((r for r in sz_rows if r["date"] == norm_date), None)
                if sz_row:
                    sz_amount = sz_row["amount_yuan"] / 100000000.0
                else:
                    unavailable_sources.append("深市历史成交额: 深证综指未覆盖该日期")
            except Exception as exc:
                unavailable_sources.append(f"深市历史成交额: {type(exc).__name__}")

    if unavailable_sources:
        return {
            "source": "P3_Public_Financial_Gateways",
            "data_status": "partial",
            "date": compact_date,
            "unavailable_sources": unavailable_sources,
            "message": "部分上游数据不可用，不能据此计算市场情绪结论。",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    total_turnover = sh_amount + sz_amount
    total_touch = zt_count + zb_count
    break_rate = (zb_count / total_touch * 100) if total_touch > 0 else 0.0

    res = {
        "source": "P3_Public_Financial_Gateways",
        "data_status": "ok",
        "date": compact_date,
        "sh_index_change": sh_change,
        "total_turnover_billion": round(total_turnover, 2),
        "zt_count": zt_count,
        "zb_count": zb_count,
        "dt_count": dt_count,
        "exact_break_rate": f"{break_rate:.2f}%",
        "max_ladder_height": f"{max_height} 连板",
        "market_broad_status": "良性分歧" if break_rate < 30 else ("高位退潮" if break_rate > 45 else "震荡博弈"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    set_cached(cache_key, res, ttl=CACHE_TTL_SECONDS if is_today else HISTORICAL_CACHE_TTL_SECONDS)
    return res


def fetch_limit_up_ladder(date_str: Optional[str] = None) -> Dict[str, Any]:
    """获取 A 股连板天梯矩阵 (各板高度代表票与晋级梯队)"""
    norm_date = normalize_date_str(date_str) if date_str else None
    if date_str and not norm_date:
        return {"error": "date_str 必须为 YYYYMMDD 或 YYYY-MM-DD", "data_status": "unavailable"}
    compact_date = norm_date.replace("-", "") if norm_date else datetime.now().strftime("%Y%m%d")
    is_today = compact_date == datetime.now().strftime("%Y%m%d")

    cache_key = f"ladder_{compact_date}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = f"https://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={compact_date}"
    try:
        data = json.loads(http_get(url, timeout=4)).get("data", {}).get("pool", [])

        ladder: Dict[int, List[Dict[str, Any]]] = {}
        for item in data:
            height = int(item.get("lbc", 1))
            ladder.setdefault(height, []).append({
                "code": item.get("c"),
                "name": item.get("n"),
                "industry": item.get("hybk", "其他"),
                "first_time": item.get("fbt"),
                "last_time": item.get("lbt"),
                "fund_million": round(float(item.get("fund", 0)) / 10000.0, 2),
            })

        summary = []
        for h in sorted(ladder.keys(), reverse=True):
            stocks = ladder[h]
            summary.append({
                "height": f"{h} 连板",
                "count": len(stocks),
                "leaders": [f"{s['name']}({s['code']})" for s in stocks[:5]],
            })

        res = {
            "source": "P3_Eastmoney_LimitUp_Ladder",
            "data_status": "ok",
            "date": compact_date,
            "total_limit_up": len(data),
            "max_height": max(ladder.keys()) if ladder else 0,
            "ladder_distribution": summary,
        }
        set_cached(cache_key, res, ttl=CACHE_TTL_SECONDS if is_today else HISTORICAL_CACHE_TTL_SECONDS)
        return res
    except Exception as e:
        return {"error": f"获取连板天梯失败: {str(e)}"}


def fetch_topic_pool(pool_path: str, compact_date: str, sort_field: str) -> List[Dict[str, Any]]:
    """东财涨停/炸板/跌停池通用拉取 (push2ex, 支持历史 date 回补)"""
    url = (f"https://push2ex.eastmoney.com/{pool_path}?ut={EM_UT}&dpt={EM_DPT}"
           f"&Pageindex=0&pagesize=500&sort={sort_field}&date={compact_date}")
    return json.loads(http_get(url, timeout=4)).get("data", {}).get("pool", []) or []


def fetch_industry_board_list() -> List[Dict[str, str]]:
    """东财全量行业板块表 (代码+名称, 日级缓存); 兼作 hybk 缩写前缀歧义判定基准"""
    cached = get_cached("industry_board_list")
    if cached:
        return cached
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1"
        "&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f12,f14"
    )
    rows = json.loads(http_get(url, timeout=5)).get("data", {}).get("diff", []) or []
    boards = [{"code": str(r.get("f12", "")), "name": str(r.get("f14", "")).strip()}
              for r in rows if str(r.get("f12", "")).startswith("BK")]
    if not boards:
        raise ValueError("行业板块表为空")
    set_cached("industry_board_list", boards, ttl=86400)
    return boards


def industry_hybk_matches(hybk: str, board_name: str) -> bool:
    """涨停/炸板池 hybk 为 <=4 字行业缩写 (如"农产品加工"->"农产品加"), 全称相等或缩写为全称前缀才算同板块"""
    short = (hybk or "").strip()
    full = (board_name or "").strip()
    if not short or not full:
        return False
    return full == short or full.startswith(short)


def fetch_sector_limit_quality(sector: str, date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    板块级触板/炸板结构与板块炸板率 (直供 Q=(1-板块炸板率)×100 的确定性输入)
    涨停池/炸板池 hybk 为 <=4 字行业缩写, 此处按前缀规则匹配并对全板块表做歧义校验,
    杜绝"按板块全称精确匹配漏票"导致的板块炸板率失真; 触板 <3 家时 Q 记 null (小样本不稳定)
    """
    if not isinstance(sector, str) or not sector.strip():
        return {"error": "sector 必须是非空字符串", "data_status": "unavailable"}
    norm_date = normalize_date_str(date_str) if date_str else None
    if date_str and not norm_date:
        return {"error": "date_str 必须为 YYYYMMDD 或 YYYY-MM-DD", "data_status": "unavailable"}
    compact_date = norm_date.replace("-", "") if norm_date else datetime.now().strftime("%Y%m%d")
    is_today = compact_date == datetime.now().strftime("%Y%m%d")

    clean = sector.strip()
    upper = clean.upper().replace("90.", "")
    sector_code = upper if upper.startswith("BK") and upper[2:].isdigit() else resolve_sector_code(clean)
    if not sector_code:
        return {"error": f"无法解析板块: {clean}", "data_status": "unavailable"}

    try:
        boards = fetch_industry_board_list()
    except Exception as exc:
        return {"error": f"行业板块表不可用: {type(exc).__name__}", "data_status": "unavailable"}
    target = next((b for b in boards if b["code"] == sector_code), None)
    if not target:
        return {"error": f"{sector_code} 不在东财行业板块表内 (仅支持行业板块, 概念板块无 hybk 归属)", "data_status": "unavailable"}

    cache_key = f"sector_limit_quality_{sector_code}_{compact_date}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    unavailable_sources: List[str] = []
    try:
        zt_pool = fetch_topic_pool("getTopicZTPool", compact_date, "fbt:asc")
    except Exception:
        zt_pool = []
        unavailable_sources.append(f"涨停池@{compact_date}")
    try:
        zb_pool = fetch_topic_pool("getTopicZBPool", compact_date, "fbt:asc")
    except Exception:
        zb_pool = []
        unavailable_sources.append(f"炸板池@{compact_date}")
    if not zt_pool and not zb_pool:
        res = {"error": f"{compact_date} 涨停池与炸板池均为空 (可能为非交易日或数据源未覆盖)",
               "data_status": "unavailable"}
        return res

    def attribute(pool: List[Dict[str, Any]], extra_fields) -> Tuple[List, List]:
        """按 hybk 归属目标板块: 精确同名唯一归属; 否则前缀匹配, 与多个板块前缀冲突的缩写剔除并返回歧义清单"""
        matched, ambiguous = [], []
        for item in pool:
            hybk = str(item.get("hybk", "") or "").strip()
            exact = next((b for b in boards if b["name"] == hybk), None)
            entry = {"code": item.get("c"), "name": item.get("n"), "industry_raw": hybk or "N/A"}
            entry.update(extra_fields(item))
            if exact is not None:
                if exact["code"] == target["code"]:
                    matched.append(entry)
                continue
            if not industry_hybk_matches(hybk, target["name"]):
                continue
            collisions = [b["name"] for b in boards
                          if b["code"] != target["code"] and industry_hybk_matches(hybk, b["name"])]
            if collisions:
                entry["ambiguous_with"] = collisions
                ambiguous.append(entry)
            else:
                matched.append(entry)
        return matched, ambiguous

    sealed, ambiguous_zt = attribute(zt_pool, lambda it: {"lbc": int(it.get("lbc", 1) or 1), "first_time": it.get("fbt")})
    broken, ambiguous_zb = attribute(zb_pool, lambda it: {"break_count": int(it.get("zbc", 1) or 1)})

    sealed_count, broken_count = len(sealed), len(broken)
    touched = sealed_count + broken_count
    rate = round(broken_count / touched * 100.0, 2) if touched else 0.0
    q_value = round((1 - broken_count / touched) * 100.0, 1) if touched >= 3 else None
    if touched >= 3:
        q_note = "Q=(1-板块炸板率)×100; 供评分层直接使用"
    elif touched > 0:
        q_note = "触板不足 3 家, Q 记 null (小样本炸板率不稳定), 评分层对可得权重归一化, 不得借用全市场炸板率"
    else:
        q_note = "本板块当日无触板个股, Q 记 null"

    ambiguous = ambiguous_zt + ambiguous_zb
    res = {
        "source": "P3_Eastmoney_Sector_Limit_Quality",
        "data_status": "partial" if unavailable_sources else "ok",
        "sector": target["name"],
        "sector_code": target["code"],
        "date": compact_date,
        "sealed_count": sealed_count,
        "broken_count": broken_count,
        "touched_count": touched,
        "sector_break_rate": f"{rate:.2f}%",
        "seal_quality_q": q_value,
        "q_note": q_note,
        "industry_match_rule": "hybk 与板块全称精确相等时唯一归属; 否则 hybk(<=4字缩写)按前缀匹配全称, 与多个板块前缀冲突的缩写剔除并披露",
        "limit_up_stocks": sealed,
        "broken_stocks": broken,
    }
    if ambiguous:
        res["ambiguous_industry_stocks"] = ambiguous
    if unavailable_sources:
        res["unavailable_sources"] = unavailable_sources
    set_cached(cache_key, res, ttl=CACHE_TTL_SECONDS if is_today else HISTORICAL_CACHE_TTL_SECONDS)
    return res


def fetch_market_breadth(days: int = 5) -> Dict[str, Any]:
    """
    获取全市场广度 N 个交易日序列:
    - 最新交易日: 东财涨跌分布快照给出精确的上涨/下跌/平盘家数与红盘率 (快照仅支持最新交易日)
    - 历史交易日: 官方公开网关不提供全市场涨跌家数, 以涨停/炸板/跌停池与沪指逐日涨跌幅替代,
      并通过 breadth_precision 字段显式标注精度, 绝不估算
    直供 sector-rotation 全窗口市场广度温度计与情绪退潮识别
    """
    if not isinstance(days, int) or not 2 <= days <= 10:
        return {"error": "days 必须是 2 至 10 的整数", "data_status": "unavailable"}

    cached = get_cached(f"breadth_{days}")
    if cached:
        return cached

    # 1. 交易日序列以沪指日K为准 (不自行维护交易日历)
    try:
        sh_bars = fetch_index_daily_bars(INDEX_ALIASES["SHCI"][0], days)
    except Exception as exc:
        return {"error": f"交易日序列(沪指日K)不可用: {type(exc).__name__}", "data_status": "unavailable"}
    if len(sh_bars) < 2:
        return {"error": "沪指日K序列不足，无法构建交易日窗口", "data_status": "unavailable"}

    unavailable_sources: List[str] = []

    # 2. 最新交易日的精确涨跌家数快照
    exact = None
    exact_date = None
    try:
        raw = http_get(f"https://push2ex.eastmoney.com/getTopicZDFenBu?ut={EM_UT}&dpt={EM_DPT}")
        data = json.loads(raw).get("data", {}) or {}
        qdate = str(data.get("qdate", ""))
        fenbu: Dict[str, int] = {}
        for item in data.get("fenbu", []) or []:
            if isinstance(item, dict):
                fenbu.update(item)
        up = sum(v for k, v in fenbu.items() if str(k).lstrip("-").isdigit() and int(k) > 0)
        down = sum(v for k, v in fenbu.items() if str(k).lstrip("-").isdigit() and int(k) < 0)
        flat = sum(v for k, v in fenbu.items() if str(k) == "0")
        total = up + down + flat
        if total > 0:
            exact = {"up_count": up, "down_count": down, "flat_count": flat,
                     "total_stocks": total, "red_rate": round(up / total * 100.0, 2)}
            exact_date = f"{qdate[:4]}-{qdate[4:6]}-{qdate[6:8]}" if len(qdate) == 8 else None
    except Exception as exc:
        unavailable_sources.append(f"涨跌分布快照: {type(exc).__name__}")

    # 3. 逐交易日组装: 指数涨跌幅 + 情绪池 (东财池支持历史 date 回补)
    def pool_json(pool_path: str, d_compact: str, sort_field: str) -> List[Dict[str, Any]]:
        return fetch_topic_pool(pool_path, d_compact, sort_field)

    day_rows: List[Dict[str, Any]] = []
    for i in range(max(1, len(sh_bars) - days), len(sh_bars)):
        cur, prev = sh_bars[i], sh_bars[i - 1]
        d_dash = cur["date"]
        d_compact = d_dash.replace("-", "")
        row: Dict[str, Any] = {
            "date": d_dash,
            "sh_index_change": f"{((cur['close'] - prev['close']) / prev['close'] * 100):+.2f}%" if prev["close"] > 0 else "N/A",
            "breadth_precision": "limit_pools_only",
        }
        if exact and d_dash == exact_date:
            row.update({
                "up_count": exact["up_count"],
                "down_count": exact["down_count"],
                "flat_count": exact["flat_count"],
                "total_stocks": exact["total_stocks"],
                "red_rate": f"{exact['red_rate']:.2f}%",
                "breadth_precision": "exact",
            })
        try:
            zt_rows = pool_json("getTopicZTPool", d_compact, "fbt:asc")
            row["zt_count"] = len(zt_rows)
            row["max_ladder_height"] = max([int(x.get("lbc", 1) or 1) for x in zt_rows]) if zt_rows else 0
        except Exception:
            unavailable_sources.append(f"涨停池@{d_dash}")
        try:
            row["zb_count"] = len(pool_json("getTopicZBPool", d_compact, "fbt:asc"))
        except Exception:
            unavailable_sources.append(f"炸板池@{d_dash}")
        try:
            row["dt_count"] = len(pool_json("getTopicDTPool", d_compact, "fund:asc"))
        except Exception:
            unavailable_sources.append(f"跌停池@{d_dash}")
        day_rows.append(row)

    res = {
        "source": "P3_Public_Financial_Gateways",
        "data_status": "partial" if (unavailable_sources or exact is None) else "ok",
        "days_window": day_rows,
        "note": ("最新交易日为精确全市场涨跌家数口径 (breadth_precision=exact)；"
                 "历史交易日官方公开网关不提供全市场涨跌家数，以涨停/炸板/跌停池与沪指涨跌幅替代 "
                 "(breadth_precision=limit_pools_only)，不进行估算"),
    }
    if exact:
        res["latest_exact_snapshot"] = {"date": exact_date, **exact}
    if unavailable_sources:
        res["unavailable_sources"] = unavailable_sources
    set_cached(f"breadth_{days}", res)
    return res


def fetch_sector_fund_history(sector_code: str, days: int) -> List[Dict[str, Any]]:
    """
    获取单个行业板块的主力资金流日K历史 (东财 fflow daykline 网关, 带板块级缓存)
    每行字段序: 日期, 主力净额(元), 小单, 中单, 大单, 超大单, 各占比..., 收盘, 涨跌幅...
    """
    cache_key = f"fflow_{sector_code}_{days}"
    cached = get_cached(cache_key)
    if cached:
        return cached
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?lmt={days}&klt=101&secid=90.{sector_code}&secid2=90.{sector_code}"
        "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
    )
    raw = http_get(url, timeout=4)
    klines = (json.loads(raw).get("data") or {}).get("klines") or []
    hist = []
    for line in klines[-days:]:
        parts = line.split(",")
        if len(parts) >= 13:
            hist.append({
                "date": parts[0],
                "main_net_inflow_billion": round(safe_float(parts[1], 0.0) / 100000000.0, 2),
                "change_pct": f"{safe_float(parts[12], 0.0):+.2f}%",
            })
    if not hist:
        raise ValueError("资金流历史为空")
    set_cached(cache_key, hist, ttl=ttl_for_history(hist[-1]["date"]))
    return hist


def fund_flow_trend_label(hist: List[Dict[str, Any]]) -> str:
    """根据逐日主力净额符号序列给出资金趋势定性"""
    if not hist:
        return "N/A"
    values = [h["main_net_inflow_billion"] for h in hist]
    if all(v == 0 for v in values):
        return "零净流入"  # 全零序列按符号判定会被误标为"连续净流出"
    signs = [1 if v > 0 else -1 for v in values]
    if all(s > 0 for s in signs):
        return "连续净流入"
    if all(s < 0 for s in signs):
        return "连续净流出"
    return "净流出转净流入" if signs[-1] > 0 else "净流入转净流出"


def resolve_sector_code(keyword: str) -> Optional[str]:
    """解析板块名称或代码为东财行业板块代码 (BKxxxxxx)；名称走 clist 全量行业板块表模糊匹配"""
    clean = keyword.strip()
    upper = clean.upper().replace("90.", "")
    if upper.startswith("BK") and upper[2:].isdigit():
        return upper

    cache_key = f"sector_lookup_{clean}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1"
        "&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f12,f14"
    )
    try:
        rows = json.loads(http_get(url, timeout=5)).get("data", {}).get("diff", []) or []
        exact = next((str(r["f12"]) for r in rows if str(r.get("f14", "")).strip() == clean), None)
        if exact:
            set_cached(cache_key, exact, ttl=86400)
            return exact
        fuzzy = [r for r in rows if clean in str(r.get("f14", ""))]
        if len(fuzzy) == 1:
            set_cached(cache_key, str(fuzzy[0]["f12"]), ttl=86400)
            return str(fuzzy[0]["f12"])
    except Exception:
        pass
    return None


def _sector_ma(closes: List[float], window: int) -> Optional[float]:
    return round(sum(closes[-window:]) / window, 2) if len(closes) >= window else None


def _sector_return(closes: List[float], window: int) -> str:
    n = len(closes)
    w = min(window, n - 1)  # 序列不足窗口时退化为可得区间
    base = closes[-(w + 1)]
    return f"{((closes[-1] - base) / base * 100):+.2f}%" if base > 0 else "N/A"


def fetch_sector_kline(sector: str, count: int = 130) -> Dict[str, Any]:
    """
    获取东财行业板块指数日K序列、均线体系、区间涨幅与资金证据
    主源为东财标准K线 (完整OHLCV+成交额, 支撑板块资金延续评分的成交额对比);
    主源不可用时自动兜底 fflow daykline (收盘序列+主力净额, 高低点为收盘价口径)
    直供 stock-analysis L4 行业基准、daily-review 资金延续 V 项与 L2 板块强度证据
    """
    if not isinstance(count, int) or not 20 <= count <= 250:
        return {"error": "count 必须是 20 至 250 的整数", "data_status": "unavailable"}
    sector_code = resolve_sector_code(sector)
    if not sector_code:
        return {
            "error": f"无法解析板块: {sector} (可传 BK 代码如 BK1036; 板块代码可用 get_sector_fund_flow 查询)",
            "data_status": "unavailable",
        }

    cache_key = f"sector_kline_{sector_code}_{count}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    # 主源: 东财标准K线 (完整 OHLCV + 成交额)
    try:
        kline_url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid=90.{sector_code}&klt=101&fqt=1&lmt={count}&end=20500101"
            "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
        )
        data = (json.loads(http_get(kline_url, timeout=5)).get("data") or {})
        klines = data.get("klines") or []
        rows = []
        for line in klines[-count:]:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({
                    "date": parts[0],
                    "open": safe_float(parts[1], 0.0),
                    "close": safe_float(parts[2], 0.0),
                    "high": safe_float(parts[3], 0.0),
                    "low": safe_float(parts[4], 0.0),
                    "amount_billion": round(safe_float(parts[6], 0.0) / 100000000.0, 2),
                })
        closes = [r["close"] for r in rows]
        n = len(closes)
        if n >= 2 and closes[-1] > 0:
            amounts = [r["amount_billion"] for r in rows]
            prev_amount = amounts[-2] if n >= 2 else None
            res = {
                "source": "P3_Eastmoney_Sector_Kline",
                "data_status": "ok",
                "ohlc_source": True,
                "sector_code": sector_code,
                "sector_name": data.get("name", sector),
                "valid_bars": n,
                "latest_date": rows[-1]["date"],
                "latest_close": closes[-1],
                "latest_open": rows[-1]["open"],
                "latest_high": rows[-1]["high"],
                "latest_low": rows[-1]["low"],
                "latest_change_pct": _sector_return(closes, 1),
                "ma5": _sector_ma(closes, 5),
                "ma10": _sector_ma(closes, 10),
                "ma20": _sector_ma(closes, 20),
                "ma60": _sector_ma(closes, 60),
                "recent_5d_return": _sector_return(closes, 5),
                "recent_20d_return": _sector_return(closes, 20),
                "recent_60d_return": _sector_return(closes, 60),
                "high_20d": max(r["high"] for r in rows[-min(20, n):]),
                "low_20d": min(r["low"] for r in rows[-min(20, n):]),
                "high_60d": max(r["high"] for r in rows[-min(60, n):]),
                "low_60d": min(r["low"] for r in rows[-min(60, n):]),
                "latest_amount_billion": amounts[-1],
                "prev_amount_billion": prev_amount,
                "amount_ratio_1d": round(amounts[-1] / prev_amount, 2) if prev_amount and prev_amount > 0 else None,
                "avg_amount_5d_billion": round(sum(amounts[-min(5, n):]) / min(5, n), 2),
                "note": "完整OHLCV+成交额口径 (东财板块标准K线)；amount_ratio_1d 即板块资金延续评分 (Capital Continuity) 成交连续度 V 项的直接输入",
            }
            if n < count:
                res["data_status"] = "partial"
                res["note"] += f"；实际仅取得 {n} 根 (不足请求的 {count} 根)"
            set_cached(cache_key, res, ttl=ttl_for_history(rows[-1]["date"]))
            return res
    except Exception:
        pass  # 主源不可用, 自动走 fflow 兜底

    # 兜底: fflow daykline (收盘序列 + 主力净额, 无盘中高低价与成交额)
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?lmt={count}&klt=101&secid=90.{sector_code}&secid2=90.{sector_code}"
        "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
    )
    try:
        data = json.loads(http_get(url, timeout=5)).get("data") or {}
        klines = data.get("klines") or []
        if len(klines) < 2:
            return {"error": f"未获取到板块日K序列: {sector}", "data_status": "unavailable",
                    "hint": "东财板块源不可用时, 可改用 get_basket_index 传入板块主要成分股构造等权代理序列 (使用边界见公共研究契约)"}

        rows = []
        for line in klines[-count:]:
            parts = line.split(",")
            if len(parts) >= 13:
                rows.append({
                    "date": parts[0],
                    "close": safe_float(parts[11], 0.0),
                    "change_pct": f"{safe_float(parts[12], 0.0):+.2f}%",
                    "main_net_inflow_billion": round(safe_float(parts[1], 0.0) / 100000000.0, 2),
                })
        closes = [r["close"] for r in rows]
        n = len(closes)
        if n < 2 or closes[-1] <= 0:
            return {"error": "板块日K序列不完整", "data_status": "unavailable"}

        res = {
            "source": "P3_Eastmoney_Sector_Kline",
            "data_status": "ok",
            "ohlc_source": False,
            "sector_code": sector_code,
            "sector_name": data.get("name", sector),
            "valid_bars": n,
            "latest_date": rows[-1]["date"],
            "latest_close": closes[-1],
            "latest_change_pct": rows[-1]["change_pct"],
            "ma5": _sector_ma(closes, 5),
            "ma10": _sector_ma(closes, 10),
            "ma20": _sector_ma(closes, 20),
            "ma60": _sector_ma(closes, 60),
            "recent_5d_return": _sector_return(closes, 5),
            "recent_20d_return": _sector_return(closes, 20),
            "recent_60d_return": _sector_return(closes, 60),
            "high_close_20d": max(closes[-min(20, n):]),
            "low_close_20d": min(closes[-min(20, n):]),
            "high_close_60d": max(closes[-min(60, n):]),
            "low_close_60d": min(closes[-min(60, n):]),
            "cum_main_net_inflow_5d_billion": round(sum(r["main_net_inflow_billion"] for r in rows[-5:]), 2),
            "cum_main_net_inflow_20d_billion": round(sum(r["main_net_inflow_billion"] for r in rows[-min(20, n):]), 2),
            "note": "收盘序列来自东财板块资金流日K网关 (无盘中高低价与成交额, 高低点为收盘价口径)；近5/20日主力净流入累计为板块资金延续证据",
        }
        if n < count:
            res["data_status"] = "partial"
            res["note"] += f"；实际仅取得 {n} 根 (不足请求的 {count} 根)"
        set_cached(cache_key, res, ttl=ttl_for_history(rows[-1]["date"]))
        return res
    except Exception as exc:
        return {"error": f"获取板块日K出错: {type(exc).__name__}", "data_status": "unavailable",
                "hint": "东财板块源不可用时, 可改用 get_basket_index 传入板块主要成分股构造等权代理序列 (使用边界见公共研究契约)"}


def fetch_basket_index(stocks: List[str], count: int = 20) -> Dict[str, Any]:
    """
    以腾讯前复权日K构造等权篮子指数（日度再平衡口径：篮子日收益 = 成分股当日收益的等权均值）
    用途：东财板块指数网关抖动时的代理序列（如保险 BK0735 仅 6 只成分股，等权大票覆盖度高）、
    主线篮子相对强度对照。输出为构造序列（series_type=equal_weight_constructed），
    只能用于方向性对照，不得用于精确评分阈值——使用边界见公共研究契约
    """
    if not isinstance(stocks, list) or len(stocks) < 2 or len(stocks) > 10:
        return {"error": "stocks 必须是 2 至 10 个标的的数组", "data_status": "unavailable"}
    if not all(isinstance(s, str) and s.strip() for s in stocks):
        return {"error": "stocks 必须是非空字符串数组", "data_status": "unavailable"}
    if not isinstance(count, int) or not 5 <= count <= 60:
        return {"error": "count 必须是 5 至 60 的整数", "data_status": "unavailable"}

    cache_key = f"basket_{'|'.join(dict.fromkeys(s.strip() for s in stocks))}_{count}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    # 1. 逐标的拉取前复权收盘序列 (去重; 停牌/未上市日期自然缺失, 由 ffill 与按日可用集处理)
    series_by_stock: Dict[str, Dict[str, float]] = {}
    succeeded: List[str] = []
    failed: List[str] = []
    for raw in dict.fromkeys(stocks):
        ts_code = normalize_symbol(raw)
        try:
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={ts_code},day,,,{count + 1},qfq"
            data = json.loads(http_get(url, timeout=5)).get("data", {}).get(ts_code, {})
            bars = data.get("qfqday") or data.get("day") or []
            closes = {str(r[0]): float(r[2]) for r in bars[-(count + 1):] if len(r) >= 3}
            if len(closes) >= 2:
                series_by_stock[ts_code] = closes
                succeeded.append(f"{raw}({ts_code})")
            else:
                failed.append(str(raw))
        except Exception:
            failed.append(str(raw))

    if len(series_by_stock) < 2:
        return {
            "error": f"有效成分股不足 2 只 (成功: {succeeded or '无'}; 失败: {failed or '无'})",
            "data_status": "unavailable",
        }

    # 2. 交易日并集 + 逐标的 ffill; 每日收益只纳入当日有前收盘价的标的
    all_dates = sorted({d for s in series_by_stock.values() for d in s})
    basket_dates = all_dates[-(count + 1):]
    if len(basket_dates) < 2:
        return {"error": "有效交易日不足", "data_status": "unavailable"}

    levels: List[Dict[str, Any]] = []
    level = 100.0
    prev_date: Optional[str] = None
    for d in basket_dates:
        if prev_date is not None:
            rets = []
            for closes in series_by_stock.values():
                cur = closes.get(d) or _last_close_on_or_before(closes, d)
                prev = closes.get(prev_date) or _last_close_on_or_before(closes, prev_date)
                if cur is not None and prev is not None and prev > 0:
                    rets.append(cur / prev - 1.0)
            if rets:
                level *= (1.0 + sum(rets) / len(rets))
            levels.append({
                "date": d,
                "level": round(level, 2),
                "change_pct": f"{(sum(rets) / len(rets) * 100):+.2f}%" if rets else "0.00%",
                "stocks_counted": len(rets),
            })
        else:
            levels.append({"date": d, "level": 100.0, "change_pct": "0.00% (基期)", "stocks_counted": len(series_by_stock)})
        prev_date = d

    ret_5 = _basket_return(levels, 5)
    ret_20 = _basket_return(levels, 20)
    res = {
        "source": "P3_Tencent_Constructed_Basket",
        "data_status": "partial" if failed else "ok",
        "series_type": "equal_weight_constructed",
        "basket_size": len(series_by_stock),
        "stocks_succeeded": succeeded,
        "stocks_failed": failed,
        "valid_bars": len(levels) - 1,
        "latest_date": levels[-1]["date"],
        "latest_level": levels[-1]["level"],
        "recent_5d_return": ret_5,
        "recent_20d_return": ret_20,
        "series": levels,
        "note": ("等权构造序列 (日度再平衡口径, 腾讯前复权收盘): 与板块官方市值加权指数存在口径差异, "
                 "只能用于方向性强弱对照, 不得用于精确评分阈值或赔率计算; 报告中必须标注'代理序列'并披露成分覆盖度"),
    }
    if failed:
        res["note"] += f"；未纳入成分: {', '.join(failed)}"
    set_cached(cache_key, res, ttl=300)
    return res


def _last_close_on_or_before(closes: Dict[str, float], date_str: str) -> Optional[float]:
    """返回 closes 中不晚于 date_str 的最近收盘价 (处理停牌/迟到上市)"""
    earlier = [d for d in closes if d <= date_str]
    return closes[max(earlier)] if earlier else None


def _basket_return(levels: List[Dict[str, Any]], window: int) -> str:
    if len(levels) < window + 1:
        w = len(levels) - 1
    else:
        w = window
    if w <= 0 or levels[-(w + 1)]["level"] <= 0:
        return "N/A"
    return f"{((levels[-1]['level'] - levels[-(w + 1)]['level']) / levels[-(w + 1)]['level'] * 100):+.2f}%"


def fetch_sector_fund_flow(count: int = 20, days: int = 1) -> Dict[str, Any]:
    """
    获取 A 股全行业板块主力资金流向、涨跌幅排行与领涨龙头；days>1 时附各板块 N 日主力净流入历史
    直供 daily-review L2 强势板块定位与 sector-rotation 5日资金迁移分析
    """
    if not isinstance(count, int) or not 1 <= count <= 100:
        return {"error": "count 必须是 1 至 100 的整数", "data_status": "unavailable"}
    if not isinstance(days, int) or not 1 <= days <= 10:
        return {"error": "days 必须是 1 至 10 的整数", "data_status": "unavailable"}
    if days > 1 and count > 12:
        return {"error": "days > 1 时 count 上限为 12 (控制上游请求数)", "data_status": "unavailable"}

    cache_key = f"sector_fund_flow_{count}_{days}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1"
        "&ut=b2884a393a59ad64002292a3e90d46a5&fltt=2&invt=2&fid=f62&fs=m:90+t:2+f:!50"
        "&fields=f12,f14,f2,f3,f62,f184,f204,f205"
    )
    try:
        raw = http_get(url)
        data = json.loads(raw).get("data", {}).get("diff", [])
        if not data:
            return {"error": "未获取到行业资金流数据"}

        sectors = []
        for item in data:
            net_inflow_yuan = safe_float(item.get("f62"), 0.0)
            net_inflow_billion = round(net_inflow_yuan / 100000000.0, 2)
            sectors.append({
                "code": item.get("f12"),
                "name": item.get("f14"),
                "change_pct": f"{safe_float(item.get('f3'), 0.0):+.2f}%",
                "change_val": safe_float(item.get("f3"), 0.0),
                "net_inflow_billion": net_inflow_billion,
                "net_inflow_ratio": f"{safe_float(item.get('f184'), 0.0):+.2f}%",
                "top_stock_name": item.get("f204", "--"),
                "top_stock_code": item.get("f205", "--"),
            })

        sorted_by_inflow = sorted(sectors, key=lambda x: x["net_inflow_billion"], reverse=True)
        top_inflows = sorted_by_inflow[:count]
        top_outflows = sorted_by_inflow[-count:][::-1]

        sorted_by_gain = sorted(sectors, key=lambda x: x["change_val"], reverse=True)
        top_gainers = sorted_by_gain[:count]
        top_losers = sorted_by_gain[-count:][::-1]

        res = {
            "source": "P3_Eastmoney_Sector_Fund_Flow",
            "data_status": "ok",
            "total_sectors_tracked": len(sectors),
            "top_inflow_sectors": [
                {
                    "rank": i + 1,
                    "name": s["name"],
                    "code": s["code"],
                    "change_pct": s["change_pct"],
                    "net_inflow_billion": f"{s['net_inflow_billion']:+.2f} 亿",
                    "inflow_ratio": s["net_inflow_ratio"],
                    "leading_stock": f"{s['top_stock_name']}({s['top_stock_code']})",
                }
                for i, s in enumerate(top_inflows)
            ],
            "top_outflow_sectors": [
                {
                    "rank": i + 1,
                    "name": s["name"],
                    "code": s["code"],
                    "change_pct": s["change_pct"],
                    "net_outflow_billion": f"{s['net_inflow_billion']:+.2f} 亿",
                    "leading_stock": f"{s['top_stock_name']}({s['top_stock_code']})",
                }
                for i, s in enumerate(top_outflows)
            ],
            "top_gainer_sectors": [
                {
                    "rank": i + 1,
                    "name": s["name"],
                    "change_pct": s["change_pct"],
                    "net_inflow": f"{s['net_inflow_billion']:+.2f} 亿",
                    "leader": f"{s['top_stock_name']}({s['top_stock_code']})",
                }
                for i, s in enumerate(top_gainers)
            ],
            "top_loser_sectors": [
                {
                    "rank": i + 1,
                    "name": s["name"],
                    "change_pct": s["change_pct"],
                    "net_inflow": f"{s['net_inflow_billion']:+.2f} 亿",
                }
                for i, s in enumerate(top_losers)
            ],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # days > 1: 对流入/流出榜板块逐个回补主力资金 N 日历史 (单板块失败不影响整体, 标记 partial)
        if days > 1:
            target_codes = list(dict.fromkeys([s["code"] for s in top_inflows + top_outflows]))
            history_map: Dict[str, List[Dict[str, Any]]] = {}
            failed_history: List[str] = []
            for code in target_codes:
                try:
                    history_map[str(code)] = fetch_sector_fund_history(str(code), days)
                except Exception:
                    failed_history.append(str(next((s["name"] for s in sectors if s["code"] == code), code)))
                time.sleep(0.12)  # 批量回补时节流, 避免触发上游限流
            for entry in res["top_inflow_sectors"] + res["top_outflow_sectors"]:
                hist = history_map.get(str(entry.get("code")))
                if hist:
                    entry["history"] = hist
                    entry["cum_net_inflow_billion"] = round(
                        sum(h["main_net_inflow_billion"] for h in hist), 2)
                    entry["fund_flow_trend"] = fund_flow_trend_label(hist)
            res["history_days"] = days
            if failed_history:
                res["data_status"] = "partial"
                res["history_unavailable_sectors"] = failed_history

        set_cached(cache_key, res)
        return res
    except Exception as e:
        return {"error": f"获取行业资金流向出错: {str(e)}"}


def fetch_longhubang_detail(symbol: Optional[str] = None, date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    获取 A 股交易所公开龙虎榜席位明细（全市场概览或个股前五大买卖席位穿透）
    直供 daily-review 席位品质与 stock-analysis L5 筹码结构
    """
    clean_symbol = symbol.strip() if symbol else ""
    if clean_symbol:
        code_only = clean_symbol.split(".")[0].replace("sh", "").replace("sz", "").replace("bj", "")
    else:
        code_only = ""

    norm_date = normalize_date_str(date_str) if date_str else None
    if date_str and not norm_date:
        return {"error": "date_str 必须为 YYYYMMDD 或 YYYY-MM-DD", "data_status": "unavailable"}

    cache_key = f"lhb_{code_only}_{norm_date or 'latest'}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        if code_only:
            filter_expr = f'(SECURITY_CODE="{code_only}")'
            if norm_date:
                filter_expr += f"(TRADE_DATE='{norm_date}')"
            buy_url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get?"
                + urllib.parse.urlencode({
                    "reportName": "RPT_BILLBOARD_DAILYDETAILSBUY",
                    "columns": "ALL",
                    "pageNumber": 1,
                    "pageSize": 5,
                    "sortTypes": -1,
                    "sortColumns": "TRADE_DATE",
                    "filter": filter_expr,
                    "source": "WEB",
                    "client": "WEB",
                })
            )
            sell_url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get?"
                + urllib.parse.urlencode({
                    "reportName": "RPT_BILLBOARD_DAILYDETAILSSELL",
                    "columns": "ALL",
                    "pageNumber": 1,
                    "pageSize": 5,
                    "sortTypes": -1,
                    "sortColumns": "TRADE_DATE",
                    "filter": filter_expr,
                    "source": "WEB",
                    "client": "WEB",
                })
            )
            summary_url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get?"
                + urllib.parse.urlencode({
                    "reportName": "RPT_BILLBOARD_DAILYDETAILS",
                    "columns": "ALL",
                    "pageNumber": 1,
                    "pageSize": 1,
                    "sortTypes": -1,
                    "sortColumns": "TRADE_DATE",
                    "filter": filter_expr,
                    "source": "WEB",
                    "client": "WEB",
                })
            )
            buy_rows = json.loads(http_get(buy_url, timeout=4)).get("result", {}).get("data", []) or []

            sell_rows = json.loads(http_get(sell_url, timeout=4)).get("result", {}).get("data", []) or []

            sum_rows = json.loads(http_get(summary_url, timeout=4)).get("result", {}).get("data", []) or []

            if not buy_rows and not sell_rows and not sum_rows:
                return {
                    "source": "P3_Eastmoney_LHB_Details",
                    "data_status": "ok",
                    "symbol": symbol,
                    "status": "未上榜 / 近期无龙虎榜记录",
                    "explanation": "标的近期未触发龙虎榜披露标准 (日涨跌偏离度达7%或日换手达20%等)",
                }

            sum_item = sum_rows[0] if sum_rows else {}
            trade_date = (sum_item.get("TRADE_DATE") or (buy_rows[0].get("TRADE_DATE") if buy_rows else "近期"))[:10]

            def parse_seat(row):
                dept_name = row.get("OPERATEDEPT_NAME", "")
                buy_amt = round(safe_float(row.get("BUY"), 0.0) / 10000.0, 2)
                sell_amt = round(safe_float(row.get("SELL"), 0.0) / 10000.0, 2)
                net_amt = round(safe_float(row.get("NET"), 0.0) / 10000.0, 2)
                seat_type = "机构专用" if "机构" in dept_name else ("北向专用" if ("深股通" in dept_name or "沪股通" in dept_name) else "游资营业部")
                return {
                    "seat_name": dept_name,
                    "seat_type": seat_type,
                    "buy_wan": f"{buy_amt:+.2f} 万",
                    "sell_wan": f"{sell_amt:+.2f} 万",
                    "net_wan": f"{net_amt:+.2f} 万",
                }

            buyer_seats = [parse_seat(r) for r in buy_rows]
            seller_seats = [parse_seat(r) for r in sell_rows]

            # 机构专用席位净额: 买卖两榜合并到席位粒度再取 NET 合计 (单边 BUY/SELL 相减会丢失席位自身对冲)
            org_seats: Dict[str, Dict[str, float]] = {}
            for r in buy_rows + sell_rows:
                dept = r.get("OPERATEDEPT_NAME", "") or ""
                if "机构" not in dept:
                    continue
                cur = org_seats.setdefault(dept, {"buy": 0.0, "sell": 0.0, "net": 0.0})
                cur["buy"] += safe_float(r.get("BUY"), 0.0) or 0.0
                cur["sell"] += safe_float(r.get("SELL"), 0.0) or 0.0
                cur["net"] += safe_float(r.get("NET"), 0.0) or 0.0
            org_net_wan = round(sum(v["net"] for v in org_seats.values()) / 10000.0, 2)

            res = {
                "source": "P3_Eastmoney_LHB_Details",
                "data_status": "ok",
                "symbol": symbol,
                "name": sum_item.get("SECURITY_NAME_ABBR", symbol),
                "trade_date": trade_date,
                "explanation": sum_item.get("EXPLANATION", "上榜异动"),
                "total_lhb_buy_million": round(safe_float(sum_item.get("TOTAL_BUY"), 0.0) / 1000000.0, 2),
                "total_lhb_sell_million": round(safe_float(sum_item.get("TOTAL_SELL"), 0.0) / 1000000.0, 2),
                "total_lhb_net_million": round(safe_float(sum_item.get("TOTAL_NET"), 0.0) / 1000000.0, 2),
                "org_seat_net_wan": f"{org_net_wan:+.2f} 万元",
                "org_seat_count": len(org_seats),
                "org_seat_net_details": [
                    {
                        "seat_name": dept,
                        "buy_wan": f"{v['buy'] / 10000.0:+.2f} 万",
                        "sell_wan": f"{v['sell'] / 10000.0:+.2f} 万",
                        "net_wan": f"{v['net'] / 10000.0:+.2f} 万",
                    }
                    for dept, v in sorted(org_seats.items(), key=lambda kv: kv[1]["net"], reverse=True)
                ],
                "seat_quality_judgment": "机构席位净买入" if org_net_wan > 0 else ("机构席位净卖出" if org_net_wan < 0 else "未见机构席位净方向"),
                "seat_quality_note": "仅基于披露席位的机构专用净额，不推断外资、游资或散户资金性质。",
                "top5_buyers": buyer_seats,
                "top5_sellers": seller_seats,
            }
            set_cached(cache_key, res, ttl=ttl_for_history(trade_date))
            return res

        else:
            filter_expr = f"(TRADE_DATE='{norm_date}')" if norm_date else ""
            params = {
                "reportName": "RPT_BILLBOARD_DAILYDETAILS",
                "columns": "ALL",
                "pageNumber": 1,
                "pageSize": 20,
                "sortTypes": -1,
                "sortColumns": "TOTAL_NET",
                "source": "WEB",
                "client": "WEB",
            }
            if filter_expr:
                params["filter"] = filter_expr

            url = "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urllib.parse.urlencode(params)
            data_rows = json.loads(http_get(url, timeout=4)).get("result", {}).get("data", []) or []

            stocks = []
            for r in data_rows:
                net_amt_wan = round(safe_float(r.get("TOTAL_NET"), 0.0) / 10000.0, 2)
                stocks.append({
                    "code": r.get("SECURITY_CODE"),
                    "name": r.get("SECURITY_NAME_ABBR"),
                    "change_pct": f"{safe_float(r.get('CHANGE_RATE'), 0.0):+.2f}%",
                    "close_price": safe_float(r.get("CLOSE_PRICE"), 0.0),
                    "net_inflow_wan": f"{net_amt_wan:+.2f} 万",
                    "turnover_rate": f"{safe_float(r.get('TURNRATE'), 0.0):.2f}%",
                    "reason": r.get("EXPLANATION", ""),
                })

            res = {
                "source": "P3_Eastmoney_LHB_Daily_Summary",
                "data_status": "ok",
                "date": norm_date or (data_rows[0].get("TRADE_DATE", "")[:10] if data_rows else datetime.now().strftime("%Y-%m-%d")),
                "total_stocks_on_list": len(stocks),
                "top_net_buy_stocks": stocks[:10],
            }
            set_cached(cache_key, res, ttl=ttl_for_history(res["date"]))
            return res

    except Exception as e:
        return {"error": f"获取龙虎榜席位明细出错: {str(e)}"}


def fetch_company_quality(symbol: str) -> Dict[str, Any]:
    """
    获取 A 股个股基本面质量、财务指标、商誉、解禁与排雷数据
    直接满足 stock-analysis L8 公司质量与事件风险评估
    """
    clean_symbol = symbol.strip()
    code_only = clean_symbol.split(".")[0].replace("sh", "").replace("sz", "").replace("bj", "")
    cache_key = f"quality_{code_only}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        fina_url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            + urllib.parse.urlencode({
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "ALL",
                "pageNumber": 1,
                "pageSize": 2,
                "sortTypes": -1,
                "sortColumns": "REPORT_DATE",
                "filter": f'(SECURITY_CODE="{code_only}")',
                "source": "WEB",
                "client": "WEB",
            })
        )
        fina_rows = json.loads(http_get(fina_url, timeout=4)).get("result", {}).get("data", []) or []

        lift_url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            + urllib.parse.urlencode({
                "reportName": "RPT_LIFT_STAGE",
                "columns": "ALL",
                "pageNumber": 1,
                "pageSize": 5,
                "sortTypes": 1,
                "sortColumns": "FREE_DATE",
                "filter": f'(SECURITY_CODE="{code_only}")',
                "source": "WEB",
                "client": "WEB",
            })
        )
        lift_rows = json.loads(http_get(lift_url, timeout=4)).get("result", {}).get("data", []) or []

        balance_url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            + urllib.parse.urlencode({
                "reportName": "RPT_DMSK_FN_BALANCE",
                "columns": "ALL",
                "pageNumber": 1,
                "pageSize": 1,
                "sortTypes": -1,
                "sortColumns": "REPORT_DATE",
                "filter": f'(SECURITY_CODE="{code_only}")',
                "source": "WEB",
                "client": "WEB",
            })
        )
        balance_rows = json.loads(http_get(balance_url, timeout=4)).get("result", {}).get("data", []) or []

        f0 = fina_rows[0] if fina_rows else {}
        b0 = balance_rows[0] if balance_rows else {}

        report_period = f0.get("REPORT_DATE_NAME", "最新报告期")
        revenue_billion = round(safe_float(f0.get("TOTALOPERATEREVE"), 0.0) / 100000000.0, 2)
        revenue_yoy = f"{safe_float(f0.get('TOTALOPERATEREVETZ'), 0.0):+.2f}%"
        net_profit_million = round(safe_float(f0.get("PARENTNETPROFIT"), 0.0) / 10000.0, 2)
        net_profit_yoy = f"{safe_float(f0.get('PARENTNETPROFITTZ'), 0.0):+.2f}%"
        roe_weighted = f"{safe_float(f0.get('ROEJQ'), 0.0):.2f}%"
        gross_margin = f"{safe_float(f0.get('XSMLL'), 0.0):.2f}%"
        debt_ratio = f"{safe_float(f0.get('ZCFZL'), 0.0):.2f}%"
        operating_cashflow_per_share = round(safe_float(f0.get("MGJYXJJE"), 0.0), 2)

        goodwill_yuan = safe_float(b0.get("GOODWILL"), 0.0)
        total_equity_yuan = safe_float(b0.get("TOTAL_EQUITY"), 1.0)
        goodwill_million = round(goodwill_yuan / 10000.0, 2)
        goodwill_ratio = round((goodwill_yuan / total_equity_yuan) * 100.0, 2) if total_equity_yuan > 0 else 0.0

        future_lifts = []
        now_date = datetime.now().strftime("%Y-%m-%d")
        for lr in lift_rows:
            free_date_str = str(lr.get("FREE_DATE", ""))[:10]
            if free_date_str >= now_date:
                future_lifts.append({
                "lift_date": free_date_str,
                "lift_shares_wan": round(safe_float(lr.get("CURRENT_FREE_SHARES"), 0.0), 2),
                "ratio_of_total_shares": f"{(safe_float(lr.get('TOTAL_RATIO'), 0.0) * 100):.2f}%",
                "shares_type": lr.get("FREE_SHARES_TYPE", "首发原股东/定增"),
                    "is_future": True,
                })

        audit_opinion_status = "N/A（当前数据源未提供审计意见；需以年度审计报告或交易所公告核验）"

        debt_val = safe_float(f0.get("ZCFZL"), 0.0)
        risk_level = "待补充核验"
        risk_reasons = []
        if debt_val > 70:
            risk_level = "高"
            risk_reasons.append(f"资产负债率偏高 ({debt_ratio})")
        elif debt_val > 50:
            risk_level = "中"
            risk_reasons.append(f"资产负债率中等 ({debt_ratio})")
        if goodwill_ratio > 30:
            risk_level = "高"
            risk_reasons.append(f"商誉占净资产比例过高 ({goodwill_ratio}%)")
        if not risk_reasons:
            risk_reasons.append("仅完成负债率与商誉占比筛查；现金流、质押、减持、监管、诉讼及审计意见未覆盖")

        res = {
            "source": "P3_Eastmoney_Company_Quality_Gateway",
            "data_status": "partial",
            "symbol": symbol,
            "name": f0.get("SECURITY_NAME_ABBR", symbol),
            "report_period": report_period,
            "financial_summary": {
                "revenue_billion": f"{revenue_billion} 亿元",
                "revenue_yoy": revenue_yoy,
                "net_profit_wan": f"{net_profit_million} 万元",
                "net_profit_yoy": net_profit_yoy,
                "gross_margin": gross_margin,
                "weighted_roe": roe_weighted,
                "debt_to_assets_ratio": debt_ratio,
                "operating_cashflow_per_share": f"{operating_cashflow_per_share} 元",
            },
            "balance_and_goodwill": {
                "goodwill_million": f"{goodwill_million} 万元",
                "goodwill_to_equity_ratio": f"{goodwill_ratio:.2f}%",
                "inventory_million": f"{round(safe_float(b0.get('INVENTORY'), 0.0) / 10000.0, 2)} 万元",
            },
            "restricted_shares_lifting": future_lifts[:3],
            "audit_opinion_status": audit_opinion_status,
            "company_risk_level": risk_level,
            "company_risk_assessment": "；".join(risk_reasons),
            "uncovered_risks": ["审计意见", "股权质押", "股东减持", "监管问询/处罚", "诉讼仲裁", "退市风险"],
        }
        set_cached(cache_key, res, ttl=ttl_for_history(f0.get("REPORT_DATE")))
        return res

    except Exception as e:
        return {"error": f"获取公司质量排雷数据出错: {str(e)}"}


def fetch_stock_timeline(symbol: str) -> Dict[str, Any]:
    """
    获取 A 股个股当日分时走势全景、分时均线 (VWAP)、盘口放量脉冲与集合竞价数据
    支持数字代码或纯中文名称 (如 '301489', '贵州茅台')
    直供 market-prediction 竞价承接力研判与 stock-analysis 分时异动研判
    """
    ts_code = normalize_symbol(symbol)
    mkt = "1" if ts_code.startswith("sh") else "0"
    code = ts_code[2:] if len(ts_code) > 2 and ts_code.startswith(("sh", "sz", "bj")) else ts_code

    cache_key = f"timeline_{ts_code}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    secid = f"{mkt}.{code}"
    url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
    try:
        raw = http_get(url, timeout=4)
        res_json = json.loads(raw)
        data = res_json.get("data", {})
        if not data or not data.get("trends"):
            return {"error": f"未获取到 {symbol} 的分时走势数据"}

        trends = data.get("trends", [])
        pre_close = safe_float(data.get("preClose"), 0.0)
        stock_name = data.get("name", symbol)

        parsed_points = []
        max_price = -1.0
        min_price = 9999999.0
        max_time = ""
        min_time = ""
        morning_point = None

        for item in trends:
            parts = item.split(",")
            if len(parts) < 8:
                continue
            tm_str = parts[0]
            c_p = safe_float(parts[2], 0.0)
            h_p = safe_float(parts[3], 0.0)
            l_p = safe_float(parts[4], 0.0)
            vol_hand = safe_float(parts[5], 0.0)
            amt_yuan = safe_float(parts[6], 0.0)
            avg_p = safe_float(parts[7], 0.0)

            if "09:25" in tm_str:
                morning_point = {
                    "time": tm_str,
                    "auction_price": c_p,
                    "auction_change_pct": f"{((c_p - pre_close) / pre_close * 100):+.2f}%" if pre_close > 0 else "0.00%",
                }

            if h_p > max_price:
                max_price = h_p
                max_time = tm_str
            if l_p < min_price and l_p > 0:
                min_price = l_p
                min_time = tm_str

            parsed_points.append({
                "time": tm_str,
                "price": c_p,
                "volume": vol_hand,
                "amount": amt_yuan,
                "avg_price": avg_p,
            })

        if not parsed_points:
            return {"error": "分时数据点解析为空"}

        latest = parsed_points[-1]
        latest_price = latest["price"]
        latest_avg = latest["avg_price"]
        latest_change_pct = f"{((latest_price - pre_close) / pre_close * 100):+.2f}%" if pre_close > 0 else "0.00%"
        bias_to_avg = f"{((latest_price - latest_avg) / latest_avg * 100):+.2f}%" if latest_avg > 0 else "0.00%"

        sorted_by_amt = sorted(parsed_points, key=lambda x: x["amount"], reverse=True)
        top_surge = [
            {
                "time": p["time"],
                "price": p["price"],
                "minute_amount_million": f"{round(p['amount'] / 1000000.0, 2)} 百万",
                "avg_price": p["avg_price"],
            }
            for p in sorted_by_amt[:3]
        ]

        if latest_price > latest_avg and safe_float(latest_change_pct.rstrip('%')) > 0:
            timeline_status = "强势放量：全天站上分时均线上方运行"
        elif latest_price < latest_avg:
            timeline_status = "弱势承压：处于分时均线下方震荡"
        else:
            timeline_status = "震荡拉锯：紧贴分时均线缠绕"

        res = {
            "source": "P3_Eastmoney_Intraday_Timeline",
            "data_status": "ok",
            "symbol": code,
            "ts_code": ts_code,
            "name": stock_name,
            "pre_close": pre_close,
            "latest_price": latest_price,
            "change_pct": latest_change_pct,
            "intraday_avg_price": latest_avg,
            "bias_to_avg_line": bias_to_avg,
            "intraday_high": f"{max_price} ({max_time})",
            "intraday_low": f"{min_price} ({min_time})",
            "morning_call_auction": morning_point or "9:25 未录入",
            "intraday_strength_label": timeline_status,
            "volume_surge_moments": top_surge,
            "total_intraday_points": len(parsed_points),
        }
        set_cached(cache_key, res)
        return res
    except Exception as e:
        return {"error": f"获取分时走势失败: {str(e)}"}


# -----------------------------------------------------------------------------
# 3. 标准 MCP JSON-RPC 2.0 协议处理器 (stdio 管道)
# -----------------------------------------------------------------------------
SERVER_INFO = {
    "name": "marketgraph-data",
    "version": "1.8.0",
}

def _dispatch_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        return {"error": "arguments 必须是对象", "data_status": "unavailable"}
    if name in {"get_stock_quote", "get_stock_kline", "get_stock_timeline", "get_company_quality"}:
        if not isinstance(arguments.get("symbol"), str) or not arguments["symbol"].strip():
            return {"error": "symbol 必须是非空字符串", "data_status": "unavailable"}
    if name == "get_sector_kline":
        if not isinstance(arguments.get("sector"), str) or not arguments["sector"].strip():
            return {"error": "sector 必须是非空字符串", "data_status": "unavailable"}
        if arguments.get("count", 130) is not None and (not isinstance(arguments.get("count", 130), int) or not 20 <= arguments.get("count", 130) <= 250):
            return {"error": "count 必须是 20 至 250 的整数", "data_status": "unavailable"}
    if name == "get_sector_limit_quality":
        if not isinstance(arguments.get("sector"), str) or not arguments["sector"].strip():
            return {"error": "sector 必须是非空字符串", "data_status": "unavailable"}
    if name == "get_basket_index":
        stocks = arguments.get("stocks")
        if not isinstance(stocks, list) or len(stocks) < 2 or len(stocks) > 10 or not all(isinstance(s, str) and s.strip() for s in stocks):
            return {"error": "stocks 必须是 2 至 10 个非空字符串的数组", "data_status": "unavailable"}
        if arguments.get("count", 20) is not None and (not isinstance(arguments.get("count", 20), int) or not 5 <= arguments.get("count", 20) <= 60):
            return {"error": "count 必须是 5 至 60 的整数", "data_status": "unavailable"}
    if name == "get_sector_fund_flow" and (not isinstance(arguments.get("count", 20), int) or not 1 <= arguments.get("count", 20) <= 100):
        return {"error": "count 必须是 1 至 100 的整数", "data_status": "unavailable"}
    if name == "get_index_kline" and arguments.get("count", 5) is not None and (not isinstance(arguments.get("count", 5), int) or not 2 <= arguments.get("count", 5) <= 130):
        return {"error": "count 必须是 2 至 130 的整数", "data_status": "unavailable"}
    if name == "get_market_breadth" and arguments.get("days", 5) is not None and (not isinstance(arguments.get("days", 5), int) or not 2 <= arguments.get("days", 5) <= 10):
        return {"error": "days 必须是 2 至 10 的整数", "data_status": "unavailable"}
    if name == "get_index_kline" and arguments.get("indices") is not None and (
        not isinstance(arguments.get("indices"), list) or not all(isinstance(x, str) for x in arguments["indices"])
    ):
        return {"error": "indices 必须是字符串数组", "data_status": "unavailable"}
    if name == "get_stock_quote":
        return fetch_stock_quote(arguments.get("symbol", ""))
    elif name == "get_stock_kline":
        return fetch_stock_kline(
            arguments.get("symbol", ""),
            arguments.get("count", 750),
            arguments.get("compact", True)
        )
    elif name == "get_stock_timeline":
        return fetch_stock_timeline(arguments.get("symbol", ""))
    elif name == "get_market_sentiment":
        return fetch_market_sentiment(arguments.get("date_str"))
    elif name == "get_limit_up_ladder":
        return fetch_limit_up_ladder(arguments.get("date_str"))
    elif name == "get_sector_limit_quality":
        return fetch_sector_limit_quality(arguments.get("sector", ""), arguments.get("date_str"))
    elif name == "get_index_kline":
        return fetch_index_kline(arguments.get("indices"), arguments.get("count", 5))
    elif name == "get_market_breadth":
        return fetch_market_breadth(arguments.get("days", 5))
    elif name == "get_sector_fund_flow":
        return fetch_sector_fund_flow(arguments.get("count", 20), arguments.get("days", 1))
    elif name == "get_sector_kline":
        return fetch_sector_kline(arguments.get("sector", ""), arguments.get("count", 130))
    elif name == "get_basket_index":
        return fetch_basket_index(arguments.get("stocks", []), arguments.get("count", 20))
    elif name == "get_longhubang_detail":
        return fetch_longhubang_detail(arguments.get("symbol"), arguments.get("date_str"))
    elif name == "get_company_quality":
        return fetch_company_quality(arguments.get("symbol", ""))
    else:
        return {"error": f"未知工具: {name}"}


def response_envelope(result: Dict[str, Any]) -> Dict[str, Any]:
    """增加 v2 标准信封，同时保留旧顶层字段供已安装客户端兼容读取。"""
    legacy = dict(result) if isinstance(result, dict) else {"value": result}
    error = legacy.get("error")
    warnings = legacy.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [warnings]
    status = legacy.get("data_status") or ("unavailable" if error else "ok")
    source = str(legacy.get("source") or "marketgraph-data")
    as_of = legacy.get("as_of") or legacy.get("timestamp") or legacy.get("latest_date") or legacy.get("date")
    enriched = dict(legacy)
    enriched.update({
        "api_version": "2.0",
        "source": source,
        "data_status": status,
        "as_of": as_of,
        "data": legacy,
        "errors": [str(error)] if error else [],
        "warnings": list(warnings),
        "legacy_fields_retained": True,
    })
    return enriched


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return response_envelope(_dispatch_tool_call(name, arguments))


def run_stdio_server():
    """标准 MCP stdio 消息循环 (JSON-RPC 2.0)"""
    sys.stderr.write("[MarketGraph-MCP] 服务已启动，正在监听 stdio JSON-RPC...\n")
    sys.stderr.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue

        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}) + "\n")
            sys.stdout.flush()
            continue

        msg_id = req.get("id")
        method = req.get("method")

        # 1. 握手与初始化 (initialize)
        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": SERVER_INFO,
                },
            }
            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        # 2. 客户端完成通知 (notifications/initialized)
        elif method == "notifications/initialized":
            pass

        # 3. 列出工具 (tools/list)
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": AVAILABLE_TOOLS,
                },
            }
            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        # 4. 执行工具调用 (tools/call)
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            tool_res = handle_tool_call(name, arguments)

            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(tool_res, ensure_ascii=False, indent=2),
                        }
                    ],
                    "isError": "error" in tool_res,
                },
            }
            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        # 5. 心跳检测 (ping)
        elif method == "ping":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            }
            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        else:
            if msg_id is not None:
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()


# -----------------------------------------------------------------------------
# 4. 命令行直接测试模式 (方便开发者免配置验证)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        tool_name = sys.argv[2] if len(sys.argv) > 2 else "get_stock_quote"
        target_symbol = sys.argv[3] if len(sys.argv) > 3 else "300308"
        print(f"[*] 正在本地直接调试工具: {tool_name} (标的: {target_symbol})")
        if tool_name == "get_stock_quote":
            out = fetch_stock_quote(target_symbol)
        elif tool_name == "get_stock_kline":
            is_compact = True if len(sys.argv) <= 4 or sys.argv[4] != "full" else False
            out = fetch_stock_kline(target_symbol, 750, compact=is_compact)
        elif tool_name == "get_stock_timeline":
            out = fetch_stock_timeline(target_symbol)
        elif tool_name == "get_market_sentiment":
            out = fetch_market_sentiment()
        elif tool_name == "get_limit_up_ladder":
            out = fetch_limit_up_ladder()
        elif tool_name == "get_sector_limit_quality":
            # --test 默认标的是个股代码, 板块工具需独立默认板块名
            out = fetch_sector_limit_quality(sys.argv[3] if len(sys.argv) > 3 else "半导体")
        elif tool_name == "get_index_kline":
            out = fetch_index_kline()
        elif tool_name == "get_market_breadth":
            out = fetch_market_breadth()
        elif tool_name == "get_sector_fund_flow":
            days = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 1
            out = fetch_sector_fund_flow(10 if days > 1 else 20, days)
        elif tool_name == "get_sector_kline":
            # --test 默认标的是个股代码, 板块工具需独立默认板块名
            out = fetch_sector_kline(sys.argv[3] if len(sys.argv) > 3 else "半导体")
        elif tool_name == "get_basket_index":
            default_stocks = ["601318", "601628", "601601", "601366"]  # 保险板块四大成分
            stocks = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3].strip() else default_stocks
            out = fetch_basket_index(stocks)
        elif tool_name == "get_longhubang_detail":
            out = fetch_longhubang_detail(target_symbol)
        elif tool_name == "get_company_quality":
            out = fetch_company_quality(target_symbol)
        else:
            out = {"error": "未知工具"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        run_stdio_server()
