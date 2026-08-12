.PHONY: all dev start test format lint clean check

# ------------------------------------------------------------------------------
# BFSI Solution Factory Standard Root Makefile
# Project: 120_sebi_mf_swing_pricing_stress_engine
# Backend Port: 8120 | Frontend Port: 3120
# ------------------------------------------------------------------------------

all: dev

run-mock:
	@echo "Starting project in MOCK mode..."
	$(MAKE) dev

run-portless:
	@echo "Starting project with portless routing..."
	$(MAKE) dev

dev:
	@echo "Starting backend and frontend in development mode..."
	npx concurrently -k -p "[{name}]" -n "BACKEND,FRONTEND" -c "blue.bold,cyan.bold" \
		"cd backend && PYTHONPATH=. uv run uvicorn main:app --host 0.0.0.0 --port 8120 --reload" \
		"cd frontend && pnpm dev -p 3120"

start:
	@echo "Starting backend and frontend in production mode..."
	npx concurrently -k -p "[{name}]" -n "BACKEND,FRONTEND" -c "blue.bold,cyan.bold" \
		"cd backend && PYTHONPATH=. uv run uvicorn main:app --host 0.0.0.0 --port 8120" \
		"cd frontend && pnpm start -p 3120"

test:
	@echo "Running backend test suite..."
	cd backend && PYTHONPATH=. uv run pytest
	@echo "Running frontend validation..."
	cd frontend && $(MAKE) test

format:
	@echo "Formatting backend code..."
	cd backend && uv run ruff format .
	@echo "Formatting frontend code..."
	cd frontend && pnpm biome format --write src/

lint:
	@echo "Linting backend code..."
	cd backend && uv run ruff check .
	@echo "Linting frontend code..."
	cd frontend && pnpm biome lint --write src/

check:
	@echo "Running full verification pipeline..."
	$(MAKE) format
	$(MAKE) lint
	$(MAKE) test

clean:
	@echo "Cleaning temporary files and build artifacts..."
	cd backend && $(MAKE) clean || rm -rf .pytest_cache __pycache__
	cd frontend && $(MAKE) clean || rm -rf .next dist out
