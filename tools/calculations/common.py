"""计算结果公共封装。"""


def clamp(value, lower=0.0, upper=100.0):
    return max(lower, min(upper, float(value)))


def result(value, formula_version, input_snapshot_id=None, missing=None, status=None, **details):
    missing = sorted(set(missing or []))
    if status is None:
        status = "complete" if not missing else "partial"
    payload = {
        "value": value,
        "formula_version": formula_version,
        "input_snapshot_id": input_snapshot_id or "N/A",
        "missing": missing,
        "status": status,
    }
    payload.update(details)
    return payload


def require_range(name, value, lower=0.0, upper=100.0):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower <= value <= upper:
        raise ValueError(f"{name} 必须在 {lower}–{upper} 之间")

