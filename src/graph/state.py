"""LangGraph state schema for the fraud detection pipeline.

FraudDetectionState is the single shared data structure passed between
every node in the StateGraph.  TypedDict is required by LangGraph; all
fields are optional except `transaction`, which must be set before the
graph is invoked.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from src.models.schemas import (
    AgentReport,
    AuditRecord,
    CustomerProfile,
    FraudAssessment,
    RiskSignal,
    Transaction,
)
from src.models.enums import RiskLevel


class FraudDetectionState(TypedDict, total=False):
    """Shared state object threaded through the LangGraph StateGraph.

    Fields are populated incrementally as each node executes.  The
    orchestrator node consumes all populated fields and emits
    ``final_assessment``.
    """

    # ── Input ────────────────────────────────────────────────────────
    transaction: Transaction
    """The transaction being evaluated.  Required; set by the caller."""

    customer_profile: CustomerProfile | None
    """Pre-fetched customer behavioural profile.  May be None if the
    customer is new or profile fetch failed gracefully."""

    # ── Intermediate agent outputs ───────────────────────────────────
    transaction_analysis: AgentReport | None
    """Output of the Transaction Analysis Agent."""

    behavioral_analysis: AgentReport | None
    """Output of the Behavioral Profiling Agent."""

    context_enrichment: AgentReport | None
    """Output of the Context Enrichment (RAG) Agent."""

    # ── Accumulated risk state ────────────────────────────────────────
    risk_signals: list[RiskSignal]
    """All risk signals emitted by agents so far, in arrival order."""

    current_risk_level: RiskLevel
    """Running worst-case risk level; updated after each agent call."""

    # ── Terminal output ───────────────────────────────────────────────
    final_assessment: FraudAssessment | None
    """Final fraud determination emitted by the Orchestrator node."""

    # ── Housekeeping ──────────────────────────────────────────────────
    audit_trail: list[AuditRecord]
    """Ordered audit log of every state transition and agent call."""

    iteration_count: int
    """Guard counter — incremented on every node execution to prevent
    runaway loops.  The graph should raise if this exceeds the
    configured max_agent_iterations."""

    error: str | None
    """Human-readable error message set when a node fails gracefully."""


def initial_state(
    transaction: Transaction,
    customer_profile: CustomerProfile | None = None,
) -> FraudDetectionState:
    """Create a fresh, properly initialised state from a transaction.

    Args:
        transaction: The transaction to evaluate.
        customer_profile: Optional pre-fetched customer profile.

    Returns:
        A ``FraudDetectionState`` dict ready for graph invocation.
    """
    return FraudDetectionState(
        transaction=transaction,
        customer_profile=customer_profile,
        transaction_analysis=None,
        behavioral_analysis=None,
        context_enrichment=None,
        risk_signals=[],
        current_risk_level=RiskLevel.LOW,
        final_assessment=None,
        audit_trail=[],
        iteration_count=0,
        error=None,
    )
