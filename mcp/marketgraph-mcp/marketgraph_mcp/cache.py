"""轻量内存 TTL 缓存。"""

import time
from datetime import datetime
from typing import Any, Dict, Optional


CACHE_TTL_SECONDS = 180
HISTORICAL_CACHE_TTL_SECONDS = 86400
CACHE_STORE: Dict[str, Dict[str, Any]] = {}


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


def ttl_for_history(latest_date_str: Optional[str]) -> int:
    try:
        if latest_date_str and str(latest_date_str)[:10] < datetime.now().strftime("%Y-%m-%d"):
            return HISTORICAL_CACHE_TTL_SECONDS
    except Exception:
        pass
    return CACHE_TTL_SECONDS

