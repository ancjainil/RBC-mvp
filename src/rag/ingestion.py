"""Document ingestion pipeline for the fraud knowledge base.

Parses Markdown, JSON, and plain-text files from ``knowledge_base/``,
chunks them with ``RecursiveCharacterTextSplitter``, stamps metadata,
and writes the resulting chunks to the vector store.

Run via:
    python scripts/ingest_knowledge_base.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from src.rag.vector_store import FraudVectorStore

logger = structlog.get_logger(__name__)

# ── Chunk parameters ──────────────────────────────────────────────────────
_CHUNK_SIZE = 1_000
_CHUNK_OVERLAP = 200


class KnowledgeBaseIngestionPipeline:
    """Ingests all documents in the knowledge base directory.

    Args:
        vector_store: Target :class:`~src.rag.vector_store.FraudVectorStore`.
        knowledge_base_dir: Root directory of the knowledge base.
        chunk_size: Token/character chunk size for the text splitter.
        chunk_overlap: Overlap between consecutive chunks.
    """

    def __init__(
        self,
        vector_store: FraudVectorStore,
        knowledge_base_dir: str = "knowledge_base",
        chunk_size: int = _CHUNK_SIZE,
        chunk_overlap: int = _CHUNK_OVERLAP,
    ) -> None:
        self._store = vector_store
        self._kb_dir = Path(knowledge_base_dir)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )

    def ingest_all(self, reset: bool = False) -> dict[str, Any]:
        """Ingest all supported files in the knowledge base directory.

        Args:
            reset: If ``True``, drop the collection before ingesting.

        Returns:
            Summary dict with ``files_processed``, ``chunks_added``, ``errors``.
        """
        if reset:
            logger.info("ingestion.reset_collection")
            self._store.delete_collection()

        summary: dict[str, Any] = {
            "files_processed": 0,
            "chunks_added": 0,
            "errors": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        for path in sorted(self._kb_dir.rglob("*")):
            if path.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            try:
                chunks = self._ingest_file(path)
                if chunks:
                    ids = self._store.add_documents(chunks)
                    summary["chunks_added"] += len(ids)
                    summary["files_processed"] += 1
                    logger.info(
                        "ingestion.file_done",
                        file=str(path),
                        chunks=len(ids),
                    )
            except Exception as exc:
                logger.error("ingestion.file_error", file=str(path), error=str(exc))
                summary["errors"].append({"file": str(path), "error": str(exc)})

        summary["completed_at"] = datetime.utcnow().isoformat()
        logger.info(
            "ingestion.complete",
            files=summary["files_processed"],
            chunks=summary["chunks_added"],
            errors=len(summary["errors"]),
        )
        return summary

    def _ingest_file(self, path: Path) -> list[Document]:
        """Parse a single file into chunked LangChain Documents.

        Args:
            path: Path to the file to ingest.

        Returns:
            List of :class:`langchain_core.documents.Document` chunks.
        """
        suffix = path.suffix.lower()
        document_type = _infer_document_type(path)

        base_metadata = {
            "source_file": path.name,
            "source_path": str(path),
            "document_type": document_type,
            "last_updated": datetime.utcnow().isoformat(),
        }

        if suffix == ".md":
            return self._ingest_markdown(path, base_metadata)
        if suffix == ".json":
            return self._ingest_json(path, base_metadata)
        if suffix == ".txt":
            return self._ingest_text(path, base_metadata)
        return []

    def _ingest_markdown(
        self, path: Path, metadata: dict[str, Any]
    ) -> list[Document]:
        text = path.read_text(encoding="utf-8")
        raw_doc = Document(page_content=text, metadata=metadata)
        chunks = self._splitter.split_documents([raw_doc])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(chunks)
        return chunks

    def _ingest_json(
        self, path: Path, metadata: dict[str, Any]
    ) -> list[Document]:
        """Convert JSON document to a human-readable text before chunking."""
        data = json.loads(path.read_text(encoding="utf-8"))
        text = _json_to_text(data)
        raw_doc = Document(page_content=text, metadata=metadata)
        chunks = self._splitter.split_documents([raw_doc])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(chunks)
        return chunks

    def _ingest_text(
        self, path: Path, metadata: dict[str, Any]
    ) -> list[Document]:
        text = path.read_text(encoding="utf-8")
        raw_doc = Document(page_content=text, metadata=metadata)
        chunks = self._splitter.split_documents([raw_doc])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(chunks)
        return chunks


# ── Helpers ───────────────────────────────────────────────────────────────


def _infer_document_type(path: Path) -> str:
    """Infer document type from its directory path."""
    parts = {p.lower() for p in path.parts}
    if "regulatory" in parts:
        return "regulatory"
    if "fraud_patterns" in parts:
        return "fraud_pattern"
    if "merchant_risk" in path.name:
        return "merchant_risk"
    return "general"


def _json_to_text(data: Any, depth: int = 0, max_depth: int = 6) -> str:
    """Recursively convert a JSON structure to a readable text representation."""
    if depth > max_depth:
        return str(data)
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            lines.append(f"{'  ' * depth}{k}: {_json_to_text(v, depth + 1, max_depth)}")
        return "\n".join(lines)
    if isinstance(data, list):
        items = [_json_to_text(item, depth + 1, max_depth) for item in data[:50]]
        return "\n".join(f"{'  ' * depth}- {item}" for item in items)
    return str(data)
