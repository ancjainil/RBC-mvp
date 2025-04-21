"""FastAPI dependency injection: agents, vector store, compiled graph.

All heavyweight objects (LLM clients, vector store, compiled graph) are
initialised once at startup and shared via module-level singletons.  FastAPI
dependency functions return these singletons, making them easy to override
in tests.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends

from src.agents.behavioral_agent import BehavioralAgent
from src.agents.context_agent import ContextAgent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.transaction_agent import TransactionAgent
from src.graph.workflow import compile_graph
from src.rag.retriever import FraudRetriever
from src.rag.vector_store import FraudVectorStore

logger = structlog.get_logger(__name__)


# ── Singletons ────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_vector_store() -> FraudVectorStore:
    """Return the shared vector store singleton."""
    store = FraudVectorStore()
    logger.info("deps.vector_store.ready", doc_count=store.doc_count)
    return store


@lru_cache(maxsize=1)
def get_retriever(
    vector_store: FraudVectorStore = Depends(get_vector_store),  # noqa: B008
) -> FraudRetriever:
    """Return the shared retriever singleton."""
    return FraudRetriever(vector_store=get_vector_store())


@lru_cache(maxsize=1)
def get_transaction_agent() -> TransactionAgent:
    return TransactionAgent()


@lru_cache(maxsize=1)
def get_behavioral_agent() -> BehavioralAgent:
    return BehavioralAgent()


@lru_cache(maxsize=1)
def get_context_agent() -> ContextAgent:
    return ContextAgent(retriever=get_retriever())


@lru_cache(maxsize=1)
def get_orchestrator_agent() -> OrchestratorAgent:
    return OrchestratorAgent()


@lru_cache(maxsize=1)
def get_compiled_graph() -> object:
    """Return the compiled LangGraph StateGraph singleton."""
    graph = compile_graph(
        transaction_agent=get_transaction_agent(),
        behavioral_agent=get_behavioral_agent(),
        context_agent=get_context_agent(),
        orchestrator_agent=get_orchestrator_agent(),
    )
    logger.info("deps.graph.compiled")
    return graph


# ── FastAPI dependency aliases ─────────────────────────────────────────────

VectorStoreDep = Annotated[FraudVectorStore, Depends(get_vector_store)]
RetrieverDep = Annotated[FraudRetriever, Depends(get_retriever)]
CompiledGraphDep = Annotated[object, Depends(get_compiled_graph)]
