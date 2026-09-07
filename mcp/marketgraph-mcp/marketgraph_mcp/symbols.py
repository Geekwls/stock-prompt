"""证券代码、指数别名与日期的归一化解析。"""

import urllib.parse
from typing import List, Optional

from .cache import get_cached, set_cached
from .transport import http_get


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


def normalize_date_str(date_str: Optional[str]) -> Optional[str]:
    """将 YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD 统一归一化为 YYYY-MM-DD；非法输入返回 None"""
    if not date_str:
        return None
    clean = str(date_str).strip().replace("-", "").replace("/", "")
    if len(clean) == 8 and clean.isdigit():
        return f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"
    return None


# 核心指数体系: 标准 key -> (腾讯代码, 中文名)
INDEX_ALIASES = {
    "SHCI": ("sh000001", "上证指数"),
    "SZCI": ("sz399001", "深证成指"),
    "CYB": ("sz399006", "创业板指"),
    "CSIALL": ("sh000985", "中证全指"),
    "HS300": ("sh000300", "沪深300"),
}
INDEX_NAME_TO_KEY = {
    "上证指数": "SHCI", "上证": "SHCI", "沪指": "SHCI", "沪综指": "SHCI",
    "深证成指": "SZCI", "深成指": "SZCI",
    "创业板指": "CYB", "创业板": "CYB",
    "中证全指": "CSIALL", "全指": "CSIALL",
    "沪深300": "HS300", "沪深三百": "HS300",
}


def resolve_index_keys(indices: Optional[List[str]]) -> List[str]:
    """把用户输入的指数列表 (标准key/中文别名) 解析为去重后的标准 key 列表；空输入返回默认四大指数"""
    if not indices:
        return ["SHCI", "SZCI", "CYB", "CSIALL"]
    keys: List[str] = []
    for raw in indices:
        if not isinstance(raw, str) or not raw.strip():
            continue
        token = raw.strip()
        key = token.upper() if token.upper() in INDEX_ALIASES else INDEX_NAME_TO_KEY.get(token)
        if key and key not in keys:
            keys.append(key)
    return keys
