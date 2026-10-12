# openwebui-gpt-extract-middleware

A local stack that puts a FastAPI middleware between [Open WebUI](https://github.com/open-webui/open-webui) and OpenAI. The middleware is an OpenAI-compatible proxy that injects a system prompt into every chat completion request, turning GPT into a structured data extractor: paste any messy text and get back a consistent JSON block with confidence scores.

```
User → Open WebUI (v0.6.5) → Middleware (FastAPI) → OpenAI GPT
              │
              └── Database (PostgreSQL, Open WebUI persistence)
```

> **Status:** work in progress. So far the repository contains the middleware scaffolding (app factory, configuration, `GET /health`). The proxy, the prompt, and the Docker stack are not implemented yet.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it downloads the pinned Python 3.12 on its own)
- GNU Make

## Development

```bash
make install     # create the virtualenv and install dependencies
make check       # lint, type check and tests, all at once
```

| Command | What it does |
|---|---|
| `make install` | Install dependencies into `middleware/.venv` |
| `make format` | Format the code and apply auto-fixable lint rules |
| `make lint` | Check formatting and lint rules (ruff) |
| `make typecheck` | Run mypy in strict mode |
| `make test` | Run the unit tests with a coverage report |
| `make check` | `lint`, `typecheck` and `test` |
| `make run` | Run the middleware locally with auto-reload on port 8000 |

The unit tests make no network calls and need no API key.

## Configuration

The middleware reads its configuration from environment variables. See [.env.example](.env.example).

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | | API key used for upstream calls to OpenAI |
| `OPENAI_BASE_URL` | no | `https://api.openai.com/v1` | Upstream OpenAI-compatible API base URL |

## Running the middleware locally

```bash
OPENAI_API_KEY=sk-... make run
curl localhost:8000/health    # {"status":"ok"}
```

The middleware refuses to start when `OPENAI_API_KEY` is missing.

## Running the full stack

To be written once the Docker stack exists.

## Verifying end to end

To be written once the Docker stack exists.

## Design decisions

To be written as the middleware takes shape.
