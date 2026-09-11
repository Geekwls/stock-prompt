"""预测评估纯函数。"""

import math

from .common import result


STATES = ("up", "side", "down")


def calculate_multiclass_brier(probabilities, actual_state, input_snapshot_id=None):
    if actual_state not in STATES or any(state not in probabilities for state in STATES):
        return result("N/A", "multiclass-brier-v1", input_snapshot_id, ["probabilities_or_actual"], "unavailable")
    scale = 100.0 if sum(probabilities.values()) > 1.5 else 1.0
    # 与现有评估台账保持一致：多分类 Brier 使用各类别误差平方和。
    score = sum((probabilities[state] / scale - (1.0 if state == actual_state else 0.0)) ** 2 for state in STATES)
    return result(round(score, 8), "multiclass-brier-v1", input_snapshot_id)


def calculate_interval_score(lower, upper, actual, alpha=0.2, input_snapshot_id=None):
    if upper < lower or not 0 < alpha < 1:
        raise ValueError("区间上下界或 alpha 非法")
    score = upper - lower
    if actual < lower:
        score += 2 / alpha * (lower - actual)
    elif actual > upper:
        score += 2 / alpha * (actual - upper)
    return result(round(score, 8), "interval-score-winkler-v1", input_snapshot_id, covered=lower <= actual <= upper)


def calculate_topk_metrics(predicted, actual, k=3, input_snapshot_id=None):
    predicted, actual = list(predicted)[:k], set(actual)
    hits = sum(item in actual for item in predicted)
    value = {"hits": hits, "precision": hits / len(predicted) if predicted else 0.0, "recall": hits / len(actual) if actual else 0.0, "any_hit": hits > 0}
    return result(value, "topk-metrics-v1", input_snapshot_id)


def calculate_ndcg(predicted, relevance, k=None, input_snapshot_id=None):
    ranked = list(predicted)[:k]
    dcg = sum((2 ** relevance.get(item, 0) - 1) / math.log2(index + 2) for index, item in enumerate(ranked))
    ideal = sorted(relevance.values(), reverse=True)[:len(ranked)]
    idcg = sum((2 ** score - 1) / math.log2(index + 2) for index, score in enumerate(ideal))
    return result(round(dcg / idcg, 8) if idcg else 0.0, "ndcg-v1", input_snapshot_id)


def calculate_lifecycle_accuracy(predicted, actual, input_snapshot_id=None):
    if len(predicted) != len(actual) or not predicted:
        return result("N/A", "lifecycle-accuracy-v1", input_snapshot_id, ["aligned_nonempty_sequences"], "unavailable")
    hits = sum(left == right for left, right in zip(predicted, actual))
    return result(round(hits / len(predicted), 8), "lifecycle-accuracy-v1", input_snapshot_id, hits=hits, total=len(predicted))


def calculate_calibration_curve(probabilities, outcomes, bins=10, input_snapshot_id=None):
    if len(probabilities) != len(outcomes) or not probabilities:
        return result("N/A", "calibration-curve-v1", input_snapshot_id, ["aligned_nonempty_samples"], "unavailable")
    buckets = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes):
        probability = probability / 100 if probability > 1 else probability
        index = min(bins - 1, max(0, int(probability * bins)))
        buckets[index].append((probability, 1.0 if outcome else 0.0))
    curve = []
    for index, bucket in enumerate(buckets):
        if bucket:
            curve.append({"bin": index, "count": len(bucket), "predicted": round(sum(item[0] for item in bucket) / len(bucket), 8), "observed": round(sum(item[1] for item in bucket) / len(bucket), 8)})
    return result(curve, "calibration-curve-v1", input_snapshot_id)
