"""LangSmith tracing configuration.

When ``ENABLE_LANGSMITH_TRACING=true``, every LangGraph node execution is
automatically traced and visible in the LangSmith dashboard.  No code
changes are required in the agents — LangChain's callback mechanism handles
propagation transparently.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)


def configure_langsmith() -> None:
    """Configure LangSmith tracing via environment variables.

    LangChain reads ``LANGCHAIN_TRACING_V2`` and ``LANGCHAIN_API_KEY``
    from the environment automatically.  This function just validates the
    config and logs the result.
    """
    from config.settings import get_settings

    settings = get_settings()

    if not settings.langsmith.api_key:
        logger.warning(
            "langsmith.disabled",
            reason="LANGCHAIN_API_KEY is not set",
        )
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith.api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith.project

    logger.info(
        "langsmith.enabled",
        project=settings.langsmith.project,
    )


def get_run_url(run_id: str) -> str | None:
    """Return the LangSmith UI URL for a given run ID.

    Args:
        run_id: The LangSmith run UUID.

    Returns:
        A URL string, or None if LangSmith is not configured.
    """
    from config.settings import get_settings

    settings = get_settings()
    if not settings.flags.enable_langsmith:
        return None
    project = settings.langsmith.project
    return f"https://smith.langchain.com/public/{project}/r/{run_id}"
