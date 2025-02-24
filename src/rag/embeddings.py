"""Embedding model configuration and factory.

Supports:
- OpenAI ``text-embedding-3-small`` (default, via ``langchain-openai``)
- HuggingFace ``sentence-transformers`` (local, no API key required)

The active provider mirrors the ``LLM_PROVIDER`` setting, but can be
overridden independently if you want local embeddings with a cloud LLM.
"""

from __future__ import annotations

from functools import lru_cache

import structlog
from langchain_core.embeddings import Embeddings

from config.settings import get_settings

logger = structlog.get_logger(__name__)
_settings = get_settings()


def build_embeddings(provider: str | None = None) -> Embeddings:
    """Construct and return an embeddings model.

    Args:
        provider: ``"openai"`` or ``"huggingface"``.  If ``None``, the
            configured ``LLM_PROVIDER`` value is used.

    Returns:
        An initialised :class:`langchain_core.embeddings.Embeddings` instance.

    Raises:
        ValueError: If an unsupported provider is specified.
    """
    effective = provider or _settings.llm.provider

    if effective == "openai":
        from langchain_openai import OpenAIEmbeddings

        logger.info(
            "embeddings.init",
            provider="openai",
            model=_settings.llm.openai_embedding_model,
        )
        return OpenAIEmbeddings(
            model=_settings.llm.openai_embedding_model,
            api_key=_settings.llm.openai_api_key,  # type: ignore[arg-type]
        )

    if effective == "anthropic":
        # Anthropic doesn't provide its own embedding API; fall back to a
        # high-quality HuggingFace model for vector store operations.
        logger.info(
            "embeddings.init",
            provider="huggingface",
            reason="anthropic provider selected — falling back to local embeddings",
        )
        return _build_huggingface_embeddings()

    if effective == "huggingface":
        return _build_huggingface_embeddings()

    raise ValueError(f"Unsupported embedding provider: {effective!r}")


def _build_huggingface_embeddings() -> Embeddings:
    """Build a local sentence-transformers embedding model.

    Uses ``BAAI/bge-small-en-v1.5`` — 33M parameters, strong retrieval
    performance, runs on CPU in < 100 ms/batch on modern hardware.
    """
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        model_name = "BAAI/bge-small-en-v1.5"
        logger.info("embeddings.init", provider="huggingface", model=model_name)
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    except ImportError as exc:
        raise ImportError(
            "Install sentence-transformers: pip install sentence-transformers"
        ) from exc


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """Return a cached singleton embeddings instance."""
    return build_embeddings()
