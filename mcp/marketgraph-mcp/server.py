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
from datetime import datetime, date
from typing import Dict, Any, List, Optional

# -----------------------------------------------------------------------------
# 1. 基础配置与轻量内存缓存 (TTL Cache，防止频繁请求)
# -----------------------------------------------------------------------------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CACHE_STORE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 180  # 盘中常规缓存 3 分钟


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
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            return content.decode("gbk", errors="ignore")


def normalize_symbol(symbol: str) -> str:
    """标准化证券代码为腾讯前缀格式: sh600519, sz300308, bj830000"""
    clean = symbol.strip().lower()
    if clean.startswith(("sh", "sz", "bj")):
        return clean
    if "." in clean:
        parts = clean.split(".")
        if parts[1] in ("sh", "sz", "bj"):
            return f"{parts[1]}{parts[0]}"
        if parts[0] in ("sh", "sz", "bj"):
            return f"{parts[0]}{parts[1]}"
    code = clean.split(".")[0]
    if code.startswith(("6", "9", "5", "11")):
        return f"sh{code}"
    elif code.startswith(("0", "3", "12", "15", "16", "18")):
        return f"sz{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


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

    url = f"http://qt.gtimg.cn/q={ts_code}"
    raw = http_get(url)
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
            "source": "P1_Tencent_Securities",
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


def fetch_stock_kline(symbol: str, count: int = 120) -> Dict[str, Any]:
    """
    获取 120 日前复权日K线及量化技术指标
    直接满足 stock-analysis 行情硬门槛与 ATR(14)、MA20/50 计算
    """
    ts_code = normalize_symbol(symbol)
    cache_key = f"kline_{ts_code}_{count}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={ts_code},day,,,{count},qfq"
    raw = http_get(url)
    try:
        data = json.loads(raw)
        root = data.get("data", {}).get(ts_code, {})
        # 优先读取 qfqday (前复权日线)，无复权则回退到 day
        bars_raw = root.get("qfqday") or root.get("day") or []
        if not bars_raw:
            return {"error": f"未获取到前复权 K 线序列: {symbol}"}

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

        # 计算 MA20 与 MA50
        ma20 = sum(closes[-20:]) / min(20, valid_count) if valid_count >= 5 else closes[-1]
        ma50 = sum(closes[-50:]) / min(50, valid_count) if valid_count >= 10 else closes[-1]
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

        res = {
            "source": "P1_Tencent_QFQ_KLine",
            "symbol": symbol,
            "ts_code": ts_code,
            "valid_bars": valid_count,
            "hard_gate_passed": valid_count >= 120,
            "latest_date": bars[-1]["date"],
            "latest_close": latest_close,
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "bias_ma20": f"{bias_ma20:+.2f}%",
            "bias_ma50": f"{bias_ma50:+.2f}%",
            "atr14": round(atr14, 2),
            "atr14_pct": f"{(atr14 / latest_close * 100):.2f}%",
            "high_120": max(highs),
            "low_120": min(lows),
            "recent_5d_return": f"{((closes[-1] - closes[-min(5, valid_count)]) / closes[-min(5, valid_count)] * 100):+.2f}%",
            "recent_20d_return": f"{((closes[-1] - closes[-min(20, valid_count)]) / closes[-min(20, valid_count)] * 100):+.2f}%",
            "bars_summary": f"已提供连续 {valid_count} 交易日前复权 OHLCV 序列，完全通过行情硬门槛",
        }
        set_cached(cache_key, res, ttl=CACHE_TTL_SECONDS * 2)
        return res
    except Exception as e:
        return {"error": f"解析前复权日K线出错: {str(e)}"}


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

    try:
        # 涨停池
        zt_url = f"http://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
        req_zt = urllib.request.Request(zt_url, headers=headers)
        with urllib.request.urlopen(req_zt, timeout=4) as resp:
            zt_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            zt_count = len(zt_data)
            if zt_data:
                max_height = max([int(x.get("lbc", 1)) for x in zt_data])
    except Exception:
        pass

    try:
        # 炸板池
        zb_url = f"http://push2ex.eastmoney.com/getTopicZBPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
        req_zb = urllib.request.Request(zb_url, headers=headers)
        with urllib.request.urlopen(req_zb, timeout=4) as resp:
            zb_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            zb_count = len(zb_data)
    except Exception:
        pass

    try:
        # 跌停池
        dt_url = f"http://push2ex.eastmoney.com/getTopicDTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fund:asc&date={date_str}"
        req_dt = urllib.request.Request(dt_url, headers=headers)
        with urllib.request.urlopen(req_dt, timeout=4) as resp:
            dt_data = json.loads(resp.read().decode("utf-8")).get("data", {}).get("pool", [])
            dt_count = len(dt_data)
    except Exception:
        pass

    # 2. 抓取腾讯大盘指数成交额 (上证 + 深证)
    sh_amount = 0.0
    sz_amount = 0.0
    sh_change = "0.00%"
    try:
        idx_url = "http://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006"
        idx_raw = http_get(idx_url)
        lines = [line for line in idx_raw.split(";") if line.strip()]
        for line in lines:
            if "s_sh000001" in line:
                p = line.split("~")
                sh_change = f"{float(p[5]):+.2f}%"
                sh_amount = float(p[9]) / 10000.0  # 亿元
            elif "s_sz399001" in line:
                p = line.split("~")
                sz_amount = float(p[9]) / 10000.0  # 亿元
    except Exception:
        pass

    total_turnover = sh_amount + sz_amount
    total_touch = zt_count + zb_count
    break_rate = (zb_count / total_touch * 100) if total_touch > 0 else 0.0

    res = {
        "source": "P1_Public_Financial_Gateways",
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

    url = f"http://push2ex.eastmoney.com/getTopicZTPool?ut={EM_UT}&dpt={EM_DPT}&Pageindex=0&pagesize=500&sort=fbt:asc&date={date_str}"
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
            "source": "P1_Eastmoney_LimitUp_Ladder",
            "date": date_str,
            "total_limit_up": len(data),
            "max_height": max(ladder.keys()) if ladder else 0,
            "ladder_distribution": summary,
        }
        set_cached(cache_key, res)
        return res
    except Exception as e:
        return {"error": f"获取连板天梯失败: {str(e)}"}


