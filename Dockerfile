FROM python:3.11-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencies ─────────────────────────────────────────────────────────
FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[rerank]"

# ── Application ──────────────────────────────────────────────────────────
FROM deps AS app

COPY config/ config/
COPY src/    src/
COPY scripts/ scripts/
COPY knowledge_base/ knowledge_base/

# Non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data/chroma /app/logs && \
    chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-config", "config/logging_config.yaml"]
