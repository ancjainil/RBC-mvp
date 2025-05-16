.PHONY: help setup install install-dev lint fmt typecheck test test-unit test-integration \
        run ingest-kb gen-data evaluate docker-up docker-down docker-build clean

PYTHON   := python3
PIP      := pip
APP_PORT := 8000

help:          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────────
setup: install-dev  ## Full dev setup (venv + deps + .env)
	@[ -f .env ] || cp .env.example .env && echo ".env created from example"
	@mkdir -p data/chroma data/synthetic logs
	@echo "✓ Setup complete. Edit .env before running."

install:       ## Install production dependencies
	$(PIP) install -e .

install-dev:   ## Install all dependencies including dev/test extras
	$(PIP) install -e ".[dev,rerank]"

# ── Code Quality ─────────────────────────────────────────────────────────
lint:          ## Run ruff linter
	ruff check src tests scripts

fmt:           ## Auto-format with ruff
	ruff format src tests scripts
	ruff check --fix src tests scripts

typecheck:     ## Run mypy type checker
	mypy src

# ── Testing ──────────────────────────────────────────────────────────────
test:          ## Run all tests with coverage
	pytest -v

test-unit:     ## Run unit tests only
	pytest tests/unit -v

test-integration: ## Run integration tests (requires running services)
	pytest tests/integration -v --timeout=60

# ── Running ──────────────────────────────────────────────────────────────
run:           ## Start FastAPI dev server
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port $(APP_PORT)

run-prod:      ## Start production server with gunicorn
	gunicorn src.api.main:app -k uvicorn.workers.UvicornWorker \
		--workers 4 --bind 0.0.0.0:$(APP_PORT)

# ── Data & Knowledge Base ────────────────────────────────────────────────
ingest-kb:     ## Ingest knowledge base documents into vector store
	$(PYTHON) scripts/ingest_knowledge_base.py

gen-data:      ## Generate synthetic transaction dataset
	$(PYTHON) scripts/generate_synthetic_data.py --customers 200 --transactions 10000

evaluate:      ## Run benchmark evaluation
	$(PYTHON) scripts/run_evaluation.py --output reports/evaluation_$(shell date +%Y%m%d_%H%M%S).json

# ── Docker ───────────────────────────────────────────────────────────────
docker-build:  ## Build Docker image
	docker build -t fraud-detection:latest .

docker-up:     ## Start full stack with docker-compose
	docker-compose up -d
	@echo "API → http://localhost:$(APP_PORT)/docs"
	@echo "Grafana → http://localhost:3000"
	@echo "Prometheus → http://localhost:9090"

docker-down:   ## Stop docker-compose stack
	docker-compose down

docker-logs:   ## Tail app logs
	docker-compose logs -f app

# ── Cleanup ──────────────────────────────────────────────────────────────
clean:         ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build htmlcov .coverage coverage.xml
