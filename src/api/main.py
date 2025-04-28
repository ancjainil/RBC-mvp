"""FastAPI application entry point.

Initialises the app, attaches middleware, registers routes, and sets up
structured logging and LangSmith tracing on startup.
"""

from __future__ import annotations

import logging
import logging.config
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config.settings import get_settings
from src.api.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware
from src.api.routes import router
from src.monitoring.traces import configure_langsmith

_settings = get_settings()

# ── Logging setup ─────────────────────────────────────────────────────────


def _configure_logging() -> None:
    """Initialise structlog + stdlib logging from logging_config.yaml."""
    log_config_path = Path("config/logging_config.yaml")
    if log_config_path.exists():
        with open(log_config_path) as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if _settings.logging.format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_logging()
logger = structlog.get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup initialisation and shutdown cleanup."""
    logger.info(
        "app.startup",
        environment=_settings.api.environment,
        llm_provider=_settings.llm.provider,
        version="1.0.0",
    )

    # Warm up singletons at startup (avoids cold-start on first request)
    from src.api.dependencies import (
        get_behavioral_agent,
        get_compiled_graph,
        get_context_agent,
        get_orchestrator_agent,
        get_transaction_agent,
        get_vector_store,
    )

    try:
        get_vector_store()
        get_transaction_agent()
        get_behavioral_agent()
        get_context_agent()
        get_orchestrator_agent()
        get_compiled_graph()
        logger.info("app.startup.agents_ready")
    except Exception as exc:
        logger.error("app.startup.agent_init_failed", error=str(exc))

    # Configure LangSmith tracing if enabled
    if _settings.flags.enable_langsmith:
        configure_langsmith()

    yield

    logger.info("app.shutdown")


# ── Rate limiter ──────────────────────────────────────────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{_settings.api.rate_limit_per_minute}/minute"],
)


# ── App factory ───────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Fraud Detection Multi-Agent API",
        description=(
            "Production-grade multi-agent fraud detection system using LangChain, "
            "LangGraph, and RAG.  Built for financial institutions."
        ),
        version="1.0.0",
        docs_url="/docs" if not _settings.api.is_production else None,
        redoc_url="/redoc" if not _settings.api.is_production else None,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "fraud-detection", "description": "Transaction scoring endpoints"},
            {"name": "audit", "description": "Audit trail retrieval"},
            {"name": "ops", "description": "Operational health and metrics"},
        ],
    )

    # ── Middleware (order matters — outermost added last) ──────────────
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not _settings.api.is_production else [],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Routes ────────────────────────────────────────────────────────
    app.include_router(router)

    return app


app = create_app()
