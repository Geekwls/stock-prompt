#!/usr/bin/env python3
"""
MarketGraph Financial MCP Server (Zero-Config, Protocol 1.0 Ready)
==================================================================
跨智能体通用 A 股金融数据 MCP 服务端 (Agent Plugins 1.0 标准)
- 零注册、免 Token、零第三方重依赖 (基于 Python 3.8+ 标准库)
- 主干直连腾讯证券 CDN (毫秒级实时盘口、估值、120日前复权K线与ATR)
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
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# -----------------------------------------------------------------------------
# 1. 基础配置与轻量内存缓存 (TTL Cache，防止频繁请求)
# -----------------------------------------------------------------------------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CACHE_STORE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 180  # 盘中常规缓存 3 分钟
MAX_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
ALLOWED_HTTP_HOSTS = {
    "smartbox.gtimg.cn", "qt.gtimg.cn", "web.ifzq.gtimg.cn",
    "push2ex.eastmoney.com", "push2.eastmoney.com", "datacenter-web.eastmoney.com",
}


def get_cached(key: str) -> Optional[Any]:
    record = CACHE_STORE.get(key)
    if not record:
        return None
    if time.time() - record["time"] < record["ttl"]:
        return record["data"]
    del CACHE_STORE[key]
    return None


def set_cached(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS):
    CACHE_STORE[key] = {"data": data, "time": time.time(), "ttl": ttl}


def http_get(url: str, timeout: int = 4, encoding: str = "utf-8") -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HTTP_HOSTS:
        raise ValueError("仅允许访问预设的 HTTPS 金融数据源")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read(MAX_HTTP_RESPONSE_BYTES + 1)
        if len(content) > MAX_HTTP_RESPONSE_BYTES:
            raise ValueError("上游响应超过大小限制")
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            return content.decode("gbk", errors="ignore")


def resolve_symbol_by_name(keyword: str) -> Optional[str]:
    """通过智能证券联想网关，将纯中文股票名称解析为标准代码 (如 '贵州茅台' -> 'sh600519')"""
    clean = keyword.strip()
    cache_key = f"symbol_lookup_{clean}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = f"https://smartbox.gtimg.cn/s3/?t=all&q={urllib.parse.quote(clean)}"
    try:
        raw = http_get(url, timeout=3, encoding="gbk")
        if '="' in raw:
            val = raw.split('="')[1].rstrip('";\n ')
            items = val.split("^")
            for item in items:
                parts = item.split("~")
                if len(parts) >= 3:
                    mkt, code, name = parts[0], parts[1], parts[2]
                    if mkt in ("sh", "sz", "bj"):
                        res = f"{mkt}{code}"
                        set_cached(cache_key, res, ttl=86400)
                        return res
    except Exception:
        pass
    return None


def normalize_symbol(symbol: str) -> str:
    """标准化证券代码为腾讯前缀格式: sh600519, sz300308, bj830000；支持纯中文名称自动解析"""
    clean = symbol.strip().lower()
    if clean.startswith(("sh", "sz", "bj")) and len(clean) >= 8 and clean[2:].isdigit():
        return clean
    if "." in clean:
        parts = clean.split(".")
        if len(parts) == 2:
            if parts[1] in ("sh", "sz", "bj"):
                return f"{parts[1]}{parts[0]}"
            if parts[0] in ("sh", "sz", "bj"):
                return f"{parts[0]}{parts[1]}"
    code = clean.split(".")[0]
    if code.isdigit():
        if code.startswith(("6", "9", "5", "11")):
            return f"sh{code}"
        elif code.startswith(("0", "3", "12", "15", "16", "18")):
            return f"sz{code}"
        elif code.startswith(("4", "8")):
            return f"bj{code}"
    # 若非纯数字代码，尝试中文名称联想解析
    resolved = resolve_symbol_by_name(symbol)
    if resolved:
        return resolved
    return clean


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


def compute_wyckoff_signals(
    bars: List[Dict[str, Any]],
    ma20: float,
    ma50: float,
    ma120: Optional[float],
    ma250: Optional[float],
    atr14: float,
    latest_close: float,
    bias_ma20: float,
    high_year: float,
    low_year: float,
) -> Dict[str, Any]:
    """预计算双层威科夫时空模型（宏观大周期定性 + 微观量价结构），消除大模型数值对比幻觉"""
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

    # 1. 宏观威科夫大周期定调 (Macro Wyckoff Phase, 基于年线/半年线与年内分位点)
    year_range = high_year - low_year if high_year > low_year else 1.0
    year_percentile = round((latest_close - low_year) / year_range * 100, 1)

    bias_ma250 = round((latest_close - ma250) / ma250 * 100, 2) if ma250 else None
    bias_ma120 = round((latest_close - ma120) / ma120 * 100, 2) if ma120 else None

    if ma250 and ma120:
        if latest_close > ma250 and ma120 >= ma250 * 0.98 and year_percentile >= 50.0:
            macro_phase = "STAGE_2_MARKUP_BULLISH"  # 大级别牛市主升浪 (站稳年线上方)
        elif latest_close < ma250 and ma120 <= ma250 * 1.02 and year_percentile <= 45.0:
            macro_phase = "STAGE_4_MARKDOWN_BEARISH"  # 大级别空头阴跌通道 (年线压制)
        elif year_percentile <= 25.0:
            macro_phase = "STAGE_1_MACRO_ACCUMULATION"  # 1~2年历史大底吸筹区 (沉淀筑底)
        elif year_percentile >= 80.0:
            macro_phase = "STAGE_3_MACRO_DISTRIBUTION"  # 1~2年高位筹码派发区 (筑顶风险)
        else:
            macro_phase = "STAGE_REACCUMULATION_OR_CONSOLIDATION"  # 宏观大中继整理区
    else:
        macro_phase = "STAGE_1_MACRO_ACCUMULATION" if year_percentile <= 30.0 else "STAGE_2_MARKUP_BULLISH"

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

    return {
        "macro_wyckoff_phase": macro_phase,
        "year_price_percentile": f"{year_percentile}%",
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
            f"宏观阶段: {macro_phase} (年内分位: {year_percentile}%, 年线乖离: {bias_ma250 if bias_ma250 is not None else 'N/A'}%); "
            f"60日箱体: {tr_location} ({tr_position_pct}%位置); "
            f"量能: {'地量萎缩' if volume_dry_up else ('放量异动' if volume_expansion else '量能平稳')}({vol_ratio_to_ma20}x MA20); "
            f"形态: {'[Spring测试]' if spring_detected else ''}{'[UT假突破风险]' if upthrust_detected else ''}{'[筹码紧凑吸收]' if absorption_detected else ''}{'无异常形态' if not (spring_detected or upthrust_detected or absorption_detected) else ''}"
        ),
    }


def fetch_stock_kline(symbol: str, count: int = 250, compact: bool = True) -> Dict[str, Any]:
    """
    获取 250 日 (1年) 至 500 日 (2年) 前复权日K线、全套均线矩阵 (MA20/50/120/250) 与双层威科夫时空模型
    默认开启 compact=True 瘦身模式（保留核心统计与最近30日K线，兼顾微观博弈与宏观全景），直接满足行情硬门槛
    """
    ts_code = normalize_symbol(symbol)
    cache_key = f"kline_{ts_code}_{count}_{compact}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    if not isinstance(count, int) or not 20 <= count <= 500:
        return {"error": "count 必须是 20 至 500 的整数", "data_status": "unavailable"}
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

        # 计算全周期均线矩阵: MA20 / MA50 / MA120 (半年线) / MA250 (年线)
        ma20 = sum(closes[-20:]) / min(20, valid_count) if valid_count >= 5 else closes[-1]
        ma50 = sum(closes[-50:]) / min(50, valid_count) if valid_count >= 10 else closes[-1]
        ma120 = round(sum(closes[-120:]) / 120.0, 2) if valid_count >= 100 else None
        ma250 = round(sum(closes[-250:]) / 250.0, 2) if valid_count >= 200 else None

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

        # 1年与2年高低区间
        high_year = max(highs[-min(250, valid_count):])
        low_year = min(lows[-min(250, valid_count):])

        # 预计算双层威科夫宏观与微观信号
        wyckoff_signals = compute_wyckoff_signals(
            bars, ma20, ma50, ma120, ma250, atr14, latest_close, bias_ma20, high_year, low_year
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
            "bias_ma20": f"{bias_ma20:+.2f}%",
            "bias_ma50": f"{bias_ma50:+.2f}%",
            "bias_ma250_year": wyckoff_signals["bias_ma250"],
            "atr14": round(atr14, 2),
            "atr14_pct": f"{(atr14 / latest_close * 100):.2f}%",
            "high_120": max(highs[-min(120, valid_count):]),
            "low_120": min(lows[-min(120, valid_count):]),
            "high_year": high_year,
            "low_year": low_year,
            "recent_5d_return": f"{((closes[-1] - closes[-min(5, valid_count)]) / closes[-min(5, valid_count)] * 100):+.2f}%",
            "recent_20d_return": f"{((closes[-1] - closes[-min(20, valid_count)]) / closes[-min(20, valid_count)] * 100):+.2f}%",
            "wyckoff_multi_timeframe": wyckoff_signals,
            "bars_summary": f"已检验 {valid_count} 根前复权日K线 (含半年线MA120/年线MA250宏观视界)，完全通过行情硬门槛" + (" [精简视图：附最近30日K线]" if compact else " [完整视图：附全量K线]"),
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


def fetch_market_sentiment(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    获取全市场情绪与量能总定调 (涨停数、炸板数、精确全市场炸板率、两市总成交额)
    直供 daily-review L1 情绪引擎与 market-prediction E4 量价簇
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")

    cache_key = f"sentiment_{date_str}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    # 1. 抓取东方财富公开打板专题池 (免密 CDN)
    zt_count = 0
    zb_count = 0
    dt_count = 0
    max_height = 0
    headers = {"User-Agent": USER_AGENT}
    unavailable_sources: List[str] = []

    try:
        # 涨停池
        zt_url = f"https://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
        req_zt = urllib.request.Request(zt_url, headers=headers)
        with urllib.request.urlopen(req_zt, timeout=4) as resp:
            zt_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            zt_count = len(zt_data)
            if zt_data:
                max_height = max([int(x.get("lbc", 1)) for x in zt_data])
    except Exception as exc:
        unavailable_sources = [f"涨停池: {type(exc).__name__}"]

    try:
        # 炸板池
        zb_url = f"https://push2ex.eastmoney.com/getTopicZBPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
        req_zb = urllib.request.Request(zb_url, headers=headers)
        with urllib.request.urlopen(req_zb, timeout=4) as resp:
            zb_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            zb_count = len(zb_data)
    except Exception as exc:
        unavailable_sources.append(f"炸板池: {type(exc).__name__}")

    try:
        # 跌停池
        dt_url = f"https://push2ex.eastmoney.com/getTopicDTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fund:asc&date={date_str}"
        req_dt = urllib.request.Request(dt_url, headers=headers)
        with urllib.request.urlopen(req_dt, timeout=4) as resp:
            dt_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            dt_count = len(dt_data)
    except Exception as exc:
        unavailable_sources.append(f"跌停池: {type(exc).__name__}")

    # 2. 抓取腾讯大盘指数成交额 (上证 + 深证)
    sh_amount = 0.0
    sz_amount = 0.0
    sh_change = "0.00%"
    try:
        idx_url = "https://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006"
        idx_raw = http_get(idx_url)
        lines = [line for line in idx_raw.split(";") if line.strip()]
        for line in lines:
            if "s_sh000001" in line:
                p = line.split("~")
                sh_change = f"{float(p[5].strip('\\\"')):+.2f}%"
                sh_amount = float(p[9].strip('\\\"')) / 10000.0  # 亿元
            elif "s_sz399001" in line:
                p = line.split("~")
                sz_amount = float(p[9].strip('\\\"')) / 10000.0  # 亿元
    except Exception as exc:
        unavailable_sources.append(f"指数成交额: {type(exc).__name__}")

    if unavailable_sources:
        return {
            "source": "P3_Public_Financial_Gateways",
            "data_status": "partial",
            "date": date_str,
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
        "date": date_str,
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
    set_cached(cache_key, res)
    return res


def fetch_limit_up_ladder(date_str: Optional[str] = None) -> Dict[str, Any]:
    """获取 A 股连板天梯矩阵 (各板高度代表票与晋级梯队)"""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")

    cache_key = f"ladder_{date_str}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = f"https://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])

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
            "date": date_str,
            "total_limit_up": len(data),
            "max_height": max(ladder.keys()) if ladder else 0,
            "ladder_distribution": summary,
        }
        set_cached(cache_key, res)
        return res
    except Exception as e:
        return {"error": f"获取连板天梯失败: {str(e)}"}


def fetch_sector_fund_flow(count: int = 20) -> Dict[str, Any]:
    """
    获取 A 股全行业板块主力资金流向、涨跌幅排行与领涨龙头
    直供 daily-review L2 强势板块定位与 sector-rotation 5日资金迁移分析
    """
    cache_key = f"sector_fund_flow_{count}"
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

    cache_key = f"lhb_{code_only}_{date_str or 'latest'}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    headers = {"User-Agent": USER_AGENT}
    try:
        if code_only:
            filter_expr = f'(SECURITY_CODE="{code_only}")'
            if date_str:
                normalized_date = date_str.replace("-", "")
                if len(normalized_date) != 8 or not normalized_date.isdigit():
                    return {"error": "date_str 必须为 YYYYMMDD 或 YYYY-MM-DD", "data_status": "unavailable"}
                filter_expr += f'(TRADE_DATE=\'{normalized_date[:4]}-{normalized_date[4:6]}-{normalized_date[6:]}\')'
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
            req_b = urllib.request.Request(buy_url, headers=headers)
            with urllib.request.urlopen(req_b, timeout=4) as resp_b:
                buy_rows = json.loads(resp_b.read().decode("utf-8")).get("result", {}).get("data", []) or []

            req_s = urllib.request.Request(sell_url, headers=headers)
            with urllib.request.urlopen(req_s, timeout=4) as resp_s:
                sell_rows = json.loads(resp_s.read().decode("utf-8")).get("result", {}).get("data", []) or []

            req_sum = urllib.request.Request(summary_url, headers=headers)
            with urllib.request.urlopen(req_sum, timeout=4) as resp_sum:
                sum_rows = json.loads(resp_sum.read().decode("utf-8")).get("result", {}).get("data", []) or []

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

            org_buy = sum(safe_float(r.get("BUY"), 0.0) for r in buy_rows if "机构" in r.get("OPERATEDEPT_NAME", ""))
            org_sell = sum(safe_float(r.get("SELL"), 0.0) for r in sell_rows if "机构" in r.get("OPERATEDEPT_NAME", ""))
            org_net_wan = round((org_buy - org_sell) / 10000.0, 2)

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
                "seat_quality_judgment": "机构席位净买入" if org_net_wan > 0 else ("机构席位净卖出" if org_net_wan < 0 else "未见机构席位净方向"),
                "seat_quality_note": "仅基于披露席位的机构专用净额，不推断外资、游资或散户资金性质。",
                "top5_buyers": buyer_seats,
                "top5_sellers": seller_seats,
            }
            set_cached(cache_key, res)
            return res

        else:
            filter_expr = f'(TRADE_DATE=\'{date_str}\')' if date_str else ""
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
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                data_rows = json.loads(resp.read().decode("utf-8")).get("result", {}).get("data", []) or []

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
                "date": date_str or (data_rows[0].get("TRADE_DATE", "")[:10] if data_rows else datetime.now().strftime("%Y-%m-%d")),
                "total_stocks_on_list": len(stocks),
                "top_net_buy_stocks": stocks[:10],
            }
            set_cached(cache_key, res)
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

    headers = {"User-Agent": USER_AGENT}
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
        req_f = urllib.request.Request(fina_url, headers=headers)
        with urllib.request.urlopen(req_f, timeout=4) as resp_f:
            fina_rows = json.loads(resp_f.read().decode("utf-8")).get("result", {}).get("data", []) or []

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
        req_l = urllib.request.Request(lift_url, headers=headers)
        with urllib.request.urlopen(req_l, timeout=4) as resp_l:
            lift_rows = json.loads(resp_l.read().decode("utf-8")).get("result", {}).get("data", []) or []

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
        req_b = urllib.request.Request(balance_url, headers=headers)
        with urllib.request.urlopen(req_b, timeout=4) as resp_b:
            balance_rows = json.loads(resp_b.read().decode("utf-8")).get("result", {}).get("data", []) or []

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
        set_cached(cache_key, res)
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
    "version": "1.2.1",
}

AVAILABLE_TOOLS = [
    {
        "name": "get_stock_quote",
        "description": "获取 A 股个股实时行情、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口（支持代码或中文名，毫秒级直连）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或简称，例如 '300308', '000938.SZ', 'sh600519', '贵州茅台'",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_kline",
        "description": "获取 A 股个股 250 日 (1年) 乃至 500 日 (2年) 连续前复权日K线、全套均线矩阵 (MA20/50/120/250) 与双层威科夫时空模型（宏观牛熊阶段+微观60日交易区间）（支持代码或中文名，完全满足行情硬门槛）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '300308', '中际旭创'",
                },
                "count": {
                    "type": "integer",
                    "description": "K 线根数，默认 250 (1年，含年线MA250/半年线MA120)；可设为 500 查看2年大级别筑底周期",
                    "default": 250,
                    "minimum": 20,
                    "maximum": 500,
                },
                "compact": {
                    "type": "boolean",
                    "description": "是否开启 Token 瘦身精简模式（默认 true，附最近30日K线与核心指标，节省80% Token；传 false 则返回 250 根全量日线数组）",
                    "default": True,
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_timeline",
        "description": "获取 A 股个股当日分时全景、分时均价线 (VWAP)、盘中量能脉冲时刻与 9:25 集合竞价承接力（支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '贵州茅台', '中际旭创'",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_sentiment",
        "description": "获取全市场情绪总分指标（两市成交总额、涨停家数、炸板家数、真实炸板率、最高连板高度）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "日期字符串，格式 YYYYMMDD，省略则为当天",
                    "pattern": "^[0-9]{8}$",
                }
            },
        },
    },
    {
        "name": "get_limit_up_ladder",
        "description": "获取今日或指定交易日的 A 股连板天梯分布（各连板高度数量、领航龙头标的与所属行业）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "日期字符串，格式 YYYYMMDD，省略则为当天",
                    "pattern": "^[0-9]{8}$",
                }
            },
        },
    },
    {
        "name": "get_sector_fund_flow",
        "description": "获取 A 股全行业板块主力资金净流入榜、流出榜、涨幅榜、跌幅榜及领涨龙头股票（直供复盘与轮动）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "返回的行业板块数量，默认 20",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                }
            },
        },
    },
    {
        "name": "get_longhubang_detail",
        "description": "获取 A 股交易所公开龙虎榜席位明细（全市场当日上榜概览或指定个股前5大买卖席位穿透，支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '思泉新材'，省略时返回全市场龙虎榜概览",
                },
                "date_str": {
                    "type": "string",
                    "description": "交易日期 YYYYMMDD 或 YYYY-MM-DD，省略则为最新交易日",
                    "pattern": "^[0-9]{8}$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                },
            },
        },
    },
    {
        "name": "get_company_quality",
        "description": "获取 A 股个股基本面质量财务指标（营收/净利同比、ROE、毛利率、负债率）、商誉占比、限售解禁日与审计意见状态（支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '思泉新材'",
                }
            },
            "required": ["symbol"],
        },
    },
]


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        return {"error": "arguments 必须是对象", "data_status": "unavailable"}
    if name in {"get_stock_quote", "get_stock_kline", "get_stock_timeline", "get_company_quality"}:
        if not isinstance(arguments.get("symbol"), str) or not arguments["symbol"].strip():
            return {"error": "symbol 必须是非空字符串", "data_status": "unavailable"}
    if name == "get_sector_fund_flow" and (not isinstance(arguments.get("count", 20), int) or not 1 <= arguments.get("count", 20) <= 100):
        return {"error": "count 必须是 1 至 100 的整数", "data_status": "unavailable"}
    if name == "get_stock_quote":
        return fetch_stock_quote(arguments.get("symbol", ""))
    elif name == "get_stock_kline":
        return fetch_stock_kline(
            arguments.get("symbol", ""),
            arguments.get("count", 250),
            arguments.get("compact", True)
        )
    elif name == "get_stock_timeline":
        return fetch_stock_timeline(arguments.get("symbol", ""))
    elif name == "get_market_sentiment":
        return fetch_market_sentiment(arguments.get("date_str"))
    elif name == "get_limit_up_ladder":
        return fetch_limit_up_ladder(arguments.get("date_str"))
    elif name == "get_sector_fund_flow":
        return fetch_sector_fund_flow(arguments.get("count", 20))
    elif name == "get_longhubang_detail":
        return fetch_longhubang_detail(arguments.get("symbol"), arguments.get("date_str"))
    elif name == "get_company_quality":
        return fetch_company_quality(arguments.get("symbol", ""))
    else:
        return {"error": f"未知工具: {name}"}


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
            out = fetch_stock_kline(target_symbol, 250, compact=is_compact)
        elif tool_name == "get_stock_timeline":
            out = fetch_stock_timeline(target_symbol)
        elif tool_name == "get_market_sentiment":
            out = fetch_market_sentiment()
        elif tool_name == "get_limit_up_ladder":
            out = fetch_limit_up_ladder()
        elif tool_name == "get_sector_fund_flow":
            out = fetch_sector_fund_flow()
        elif tool_name == "get_longhubang_detail":
            out = fetch_longhubang_detail(target_symbol)
        elif tool_name == "get_company_quality":
            out = fetch_company_quality(target_symbol)
        else:
            out = {"error": "未知工具"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        run_stdio_server()
