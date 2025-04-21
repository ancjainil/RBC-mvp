"""API route handlers.

Endpoints:
  POST /api/v1/transactions/score         — Score a single transaction
  POST /api/v1/transactions/batch         — Score up to 100 transactions
  GET  /api/v1/audit/{transaction_id}     — Retrieve audit trail (in-memory)
  GET  /api/v1/health                     — Health check
  GET  /api/v1/metrics                    — Prometheus metrics
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from src.api.dependencies import CompiledGraphDep, VectorStoreDep
from src.graph.state import initial_state
from src.models.schemas import (
    BatchScoreRequest,
    BatchScoreResponse,
    FraudAssessment,
    HealthResponse,
    ScoreRequest,
    ScoreResponse,
)
from src.monitoring.dashboards import get_metrics_registry

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1")

# In-memory audit store (replace with Redis/DB in production)
_audit_store: dict[str, FraudAssessment] = {}

_APP_VERSION = "1.0.0"
_START_TIME = time.time()


# ── Health ────────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["ops"],
)
async def health_check(
    vector_store: VectorStoreDep,
) -> HealthResponse:
    """Returns service health and dependency status."""
    from config.settings import get_settings

    settings = get_settings()
    vs_health = vector_store.health_check()

    return HealthResponse(
        status="ok" if vs_health["status"] == "ok" else "degraded",
        version=_APP_VERSION,
        vector_store=vs_health["status"],
        llm_provider=settings.llm.provider,
        environment=settings.api.environment,
        uptime_seconds=round(time.time() - _START_TIME, 1),
    )


# ── Prometheus metrics ────────────────────────────────────────────────────


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics",
    tags=["ops"],
)
async def metrics_endpoint() -> str:
    """Expose Prometheus metrics in text format."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


# ── Single transaction scoring ─────────────────────────────────────────────


@router.post(
    "/transactions/score",
    response_model=ScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Score a single transaction for fraud",
    tags=["fraud-detection"],
    responses={
        200: {"description": "Fraud assessment completed successfully"},
        422: {"description": "Validation error in request body"},
        503: {"description": "Upstream LLM or vector store unavailable"},
    },
)
async def score_transaction(
    request: Request,
    body: ScoreRequest,
    graph: CompiledGraphDep,
) -> ScoreResponse:
    """Run the multi-agent fraud detection pipeline on a single transaction.

    The pipeline may invoke 1–3 specialised agents depending on the risk
    level determined by the Transaction Analysis Agent.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    txn_id = body.transaction.transaction_id

    logger.info(
        "api.score.start",
        transaction_id=txn_id,
        correlation_id=correlation_id,
    )

    t0 = time.monotonic()
    try:
        state = initial_state(
            transaction=body.transaction,
            customer_profile=body.customer_profile,
        )
        final_state = await graph.ainvoke(state)
        assessment: FraudAssessment = final_state["final_assessment"]
        assessment.processing_time_ms = (time.monotonic() - t0) * 1000

        # Store in audit cache
        _audit_store[txn_id] = assessment

        _record_metrics(assessment)

        logger.info(
            "api.score.complete",
            transaction_id=txn_id,
            risk_level=assessment.risk_level.value,
            is_fraudulent=assessment.is_fraudulent,
            action=assessment.recommended_action.value,
            elapsed_ms=round(assessment.processing_time_ms, 2),
        )

        return ScoreResponse(assessment=assessment, correlation_id=correlation_id)

    except Exception as exc:
        logger.error(
            "api.score.error",
            transaction_id=txn_id,
            error=str(exc),
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Fraud scoring pipeline failed: {exc}",
        ) from exc


# ── Batch scoring ─────────────────────────────────────────────────────────


@router.post(
    "/transactions/batch",
    response_model=BatchScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Score a batch of transactions",
    tags=["fraud-detection"],
)
async def score_batch(
    request: Request,
    body: BatchScoreRequest,
    graph: CompiledGraphDep,
) -> BatchScoreResponse:
    """Score up to 100 transactions concurrently.

    Transactions are processed with bounded concurrency (max 10 concurrent
    graph invocations) to avoid overloading the LLM API.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    t0 = time.monotonic()

    semaphore = asyncio.Semaphore(10)

    async def _score_one(item: ScoreRequest) -> FraudAssessment:
        async with semaphore:
            state = initial_state(
                transaction=item.transaction,
                customer_profile=item.customer_profile,
            )
            final_state = await graph.ainvoke(state)
            assessment = final_state["final_assessment"]
            _audit_store[item.transaction.transaction_id] = assessment
            _record_metrics(assessment)
            return assessment

    assessments = await asyncio.gather(
        *[_score_one(item) for item in body.transactions],
        return_exceptions=False,
    )

    total_ms = (time.monotonic() - t0) * 1000
    flagged = sum(1 for a in assessments if a.is_fraudulent)

    logger.info(
        "api.batch.complete",
        total=len(assessments),
        flagged=flagged,
        elapsed_ms=round(total_ms, 2),
    )

    return BatchScoreResponse(
        assessments=list(assessments),
        total=len(assessments),
        flagged=flagged,
        processing_time_ms=total_ms,
        correlation_id=correlation_id,
    )


# ── Audit trail ───────────────────────────────────────────────────────────


@router.get(
    "/audit/{transaction_id}",
    response_model=FraudAssessment,
    summary="Retrieve full audit trail for a scored transaction",
    tags=["audit"],
    responses={
        200: {"description": "Audit record found"},
        404: {"description": "Transaction ID not found in audit store"},
    },
)
async def get_audit(transaction_id: str) -> FraudAssessment:
    """Retrieve the full fraud assessment and audit trail for a transaction.

    Note: The in-memory audit store is cleared on service restart.
    In production, persist assessments to a database.
    """
    if transaction_id not in _audit_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit record found for transaction_id={transaction_id!r}",
        )
    return _audit_store[transaction_id]


# ── Helpers ───────────────────────────────────────────────────────────────


def _record_metrics(assessment: FraudAssessment) -> None:
    """Record Prometheus counters/histograms for this assessment."""
    try:
        reg = get_metrics_registry()
        reg["transactions_scored"].inc()
        reg["transactions_flagged"].inc(1 if assessment.is_fraudulent else 0)
        reg["risk_level"].labels(level=assessment.risk_level.value).inc()
        reg["processing_latency"].observe(assessment.processing_time_ms / 1000)
    except Exception:
        pass  # Metrics are non-critical; never let them break the request path
