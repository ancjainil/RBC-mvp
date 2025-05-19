"""Custom evaluation metrics for the fraud detection system.

Metrics computed:
- Standard classification: precision, recall, F1, AUC-ROC, false positive rate
- Fraud-type breakdown: per-typology precision and recall
- Operational metrics: average detection latency, p95/p99 latency
- Explanation quality scoring: checks that the explanation is non-trivial
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassificationMetrics:
    """Standard binary classification metrics."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    auc_roc: float = 0.0
    false_positive_rate: float = 0.0
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.true_negatives + self.false_positives + self.false_negatives
        return (self.true_positives + self.true_negatives) / max(total, 1)

    @property
    def specificity(self) -> float:
        return self.true_negatives / max(self.true_negatives + self.false_positives, 1)


@dataclass
class LatencyMetrics:
    """End-to-end latency statistics in milliseconds."""

    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    samples: int = 0


@dataclass
class EvaluationReport:
    """Full evaluation report produced by the benchmark runner."""

    overall: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    latency: LatencyMetrics = field(default_factory=LatencyMetrics)
    per_fraud_type: dict[str, ClassificationMetrics] = field(default_factory=dict)
    explanation_quality_mean: float = 0.0
    total_evaluated: int = 0
    total_fraudulent_ground_truth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for JSON output."""
        return {
            "summary": {
                "total_evaluated": self.total_evaluated,
                "total_fraudulent_gt": self.total_fraudulent_ground_truth,
                "precision": round(self.overall.precision, 4),
                "recall": round(self.overall.recall, 4),
                "f1": round(self.overall.f1, 4),
                "auc_roc": round(self.overall.auc_roc, 4),
                "false_positive_rate": round(self.overall.false_positive_rate, 4),
                "accuracy": round(self.overall.accuracy, 4),
                "confusion_matrix": {
                    "tp": self.overall.true_positives,
                    "tn": self.overall.true_negatives,
                    "fp": self.overall.false_positives,
                    "fn": self.overall.false_negatives,
                },
            },
            "latency_ms": {
                "mean": round(self.latency.mean_ms, 2),
                "median": round(self.latency.median_ms, 2),
                "p95": round(self.latency.p95_ms, 2),
                "p99": round(self.latency.p99_ms, 2),
                "min": round(self.latency.min_ms, 2),
                "max": round(self.latency.max_ms, 2),
            },
            "per_fraud_type": {
                ft: {
                    "precision": round(m.precision, 4),
                    "recall": round(m.recall, 4),
                    "f1": round(m.f1, 4),
                }
                for ft, m in self.per_fraud_type.items()
            },
            "explanation_quality_mean": round(self.explanation_quality_mean, 3),
            "metadata": self.metadata,
        }


# ── Metric computation ────────────────────────────────────────────────────


def compute_classification_metrics(
    y_true: list[bool],
    y_pred: list[bool],
    y_scores: list[float],
) -> ClassificationMetrics:
    """Compute precision, recall, F1, AUC-ROC, FPR.

    Args:
        y_true: Ground-truth binary labels.
        y_pred: Predicted binary labels.
        y_scores: Fraud probability scores in [0, 1].

    Returns:
        :class:`ClassificationMetrics` instance.
    """
    tp = sum(1 for g, p in zip(y_true, y_pred) if g and p)
    tn = sum(1 for g, p in zip(y_true, y_pred) if not g and not p)
    fp = sum(1 for g, p in zip(y_true, y_pred) if not g and p)
    fn = sum(1 for g, p in zip(y_true, y_pred) if g and not p)

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, 1e-9)
    fpr = fp / max(fp + tn, 1)

    auc = _auc_roc(y_true, y_scores)

    return ClassificationMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        auc_roc=auc,
        false_positive_rate=fpr,
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
    )


def compute_per_type_metrics(
    y_true: list[bool],
    y_pred: list[bool],
    fraud_types: list[str | None],
) -> dict[str, ClassificationMetrics]:
    """Compute precision/recall/F1 broken down by fraud typology.

    Args:
        y_true: Ground-truth labels.
        y_pred: Predicted labels.
        fraud_types: Fraud type for each sample (None for legitimate).

    Returns:
        Dict mapping fraud type → ClassificationMetrics.
    """
    type_data: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for gt, pred, ft in zip(y_true, y_pred, fraud_types):
        if gt and ft:
            type_data[ft].append((gt, pred))

    result: dict[str, ClassificationMetrics] = {}
    for ft, pairs in type_data.items():
        gt_list = [p[0] for p in pairs]
        pred_list = [p[1] for p in pairs]
        scores = [1.0 if p[1] else 0.0 for p in pairs]
        result[ft] = compute_classification_metrics(gt_list, pred_list, scores)
    return result


def compute_latency_metrics(latencies_ms: list[float]) -> LatencyMetrics:
    """Compute latency percentiles from a list of durations.

    Args:
        latencies_ms: List of per-transaction latencies in milliseconds.

    Returns:
        :class:`LatencyMetrics` instance.
    """
    if not latencies_ms:
        return LatencyMetrics()
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)
    return LatencyMetrics(
        mean_ms=sum(sorted_l) / n,
        median_ms=sorted_l[n // 2],
        p95_ms=sorted_l[int(n * 0.95)],
        p99_ms=sorted_l[int(n * 0.99)],
        min_ms=sorted_l[0],
        max_ms=sorted_l[-1],
        samples=n,
    )


def score_explanation_quality(explanation: str) -> float:
    """Heuristic score for explanation quality (0–1).

    Checks that the explanation:
    - Is non-trivial (> 50 characters)
    - Mentions specific signals (amount, location, category, device, etc.)
    - Is not a generic fallback message

    Args:
        explanation: Plain-text explanation from the orchestrator.

    Returns:
        Float in [0, 1] where 1 = high quality.
    """
    if not explanation or len(explanation) < 50:
        return 0.0
    score = 0.4  # base score for non-empty explanation
    keywords = [
        "amount", "location", "device", "category", "merchant",
        "velocity", "pattern", "history", "risk", "fraud",
        "transaction", "customer", "account",
    ]
    hits = sum(1 for kw in keywords if kw.lower() in explanation.lower())
    score += min(hits / len(keywords), 0.6)

    fallback_phrases = [
        "automated fraud assessment based on rule",
        "llm unavailable",
        "no llm reasoning available",
    ]
    if any(p in explanation.lower() for p in fallback_phrases):
        score *= 0.5
    return round(min(score, 1.0), 3)


# ── AUC-ROC (trapezoid rule, no numpy required) ───────────────────────────


def _auc_roc(y_true: list[bool], y_scores: list[float]) -> float:
    """Compute AUC-ROC using the trapezoidal rule."""
    pairs = sorted(zip(y_scores, y_true), reverse=True)
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    tpr_points = [0.0]
    fpr_points = [0.0]
    tp = fp = 0
    for _, label in pairs:
        if label:
            tp += 1
        else:
            fp += 1
        tpr_points.append(tp / n_pos)
        fpr_points.append(fp / n_neg)

    # Trapezoidal integration
    auc = 0.0
    for i in range(1, len(fpr_points)):
        auc += (fpr_points[i] - fpr_points[i - 1]) * (tpr_points[i] + tpr_points[i - 1]) / 2
    return auc
