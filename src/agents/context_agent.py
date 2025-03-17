"""Context Enrichment Agent (RAG-powered).

Retrieves relevant fraud-typology and regulatory documents from the
vector store and uses them to enrich the LLM's fraud determination with:
- Matched fraud typology classification
- FINTRAC / PCI-DSS regulatory flag detection
- Recommended investigation steps grounded in the knowledge base

This agent runs only for HIGH and CRITICAL risk transactions (after
behavioural analysis has confirmed or escalated the risk level).
"""

from __future__ import annotations

import time

import structlog

from src.agents.base_agent import BaseAgent, LLMCallError, LLMParseError
from src.models.enums import FraudTypology, RiskLevel, SignalSeverity
from src.models.schemas import AgentReport, RiskSignal, Transaction
from src.rag.retriever import FraudRetriever

logger = structlog.get_logger(__name__)


class ContextAgent(BaseAgent):
    """Enriches fraud assessments with knowledge-base context via RAG.

    Args:
        retriever: A pre-initialised :class:`~src.rag.retriever.FraudRetriever`
            that has access to the ingested knowledge base.
    """

    def __init__(self, retriever: FraudRetriever) -> None:
        super().__init__()
        self._retriever = retriever

    @property
    def _config_key(self) -> str:
        return "context_agent"

    async def enrich(
        self,
        transaction: Transaction,
        risk_signals: list[RiskSignal],
        transaction_report: AgentReport | None,
        behavioral_report: AgentReport | None,
    ) -> AgentReport:
        """Retrieve knowledge-base context and produce an enriched assessment.

        Args:
            transaction: The transaction under review.
            risk_signals: Accumulated signals from all prior agents.
            transaction_report: Report from the Transaction Analysis Agent.
            behavioral_report: Report from the Behavioral Profiling Agent.

        Returns:
            :class:`~src.models.schemas.AgentReport` enriched with RAG context.
        """
        t0 = time.monotonic()
        self._log.info(
            "context_agent.enrich.start",
            transaction_id=transaction.transaction_id,
        )

        # ── 1. Build retrieval query from accumulated signals ──────────
        query = _build_retrieval_query(transaction, risk_signals)
        self._log.debug("context_agent.retrieval_query", query=query[:200])

        # ── 2. Retrieve relevant documents ────────────────────────────
        retrieved_docs = await self._retriever.aretrieve(
            query=query,
            k=self._cfg.get("retrieval_top_k", 5),
            score_threshold=self._cfg.get("retrieval_similarity_threshold", 0.75),
        )

        if not retrieved_docs:
            self._log.warning(
                "context_agent.no_docs_retrieved",
                transaction_id=transaction.transaction_id,
                query=query[:100],
            )

        # ── 3. Format retrieved context ────────────────────────────────
        context_text = _format_retrieved_docs(retrieved_docs)
        signals_text = _format_signals(risk_signals)

        # ── 4. LLM enrichment call ─────────────────────────────────────
        system_prompt = (
            "You are a senior fraud intelligence analyst with access to the bank's "
            "internal knowledge base of fraud typologies and regulatory guidelines. "
            "Respond with valid JSON only."
        )
        user_prompt = self._format_prompt(
            self._prompt_template,
            risk_signals_summary=signals_text,
            retrieved_context=context_text,
        )

        raw_response = ""
        try:
            raw_response = await self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(raw_response)
        except (LLMCallError, LLMParseError) as exc:
            self._log.warning(
                "context_agent.llm.fallback",
                error=str(exc),
                transaction_id=transaction.transaction_id,
            )
            parsed = _fallback_assessment(risk_signals)

        # ── 5. Build report ────────────────────────────────────────────
        llm_signals = [
            RiskSignal(
                signal_type=s.get("signal_type", "unknown"),
                description=s.get("description", ""),
                severity=SignalSeverity(s.get("severity", "MEDIUM")),
                score=float(s.get("score", 0.5)),
                source_agent="context_agent",
            )
            for s in parsed.get("risk_signals", [])
        ]

        # Parse fraud type safely
        fraud_type_raw = parsed.get("fraud_type")
        fraud_type: FraudTypology | None = None
        if fraud_type_raw:
            try:
                fraud_type = FraudTypology(fraud_type_raw)
            except ValueError:
                fraud_type = FraudTypology.UNKNOWN

        elapsed = (time.monotonic() - t0) * 1000
        self._log.info(
            "context_agent.enrich.complete",
            transaction_id=transaction.transaction_id,
            fraud_type=fraud_type,
            docs_retrieved=len(retrieved_docs),
            elapsed_ms=round(elapsed, 2),
        )

        return AgentReport(
            agent_name="context_agent",
            risk_level=RiskLevel(parsed.get("risk_level", "HIGH")),
            fraud_probability=float(parsed.get("fraud_probability", 0.65)),
            confidence=float(parsed.get("confidence", 0.70)),
            reasoning=parsed.get("reasoning", "Context enrichment fallback."),
            risk_signals=llm_signals,
            fraud_type=fraud_type,
            regulatory_flags=parsed.get("regulatory_flags", []),
            processing_time_ms=elapsed,
            raw_llm_response=raw_response,
        )


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_retrieval_query(
    transaction: Transaction, signals: list[RiskSignal]
) -> str:
    """Construct a natural-language query for vector similarity search.

    The query is built from the most informative signals to maximise
    retrieval relevance.
    """
    parts = [
        f"fraud pattern: {transaction.merchant_category.value} transaction",
        f"channel: {transaction.channel.value}",
    ]
    for sig in signals:
        if sig.severity == SignalSeverity.HIGH:
            parts.append(sig.signal_type.replace("_", " "))
    return " ".join(parts)


def _format_retrieved_docs(docs: list[dict]) -> str:
    if not docs:
        return "No relevant documents retrieved from knowledge base."
    sections = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("metadata", {}).get("source_file", "unknown")
        score = doc.get("score", 0.0)
        content = doc.get("content", "")[:600]
        sections.append(
            f"[{i}] Source: {source} (relevance: {score:.2f})\n{content}"
        )
    return "\n\n---\n\n".join(sections)


def _format_signals(signals: list[RiskSignal]) -> str:
    if not signals:
        return "No risk signals accumulated."
    return "\n".join(
        f"- [{s.severity.value}] {s.signal_type}: {s.description}" for s in signals
    )


def _fallback_assessment(signals: list[RiskSignal]) -> dict:
    high = sum(1 for s in signals if s.severity == SignalSeverity.HIGH)
    prob = min(0.55 + 0.15 * high, 0.95)
    return {
        "risk_level": RiskLevel.from_probability(prob).value,
        "fraud_probability": prob,
        "confidence": 0.40,
        "fraud_type": None,
        "regulatory_flags": [],
        "reasoning": "LLM unavailable; context agent fell back to signal-based assessment.",
        "risk_signals": [],
    }
