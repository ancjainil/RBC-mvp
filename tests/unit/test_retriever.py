"""Unit tests for the FraudRetriever."""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.rag.retriever import FraudRetriever
from src.rag.vector_store import FraudVectorStore
from langchain_core.documents import Document


@pytest.fixture
def mock_vector_store() -> MagicMock:
    store = MagicMock(spec=FraudVectorStore)
    return store


@pytest.fixture
def retriever(mock_vector_store: MagicMock) -> FraudRetriever:
    with patch("src.rag.retriever._settings") as mock_settings:
        mock_settings.vector_store.similarity_threshold = 0.75
        mock_settings.vector_store.top_k = 5
        mock_settings.flags.enable_reranking = False
        r = FraudRetriever(
            vector_store=mock_vector_store,
            similarity_threshold=0.75,
            top_k=5,
            enable_reranking=False,
        )
    return r


class TestFraudRetriever:
    def test_retrieve_filters_by_threshold(
        self, retriever: FraudRetriever, mock_vector_store: MagicMock
    ) -> None:
        doc_above = Document(page_content="CNP fraud pattern", metadata={"source_file": "cnp.md"})
        doc_below = Document(page_content="Low score doc", metadata={"source_file": "other.md"})

        mock_vector_store.similarity_search_with_score.return_value = [
            (doc_above, 0.85),  # above threshold
            (doc_below, 0.60),  # below threshold — should be filtered
        ]

        results = retriever.retrieve("card not present fraud", k=5)
        assert len(results) == 1
        assert results[0]["content"] == "CNP fraud pattern"
        assert results[0]["score"] == 0.85

    def test_retrieve_returns_metadata(
        self, retriever: FraudRetriever, mock_vector_store: MagicMock
    ) -> None:
        doc = Document(
            page_content="Account takeover patterns",
            metadata={"source_file": "ato.md", "document_type": "fraud_pattern"},
        )
        mock_vector_store.similarity_search_with_score.return_value = [(doc, 0.90)]

        results = retriever.retrieve("account takeover")
        assert results[0]["metadata"]["source_file"] == "ato.md"
        assert results[0]["metadata"]["document_type"] == "fraud_pattern"

    def test_retrieve_empty_when_no_matches_above_threshold(
        self, retriever: FraudRetriever, mock_vector_store: MagicMock
    ) -> None:
        mock_vector_store.similarity_search_with_score.return_value = [
            (Document(page_content="x", metadata={}), 0.50)
        ]
        results = retriever.retrieve("geo velocity fraud")
        assert results == []

    @pytest.mark.asyncio
    async def test_aretrieve_async(
        self, retriever: FraudRetriever, mock_vector_store: MagicMock
    ) -> None:
        doc = Document(page_content="Synthetic identity", metadata={"source_file": "sif.md"})
        mock_vector_store.asimilarity_search_with_score = AsyncMock(
            return_value=[(doc, 0.80)]
        )
        results = await retriever.aretrieve("synthetic identity fraud")
        assert len(results) == 1