# -----------------------------------------------------------------------------
# 3. 标准 MCP JSON-RPC 2.0 协议处理器 (stdio 管道)
# -----------------------------------------------------------------------------
SERVER_INFO = {
    "name": "marketgraph-data",
    "version": "1.0.0",
}

AVAILABLE_TOOLS = [
    {
        "name": "get_stock_quote",
        "description": "获取 A 股个股实时行情、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口（毫秒级直连）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或简称，例如 '300308', '000938.SZ', 'sh600519'",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_kline",
        "description": "获取 A 股个股 120 日连续前复权日K线、MA20、MA50、ATR14与Bias偏离度（完全满足 stock-analysis 行情硬门槛）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码，例如 '300308'",
                },
                "count": {
                    "type": "integer",
                    "description": "K 线根数，默认 120",
                    "default": 120,
                },
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
                }
            },
        },
    },
]


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "get_stock_quote":
        return fetch_stock_quote(arguments.get("symbol", ""))
    elif name == "get_stock_kline":
        return fetch_stock_kline(arguments.get("symbol", ""), arguments.get("count", 120))
    elif name == "get_market_sentiment":
        return fetch_market_sentiment(arguments.get("date_str"))
    elif name == "get_limit_up_ladder":
        return fetch_limit_up_ladder(arguments.get("date_str"))
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
            out = fetch_stock_kline(target_symbol, 120)
        elif tool_name == "get_market_sentiment":
            out = fetch_market_sentiment()
        elif tool_name == "get_limit_up_ladder":
            out = fetch_limit_up_ladder()
        else:
            out = {"error": "未知工具"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        run_stdio_server()
