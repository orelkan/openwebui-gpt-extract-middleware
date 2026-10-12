.PHONY: install format lint typecheck test check run samples up down logs

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

# Runs the sample inputs against the live API to evaluate the system prompt.
# Reads OPENAI_API_KEY from .env and spends credits. Extra flags go in ARGS,
# e.g. make samples ARGS="--case receipt --verbose"
samples:
	cd middleware && uv run --env-file ../.env python -m prompt_eval.run_samples $(ARGS)

# Builds the middleware image and starts the whole stack (Open WebUI,
# PostgreSQL, middleware). Returns when all three are healthy. Needs .env.
up:
	docker compose up -d --build --wait

# Stops the stack. Chats and settings stay in the named volumes; add
# `docker compose down -v` by hand to delete them.
down:
	docker compose down

logs:
	docker compose logs -f middleware
