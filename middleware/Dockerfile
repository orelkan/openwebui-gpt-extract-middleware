# Build stage: install the locked dependencies into a virtualenv with uv.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
# Use the image's own Python, so the virtualenv also works in the final stage.
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Only the dependency files: this layer is rebuilt when the lockfile changes,
# not on every code change.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev


# Final stage: the virtualenv, the app and the prompt. No uv, tests or dev tools.
FROM python:3.12-slim

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY app ./app
COPY prompts ./prompts

# PYTHONUNBUFFERED makes log lines reach `docker logs` as they are written.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

# Liveness only: /health makes no upstream call, so an OpenAI outage does not
# mark the container unhealthy. The slim image has no curl, hence Python.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
