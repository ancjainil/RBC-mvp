"""Prometheus metrics registry for the fraud detection API.

Metrics exposed:
- fraud_transactions_scored_total        — Counter
- fraud_transactions_flagged_total       — Counter
- fraud_risk_level_total{level}          — Counter (by risk level)
- fraud_processing_latency_seconds       — Histogram
- fraud_agent_latency_seconds{agent}     — Histogram (per agent)
- fraud_vector_store_doc_count           — Gauge
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry

logger = structlog.get_logger(__name__)

_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


@lru_cache(maxsize=1)
def get_metrics_registry() -> dict[str, Any]:
    """Create and return the shared Prometheus metrics dict.

    Uses the default global registry (``prometheus_client.REGISTRY``) so that
    ``generate_latest()`` in the metrics endpoint collects everything.

    Returns:
        Dict mapping metric name → Prometheus collector object.
    """
    try:
        transactions_scored = Counter(
            "fraud_transactions_scored_total",
            "Total number of transactions submitted for fraud scoring",
        )
        transactions_flagged = Counter(
            "fraud_transactions_flagged_total",
            "Total number of transactions flagged as potentially fraudulent",
        )
        risk_level = Counter(
            "fraud_risk_level_total",
            "Fraud assessments by risk level",
            labelnames=["level"],
        )
        processing_latency = Histogram(
            "fraud_processing_latency_seconds",
            "End-to-end fraud scoring latency",
            buckets=_LATENCY_BUCKETS,
        )
        agent_latency = Histogram(
            "fraud_agent_latency_seconds",
            "Per-agent processing latency",
            labelnames=["agent"],
            buckets=_LATENCY_BUCKETS,
        )
        vector_store_docs = Gauge(
            "fraud_vector_store_doc_count",
            "Number of documents currently in the vector store",
        )

        logger.info("metrics.registry.initialised")

        return {
            "transactions_scored": transactions_scored,
            "transactions_flagged": transactions_flagged,
            "risk_level": risk_level,
            "processing_latency": processing_latency,
            "agent_latency": agent_latency,
            "vector_store_docs": vector_store_docs,
        }

    except Exception as exc:
        # Prometheus raises if a metric is registered twice (e.g. during tests).
        # Return a no-op dict so metrics never break the request path.
        logger.warning("metrics.registry.init_failed", error=str(exc))
        return _noop_registry()


class _NoopMetric:
    """Silent drop-in for any Prometheus metric."""

    def inc(self, *a: Any, **kw: Any) -> None: ...
    def observe(self, *a: Any, **kw: Any) -> None: ...
    def set(self, *a: Any, **kw: Any) -> None: ...
    def labels(self, **kw: Any) -> "_NoopMetric": return self


def _noop_registry() -> dict[str, Any]:
    noop = _NoopMetric()
    return {
        "transactions_scored": noop,
        "transactions_flagged": noop,
        "risk_level": noop,
        "processing_latency": noop,
        "agent_latency": noop,
        "vector_store_docs": noop,
    }
