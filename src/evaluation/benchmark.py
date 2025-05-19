"""Benchmark runner: evaluate the full pipeline against labelled test data.

Usage:
    python scripts/run_evaluation.py --output reports/eval_result.json

The benchmark:
1. Loads labelled transactions from data/synthetic/transactions.json (or a
   provided test file)
2. Runs each transaction through the compiled LangGraph graph
3. Computes classification and latency metrics
4. Produces a structured EvaluationReport
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from src.evaluation.metrics import (
    EvaluationReport,
    compute_classification_metrics,
    compute_latency_metrics,
    compute_per_type_metrics,
    score_explanation_quality,
)
from src.models.enums import MerchantCategory, TransactionChannel, TransactionType
from src.models.schemas import CustomerProfile, GeoLocation, ScoreRequest, Transaction

logger = structlog.get_logger(__name__)


class BenchmarkRunner:
    """Runs the fraud detection pipeline against a labelled dataset.

    Args:
        graph: A compiled LangGraph StateGraph (from ``compile_graph``).
        max_samples: Limit evaluation to this many samples (for quick runs).
        concurrency: Number of concurrent graph invocations.
    """

    def __init__(
        self,
        graph: Any,
        max_samples: int | None = None,
        concurrency: int = 5,
    ) -> None:
        self._graph = graph
        self._max_samples = max_samples
        self._concurrency = concurrency

    async def run(
        self,
        test_file: str = "data/synthetic/transactions.json",
        profile_file: str | None = "data/synthetic/customer_profiles.json",
    ) -> EvaluationReport:
        """Execute the benchmark and return a full evaluation report.

        Args:
            test_file: Path to the labelled transactions JSON file.
            profile_file: Path to the customer profiles JSON file.

        Returns:
            :class:`~src.evaluation.metrics.EvaluationReport`.
        """
        logger.info("benchmark.start", test_file=test_file)
        t0 = time.monotonic()

        # ── Load data ──────────────────────────────────────────────────
        transactions_raw = json.loads(Path(test_file).read_text())
        profiles_by_id: dict[str, CustomerProfile] = {}

        if profile_file and Path(profile_file).exists():
            profiles_raw = json.loads(Path(profile_file).read_text())
            for p in profiles_raw:
                try:
                    profile = CustomerProfile.model_validate(p)
                    profiles_by_id[profile.customer_id] = profile
                except Exception:
                    pass

        if self._max_samples:
            transactions_raw = transactions_raw[: self._max_samples]

        logger.info("benchmark.data_loaded", samples=len(transactions_raw))

        # ── Run pipeline ───────────────────────────────────────────────
        semaphore = asyncio.Semaphore(self._concurrency)
        results: list[dict] = []

        async def _run_one(raw: dict) -> dict:
            async with semaphore:
                txn = _raw_to_transaction(raw)
                profile = profiles_by_id.get(raw["customer_id"])
                t1 = time.monotonic()
                try:
                    from src.graph.state import initial_state

                    state = initial_state(transaction=txn, customer_profile=profile)
                    final_state = await self._graph.ainvoke(state)
                    assessment = final_state.get("final_assessment")
                    latency_ms = (time.monotonic() - t1) * 1000

                    return {
                        "transaction_id": txn.transaction_id,
                        "ground_truth": raw.get("fraud_label", False),
                        "ground_truth_type": raw.get("fraud_type"),
                        "predicted": assessment.is_fraudulent if assessment else False,
                        "score": assessment.fraud_probability if assessment else 0.0,
                        "fraud_type_predicted": assessment.fraud_type.value if (
                            assessment and assessment.fraud_type
                        ) else None,
                        "explanation": assessment.explanation if assessment else "",
                        "latency_ms": latency_ms,
                        "error": None,
                    }
                except Exception as exc:
                    latency_ms = (time.monotonic() - t1) * 1000
                    logger.warning("benchmark.sample_error", error=str(exc))
                    return {
                        "transaction_id": txn.transaction_id,
                        "ground_truth": raw.get("fraud_label", False),
                        "ground_truth_type": raw.get("fraud_type"),
                        "predicted": False,
                        "score": 0.0,
                        "fraud_type_predicted": None,
                        "explanation": "",
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }

        tasks = [_run_one(r) for r in transactions_raw]
        results = await asyncio.gather(*tasks)

        # ── Compute metrics ────────────────────────────────────────────
        y_true = [r["ground_truth"] for r in results]
        y_pred = [r["predicted"] for r in results]
        y_scores = [r["score"] for r in results]
        fraud_types = [r["ground_truth_type"] for r in results]
        latencies = [r["latency_ms"] for r in results]
        explanations = [r["explanation"] for r in results if r["explanation"]]

        overall = compute_classification_metrics(y_true, y_pred, y_scores)
        latency = compute_latency_metrics(latencies)
        per_type = compute_per_type_metrics(y_true, y_pred, fraud_types)
        expl_quality = (
            sum(score_explanation_quality(e) for e in explanations) / len(explanations)
            if explanations
            else 0.0
        )

        total_elapsed = (time.monotonic() - t0) * 1000

        logger.info(
            "benchmark.complete",
            total=len(results),
            precision=round(overall.precision, 3),
            recall=round(overall.recall, 3),
            f1=round(overall.f1, 3),
            auc_roc=round(overall.auc_roc, 3),
            elapsed_ms=round(total_elapsed, 0),
        )

        report = EvaluationReport(
            overall=overall,
            latency=latency,
            per_fraud_type=per_type,
            explanation_quality_mean=expl_quality,
            total_evaluated=len(results),
            total_fraudulent_ground_truth=sum(y_true),
            metadata={
                "test_file": test_file,
                "evaluated_at": datetime.utcnow().isoformat(),
                "total_elapsed_ms": round(total_elapsed, 0),
                "errors": sum(1 for r in results if r["error"]),
                "concurrency": self._concurrency,
            },
        )
        return report


# ── Data conversion ───────────────────────────────────────────────────────


def _raw_to_transaction(raw: dict) -> Transaction:
    """Convert a raw dict from the synthetic data file to a Transaction."""
    loc_raw = raw.get("location")
    location = (
        GeoLocation(
            lat=loc_raw["lat"],
            lon=loc_raw["lon"],
            city=loc_raw.get("city"),
            country_code=loc_raw.get("country_code"),
        )
        if loc_raw
        else None
    )
    return Transaction(
        transaction_id=raw.get("transaction_id", f"txn_{id(raw)}"),
        customer_id=raw["customer_id"],
        amount=Decimal(str(raw["amount"])),
        currency=raw.get("currency", "CAD"),
        merchant_id=raw.get("merchant_id", "unknown"),
        merchant_name=raw["merchant_name"],
        merchant_category_code=raw["merchant_category_code"],
        merchant_category=MerchantCategory(raw["merchant_category"]),
        transaction_type=TransactionType(
            raw.get("transaction_type", TransactionType.PURCHASE.value)
        ),
        channel=TransactionChannel(raw["channel"]),
        card_present=raw["card_present"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        location=location,
        device_fingerprint=raw.get("device_fingerprint"),
        ip_address=raw.get("ip_address"),
        recurring=raw.get("recurring", False),
    )
