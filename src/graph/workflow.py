"""LangGraph StateGraph definition for the fraud detection pipeline.

The graph encodes this decision flow:

    START
      └─ transaction_analysis
            └─ [route_after_transaction_analysis]
                  ├─ LOW      → orchestrator → END
                  ├─ MEDIUM   → behavioral_analysis
                  │                 └─ [route_after_behavioral_analysis]
                  │                       ├─ still MEDIUM → orchestrator → END
                  │                       └─ escalated    → context_enrichment → orchestrator → END
                  ├─ HIGH     → behavioral_analysis → context_enrichment → orchestrator → END
                  └─ CRITICAL → behavioral_analysis → context_enrichment → orchestrator → END

The conditional edges make this non-trivial: low-risk transactions take the
fast path (transaction_agent → orchestrator) avoiding the more expensive
behavioural and RAG calls.  High-risk transactions always run all three
agents before the orchestrator synthesises a decision.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import structlog
from langgraph.graph import END, START, StateGraph

from src.graph.nodes import (
    behavioral_analysis_node,
    context_enrichment_node,
    orchestrator_node,
    route_after_behavioral_analysis,
    route_after_transaction_analysis,
    transaction_analysis_node,
)
from src.graph.state import FraudDetectionState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from src.agents.behavioral_agent import BehavioralAgent
    from src.agents.context_agent import ContextAgent
    from src.agents.orchestrator import OrchestratorAgent
    from src.agents.transaction_agent import TransactionAgent

logger = structlog.get_logger(__name__)


def build_workflow(
    transaction_agent: "TransactionAgent",
    behavioral_agent: "BehavioralAgent",
    context_agent: "ContextAgent",
    orchestrator_agent: "OrchestratorAgent",
) -> StateGraph:
    """Construct the LangGraph StateGraph without compiling it.

    Separating construction from compilation makes unit-testing the graph
    structure straightforward.

    Args:
        transaction_agent: Agent that analyses raw transaction features.
        behavioral_agent: Agent that analyses customer behavioural patterns.
        context_agent: RAG-powered context enrichment agent.
        orchestrator_agent: Final synthesising / decision agent.

    Returns:
        An uncompiled ``StateGraph`` instance.
    """
    graph = StateGraph(FraudDetectionState)

    # ── Add nodes ─────────────────────────────────────────────────────
    graph.add_node(
        "transaction_analysis",
        transaction_analysis_node(transaction_agent),
    )
    graph.add_node(
        "behavioral_analysis",
        behavioral_analysis_node(behavioral_agent),
    )
    graph.add_node(
        "context_enrichment",
        context_enrichment_node(context_agent),
    )
    graph.add_node(
        "orchestrator",
        orchestrator_node(orchestrator_agent),
    )

    # ── Entry point ───────────────────────────────────────────────────
    graph.add_edge(START, "transaction_analysis")

    # ── Conditional routing after transaction analysis ─────────────────
    graph.add_conditional_edges(
        "transaction_analysis",
        route_after_transaction_analysis,
        {
            "orchestrator": "orchestrator",
            "behavioral_analysis": "behavioral_analysis",
        },
    )

    # ── Conditional routing after behavioral analysis ─────────────────
    graph.add_conditional_edges(
        "behavioral_analysis",
        route_after_behavioral_analysis,
        {
            "orchestrator": "orchestrator",
            "context_enrichment": "context_enrichment",
        },
    )

    # ── Context enrichment always goes to orchestrator ─────────────────
    graph.add_edge("context_enrichment", "orchestrator")

    # ── Orchestrator always terminates ─────────────────────────────────
    graph.add_edge("orchestrator", END)

    logger.info("workflow.built", nodes=list(graph.nodes))
    return graph


def compile_graph(
    transaction_agent: "TransactionAgent",
    behavioral_agent: "BehavioralAgent",
    context_agent: "ContextAgent",
    orchestrator_agent: "OrchestratorAgent",
) -> "CompiledStateGraph":
    """Build and compile the fraud detection StateGraph.

    The compiled graph is the object you call with ``await graph.ainvoke(state)``.

    Args:
        transaction_agent: Transaction analysis agent.
        behavioral_agent: Behavioural profiling agent.
        context_agent: Context enrichment agent.
        orchestrator_agent: Orchestrator / decision agent.

    Returns:
        A compiled ``CompiledStateGraph`` ready for invocation.
    """
    graph = build_workflow(
        transaction_agent=transaction_agent,
        behavioral_agent=behavioral_agent,
        context_agent=context_agent,
        orchestrator_agent=orchestrator_agent,
    )
    compiled = graph.compile()
    logger.info("workflow.compiled")
    return compiled
