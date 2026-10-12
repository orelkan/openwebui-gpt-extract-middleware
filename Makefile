.PHONY: install format lint typecheck test check run

install:
	cd middleware && uv sync

# Applies formatting and the auto-fixable lint rules (e.g. import sorting).
format:
	cd middleware && uv run ruff format . && uv run ruff check --fix .

lint:
	cd middleware && uv run ruff format --check . && uv run ruff check .

typecheck:
	cd middleware && uv run mypy app prompt_eval tests

test:
	cd middleware && uv run pytest --cov=app --cov-report=term-missing

check: lint typecheck test

# Needs OPENAI_API_KEY in the environment.
run:
	cd middleware && uv run uvicorn app.main:create_app --factory --reload
