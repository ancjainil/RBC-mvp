"""Custom retriever with similarity threshold, metadata filtering, and optional reranking.

The retriever returns a list of dicts (not raw LangChain Documents) so that
downstream agents can access both content and metadata uniformly.

Reranking (optional) uses a cross-encoder from ``sentence-transformers`` to
re-score the top-K candidates and return only the most relevant subset.
"""

from __future__ import annotations

from typing import Any

import structlog

from config.settings import get_settings
from src.rag.vector_store import FraudVectorStore

logger = structlog.get_logger(__name__)
_settings = get_settings()


class FraudRetriever:
    """High-level retriever for the fraud knowledge base.

    Args:
        vector_store: Initialised :class:`~src.rag.vector_store.FraudVectorStore`.
        similarity_threshold: Minimum cosine similarity score for inclusion.
        top_k: Maximum number of results to return after filtering.
        enable_reranking: If ``True`` and ``sentence-transformers`` is installed,
            apply cross-encoder reranking to the raw candidates.
        rerank_top_k: Number of results to return after reranking.
    """

    def __init__(
        self,
        vector_store: FraudVectorStore,
        similarity_threshold: float | None = None,
        top_k: int | None = None,
        enable_reranking: bool | None = None,
        rerank_top_k: int = 3,
    ) -> None:
        self._store = vector_store
        self._threshold = (
            similarity_threshold or _settings.vector_store.similarity_threshold
        )
        self._top_k = top_k or _settings.vector_store.top_k
        self._enable_reranking = (
            enable_reranking
            if enable_reranking is not None
            else _settings.flags.enable_reranking
        )
        self._rerank_top_k = rerank_top_k
        self._reranker = self._load_reranker() if self._enable_reranking else None

    # ── Public API ────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        k: int | None = None,
        score_threshold: float | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Synchronous retrieval with threshold filtering and optional reranking.

        Args:
            query: Natural-language query string.
            k: Override the default ``top_k``.
            score_threshold: Override the default similarity threshold.
            document_type: Filter by document type metadata (e.g. ``"regulatory"``).

        Returns:
            List of result dicts with keys ``content``, ``metadata``, ``score``.
        """
        effective_k = k or self._top_k
        effective_threshold = score_threshold or self._threshold

        where: dict[str, Any] | None = None
        if document_type:
            where = {"document_type": {"$eq": document_type}}

        raw_results = self._store.similarity_search_with_score(
            query=query,
            k=effective_k * 2,  # fetch 2× to have headroom for threshold filtering
            where=where,
        )

        # Filter by similarity threshold
        filtered = [
            {"content": doc.page_content, "metadata": doc.metadata, "score": score}
            for doc, score in raw_results
            if score >= effective_threshold
        ]

        logger.debug(
            "retriever.retrieve",
            query=query[:80],
            raw=len(raw_results),
            after_threshold=len(filtered),
            threshold=effective_threshold,
        )

        if not filtered:
            return []

        if self._enable_reranking and self._reranker:
            filtered = self._rerank(query, filtered)

        return filtered[:effective_k]

    async def aretrieve(
        self,
        query: str,
        k: int | None = None,
        score_threshold: float | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Async version of :meth:`retrieve`."""
        import asyncio

        effective_k = k or self._top_k
        effective_threshold = score_threshold or self._threshold

        where: dict[str, Any] | None = None
        if document_type:
            where = {"document_type": {"$eq": document_type}}

        raw_results = await self._store.asimilarity_search_with_score(
            query=query,
            k=effective_k * 2,
            where=where,
        )

        filtered = [
            {"content": doc.page_content, "metadata": doc.metadata, "score": score}
            for doc, score in raw_results
            if score >= effective_threshold
        ]

        if not filtered:
            return []

        if self._enable_reranking and self._reranker:
            loop = asyncio.get_running_loop()
            filtered = await loop.run_in_executor(
                None, lambda: self._rerank(query, filtered)
            )

        return filtered[:effective_k]

    # ── Reranking ─────────────────────────────────────────────────────

    def _rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Re-score candidates using a cross-encoder and return sorted results.

        Args:
            query: The original query string.
            candidates: Initial retrieval results from embedding search.

        Returns:
            Re-ranked list (highest cross-encoder score first), trimmed to
            ``rerank_top_k``.
        """
        if not self._reranker:
            return candidates

        pairs = [(query, r["content"]) for r in candidates]
        scores = self._reranker.predict(pairs)
        for result, score in zip(candidates, scores):
            result["rerank_score"] = float(score)

        reranked = sorted(candidates, key=lambda r: r["rerank_score"], reverse=True)
        logger.debug(
            "retriever.rerank",
            candidates=len(candidates),
            returned=self._rerank_top_k,
        )
        return reranked[: self._rerank_top_k]

    def _load_reranker(self) -> Any | None:
        """Load the cross-encoder reranker, returning None if unavailable."""
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("retriever.reranker.loaded")
            return model
        except ImportError:
            logger.warning(
                "retriever.reranker.unavailable",
                reason="sentence-transformers not installed",
            )
            return None
