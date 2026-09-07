"""受限 HTTPS 传输、频控和主机级断路器。"""

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HOST_MIN_INTERVAL_SECONDS = 0.5
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_COOLDOWN_SECONDS = 600
MAX_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
ALLOWED_HTTP_HOSTS = {
    "smartbox.gtimg.cn", "qt.gtimg.cn", "web.ifzq.gtimg.cn",
    "push2ex.eastmoney.com", "push2.eastmoney.com", "push2his.eastmoney.com",
    "datacenter-web.eastmoney.com",
}
_HOST_LAST_REQUEST: Dict[str, float] = {}
_HOST_FAILURE_STATE: Dict[str, Dict[str, Any]] = {}


def _throttle_host(hostname: str):
    last = _HOST_LAST_REQUEST.get(hostname, 0.0)
    wait = HOST_MIN_INTERVAL_SECONDS - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _HOST_LAST_REQUEST[hostname] = time.time()


def _breaker_check(hostname: str):
    rec = _HOST_FAILURE_STATE.get(hostname)
    if rec and rec.get("opened_at") is not None:
        remaining = BREAKER_COOLDOWN_SECONDS - (time.time() - rec["opened_at"])
        if remaining > 0:
            raise ConnectionError(f"上游 {hostname} 连续失败已熔断, 约{int(remaining)}秒后恢复探测")
        rec["opened_at"] = None


def _breaker_record_success(hostname: str):
    _HOST_FAILURE_STATE.pop(hostname, None)


def _breaker_record_failure(hostname: str):
    rec = _HOST_FAILURE_STATE.setdefault(hostname, {"count": 0, "opened_at": None})
    if rec["opened_at"] is not None:
        return
    rec["count"] += 1
    if rec["count"] >= BREAKER_FAILURE_THRESHOLD:
        rec["opened_at"] = time.time()


def http_get(url: str, timeout: int = 4, encoding: str = "utf-8") -> str:
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme != "https" or hostname not in ALLOWED_HTTP_HOSTS:
        raise ValueError("仅允许访问预设的 HTTPS 金融数据源")
    _breaker_check(hostname)
    _throttle_host(hostname)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read(MAX_HTTP_RESPONSE_BYTES + 1)
            if len(content) > MAX_HTTP_RESPONSE_BYTES:
                raise ValueError("上游响应超过大小限制")
            _breaker_record_success(hostname)
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                return content.decode("gbk", errors="ignore")
        except urllib.error.HTTPError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.8)
    _breaker_record_failure(hostname)
    raise last_exc

