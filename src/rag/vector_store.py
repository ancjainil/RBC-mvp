"""ChromaDB vector store wrapper.

Provides a thin abstraction over LangChain's Chroma integration with:
- Persistent local storage (configurable path)
- Collection health-check
- Async-compatible similarity search
- Metadata filtering support
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from config.settings import get_settings
from src.rag.embeddings import get_embeddings

logger = structlog.get_logger(__name__)
_settings = get_settings()


class FraudVectorStore:
    """Persistent ChromaDB vector store for fraud knowledge base documents.

    Usage::

        store = FraudVectorStore()
        store.add_documents(docs)
        results = store.similarity_search_with_score("card not present fraud", k=5)
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        embeddings: Embeddings | None = None,
    ) -> None:
        self._persist_dir = persist_dir or _settings.vector_store.persist_dir
        self._collection_name = (
            collection_name or _settings.vector_store.collection_name
        )
        self._embeddings = embeddings or get_embeddings()

        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

        self._chroma = Chroma(
            collection_name=self._collection_name,
            embedding_function=self._embeddings,
            persist_directory=self._persist_dir,
        )
        logger.info(
            "vector_store.init",
            collection=self._collection_name,
            persist_dir=self._persist_dir,
            doc_count=self._chroma._collection.count(),
        )

    # ── Ingestion ─────────────────────────────────────────────────────

    def add_documents(
        self,
        documents: list[Document],
        batch_size: int | None = None,
    ) -> list[str]:
        """Add documents to the vector store in batches.

        Args:
            documents: LangChain Document objects with page_content and metadata.
            batch_size: Number of documents per embedding batch.

        Returns:
            List of Chroma document IDs.
        """
        size = batch_size or _settings.vector_store.embedding_batch_size
        ids: list[str] = []
        for i in range(0, len(documents), size):
            batch = documents[i : i + size]
            batch_ids = self._chroma.add_documents(batch)
            ids.extend(batch_ids)
            logger.debug(
                "vector_store.add_batch",
                batch_index=i // size,
                batch_size=len(batch),
                total_added=len(ids),
            )
        logger.info("vector_store.add_complete", total=len(ids))
        return ids

    def delete_collection(self) -> None:
        """Drop and recreate the collection (used during re-ingestion)."""
        self._chroma.delete_collection()
        self._chroma = Chroma(
            collection_name=self._collection_name,
            embedding_function=self._embeddings,
            persist_directory=self._persist_dir,
        )
        logger.info("vector_store.collection_deleted", name=self._collection_name)

    # ── Retrieval ─────────────────────────────────────────────────────

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        """Run a synchronous similarity search.

        Args:
            query: Natural-language query string.
            k: Number of results to return.
            where: Optional ChromaDB metadata filter expression.

        Returns:
            List of (Document, relevance_score) tuples, highest score first.
            Scores are cosine similarity in [0, 1] — 1 = identical.
        """
        results = self._chroma.similarity_search_with_relevance_scores(
            query=query,
            k=k,
            filter=where,
        )
        logger.debug(
            "vector_store.search",
            query=query[:80],
            k=k,
            results=len(results),
        )
        return results

    async def asimilarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        """Async wrapper for similarity_search_with_score.

        LangChain's Chroma implementation is synchronous; this wraps it
        in an executor to avoid blocking the event loop.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.similarity_search_with_score(query, k, where),
        )

    # ── Health ────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return collection health metadata.

        Returns:
            Dict with ``status``, ``doc_count``, and ``collection_name``.
        """
        try:
            count = self._chroma._collection.count()
            return {
                "status": "ok",
                "doc_count": count,
                "collection_name": self._collection_name,
            }
        except Exception as exc:
            logger.error("vector_store.health_check.failed", error=str(exc))
            return {
                "status": "error",
                "error": str(exc),
                "collection_name": self._collection_name,
            }

    @property
    def doc_count(self) -> int:
        """Number of documents currently in the collection."""
        return self._chroma._collection.count()
