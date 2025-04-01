"""LangGraph node functions.

Each function here wraps one agent call and returns a *partial* state
update dict.  LangGraph merges the returned dict into the running state
automatically — nodes must NOT return the full state.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from src.models.enums import RiskLevel
from src.models.schemas import AuditRecord

if TYPE_CHECKING:
    from src.agents.transaction_agent import TransactionAgent
    from src.agents.behavioral_agent import BehavioralAgent
    from src.agents.context_agent import ContextAgent
    from src.agents.orchestrator import OrchestratorAgent
    from src.graph.state import FraudDetectionState

logger = structlog.get_logger(__name__)

_MAX_ITERATIONS = 20  # Hard safety cap; overridden by config at runtime


# ── Helpers ───────────────────────────────────────────────────────────────


def _audit(
    state: "FraudDetectionState",
    event_type: str,
    agent_name: str | None = None,
    previous: RiskLevel | None = None,
    new: RiskLevel | None = None,
    details: dict | None = None,
) -> AuditRecord:
    return AuditRecord(
        transaction_id=state["transaction"].transaction_id,
        event_type=event_type,
        agent_name=agent_name,
        previous_risk_level=previous,
        new_risk_level=new,
        details=details or {},
        timestamp=datetime.utcnow(),
    )


def _merge_risk_level(current: RiskLevel, new: RiskLevel) -> RiskLevel:
    """Return the more severe of two risk levels."""
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    return new if order.index(new) > order.index(current) else current


# ── Node: transaction analysis ────────────────────────────────────────────


def transaction_analysis_node(
    agent: "TransactionAgent",
) -> "callable[[FraudDetectionState], dict]":
    """Return a node function bound to *agent*.

    The returned callable is what LangGraph invokes.
    """

    async def node(state: "FraudDetectionState") -> dict:
        t0 = time.monotonic()
        logger.info(
            "node.transaction_analysis.start",
            transaction_id=state["transaction"].transaction_id,
        )

        report = await agent.analyze(
            transaction=state["transaction"],
            customer_profile=state.get("customer_profile"),
        )
        elapsed = (time.monotonic() - t0) * 1000

        new_risk = _merge_risk_level(state.get("current_risk_level", RiskLevel.LOW), report.risk_level)
        trail = list(state.get("audit_trail", []))
        trail.append(
            _audit(
                state,
                "AGENT_CALLED",
                agent_name="transaction_agent",
                previous=state.get("current_risk_level", RiskLevel.LOW),
                new=new_risk,
                details={"fraud_probability": report.fraud_probability, "elapsed_ms": elapsed},
            )
        )

        signals = list(state.get("risk_signals", [])) + report.risk_signals

        logger.info(
            "node.transaction_analysis.complete",
            risk_level=new_risk,
            elapsed_ms=elapsed,
        )
        return {
            "transaction_analysis": report,
            "risk_signals": signals,
            "current_risk_level": new_risk,
            "audit_trail": trail,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    return node


# ── Node: behavioral analysis ─────────────────────────────────────────────


def behavioral_analysis_node(
    agent: "BehavioralAgent",
) -> "callable[[FraudDetectionState], dict]":

    async def node(state: "FraudDetectionState") -> dict:
        t0 = time.monotonic()
        logger.info(
            "node.behavioral_analysis.start",
            transaction_id=state["transaction"].transaction_id,
        )

        report = await agent.analyze(
            transaction=state["transaction"],
            customer_profile=state.get("customer_profile"),
            prior_signals=state.get("risk_signals", []),
        )
        elapsed = (time.monotonic() - t0) * 1000

        new_risk = _merge_risk_level(state.get("current_risk_level", RiskLevel.LOW), report.risk_level)
        trail = list(state.get("audit_trail", []))
        trail.append(
            _audit(
                state,
                "AGENT_CALLED",
                agent_name="behavioral_agent",
                previous=state.get("current_risk_level", RiskLevel.LOW),
                new=new_risk,
                details={"fraud_probability": report.fraud_probability, "elapsed_ms": elapsed},
            )
        )
        signals = list(state.get("risk_signals", [])) + report.risk_signals

        logger.info(
            "node.behavioral_analysis.complete",
            risk_level=new_risk,
            elapsed_ms=elapsed,
        )
        return {
            "behavioral_analysis": report,
            "risk_signals": signals,
            "current_risk_level": new_risk,
            "audit_trail": trail,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    return node


# ── Node: context enrichment (RAG) ────────────────────────────────────────


def context_enrichment_node(
    agent: "ContextAgent",
) -> "callable[[FraudDetectionState], dict]":

    async def node(state: "FraudDetectionState") -> dict:
        t0 = time.monotonic()
        logger.info(
            "node.context_enrichment.start",
            transaction_id=state["transaction"].transaction_id,
        )

        report = await agent.enrich(
            transaction=state["transaction"],
            risk_signals=state.get("risk_signals", []),
            transaction_report=state.get("transaction_analysis"),
            behavioral_report=state.get("behavioral_analysis"),
        )
        elapsed = (time.monotonic() - t0) * 1000

        new_risk = _merge_risk_level(state.get("current_risk_level", RiskLevel.LOW), report.risk_level)
        trail = list(state.get("audit_trail", []))
        trail.append(
            _audit(
                state,
                "AGENT_CALLED",
                agent_name="context_agent",
                previous=state.get("current_risk_level", RiskLevel.LOW),
                new=new_risk,
                details={
                    "fraud_type": report.fraud_type,
                    "regulatory_flags": report.regulatory_flags,
                    "elapsed_ms": elapsed,
                },
            )
        )
        signals = list(state.get("risk_signals", [])) + report.risk_signals

        logger.info(
            "node.context_enrichment.complete",
            risk_level=new_risk,
            fraud_type=report.fraud_type,
            elapsed_ms=elapsed,
        )
        return {
            "context_enrichment": report,
            "risk_signals": signals,
            "current_risk_level": new_risk,
            "audit_trail": trail,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    return node


# ── Node: orchestrator ────────────────────────────────────────────────────


def orchestrator_node(
    agent: "OrchestratorAgent",
) -> "callable[[FraudDetectionState], dict]":

    async def node(state: "FraudDetectionState") -> dict:
        t0 = time.monotonic()
        logger.info(
            "node.orchestrator.start",
            transaction_id=state["transaction"].transaction_id,
        )

        assessment = await agent.decide(
            transaction=state["transaction"],
            transaction_report=state.get("transaction_analysis"),
            behavioral_report=state.get("behavioral_analysis"),
            context_report=state.get("context_enrichment"),
            risk_signals=state.get("risk_signals", []),
            audit_trail=state.get("audit_trail", []),
        )
        elapsed = (time.monotonic() - t0) * 1000

        trail = list(state.get("audit_trail", []))
        trail.append(
            _audit(
                state,
                "FINAL_DECISION",
                agent_name="orchestrator",
                new=assessment.risk_level,
                details={
                    "recommended_action": assessment.recommended_action,
                    "is_fraudulent": assessment.is_fraudulent,
                    "elapsed_ms": elapsed,
                },
            )
        )

        logger.info(
            "node.orchestrator.complete",
            risk_level=assessment.risk_level,
            action=assessment.recommended_action,
            is_fraudulent=assessment.is_fraudulent,
            elapsed_ms=elapsed,
        )
        return {
            "final_assessment": assessment,
            "current_risk_level": assessment.risk_level,
            "audit_trail": trail,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    return node


# ── Conditional routing functions ─────────────────────────────────────────


def route_after_transaction_analysis(state: "FraudDetectionState") -> str:
    """Route after the transaction analysis node.

    Routing logic:
    - LOW      → skip behavioural analysis, go straight to orchestrator
    - MEDIUM   → behavioural analysis for further signal
    - HIGH     → behavioural analysis (will escalate to context enrichment)
    - CRITICAL → behavioural analysis (will escalate to context enrichment)
    """
    risk = state.get("current_risk_level", RiskLevel.LOW)
    logger.debug("routing.after_transaction_analysis", risk_level=risk)

    if risk == RiskLevel.LOW:
        return "orchestrator"
    return "behavioral_analysis"


def route_after_behavioral_analysis(state: "FraudDetectionState") -> str:
    """Route after the behavioral analysis node.

    For MEDIUM risk: if the behavioral analysis escalates to HIGH or above,
    invoke context enrichment.  If still MEDIUM, go to orchestrator.

    For HIGH/CRITICAL: always go to context enrichment.
    """
    risk = state.get("current_risk_level", RiskLevel.LOW)
    logger.debug("routing.after_behavioral_analysis", risk_level=risk)

    if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return "context_enrichment"
    # MEDIUM that didn't escalate → resolve directly
    return "orchestrator"
