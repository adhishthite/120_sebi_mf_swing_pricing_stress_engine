.PHONY: start dev test format lint clean check

start:
	PYTHONPATH=. uv run uvicorn main:app --host 0.0.0.0 --port 8120

dev:
	PYTHONPATH=. uv run uvicorn main:app --host 0.0.0.0 --port 8120 --reload

test:
	PYTHONPATH=. uv run pytest

format:
	uv run ruff format .

lint:
	uv run ruff check .

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache

check:
	uv run ruff check .
	PYTHONPATH=. uv run pytest
