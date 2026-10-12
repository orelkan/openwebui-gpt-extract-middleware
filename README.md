# openwebui-gpt-extract-middleware

A local stack that puts a FastAPI middleware between [Open WebUI](https://github.com/open-webui/open-webui) and OpenAI. The middleware is an OpenAI-compatible proxy that injects a system prompt into every chat completion request, turning GPT into a structured data extractor: paste any messy text and get back a consistent JSON block with confidence scores.

```
User → Open WebUI (v0.6.5) → Middleware (FastAPI) → OpenAI GPT
              │
              └── Database (PostgreSQL, Open WebUI persistence)
```

> **Status:** work in progress. The middleware proxies chat completions (streaming and non-streaming) and the model list, with the system prompt injected. The shipped prompt is still a placeholder, and structured logging, upstream failure mapping, the readiness endpoint and the Docker stack are not implemented yet.

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
| `SYSTEM_PROMPT_PATH` | no | `middleware/prompts/system_prompt.md` | File holding the system prompt to inject |
| `UPSTREAM_CONNECT_TIMEOUT_SECONDS` | no | `10` | Time allowed to connect to upstream |
| `UPSTREAM_READ_TIMEOUT_SECONDS` | no | `120` | Longest allowed wait between two chunks of an upstream response |

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness. Makes no external calls. |
| `GET /v1/models` | Upstream model list, passed through unchanged. |
| `POST /v1/chat/completions` | Chat completion with the system prompt prepended. With `"stream": true` the upstream SSE stream is relayed as it arrives. |

## Running the middleware locally

```bash
OPENAI_API_KEY=sk-... make run
curl localhost:8000/health    # {"status":"ok"}
curl localhost:8000/v1/models
curl -N localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "gpt-4o-mini", "stream": true, "messages": [{"role": "user", "content": "Invoice 42 from ACME, total $310, due May 1"}]}'
```

The middleware refuses to start when `OPENAI_API_KEY` is missing or when the system prompt file is missing or empty.

## Running the full stack

To be written once the Docker stack exists.

## Verifying end to end

To be written once the Docker stack exists.

## Design decisions

This section grows with the project.

- **The system prompt always goes first, and nothing the client sent is removed.** If Open WebUI sends its own system message, it stays in place after ours.
- **Every chat completion request gets the prompt, with no special cases.** Open WebUI's background tasks (titles, tags) use the same endpoint, so they will be switched off in the Open WebUI configuration instead of being detected in the middleware.
- **Transparent pass-through.** Request fields the middleware does not know are forwarded unchanged, and upstream answers, errors included, are returned with their original status code and body.
- **The middleware uses its own API key.** Any `Authorization` header sent by the caller is ignored and never forwarded. The middleware itself has no authentication, so it must only be reachable by Open WebUI.
- **One shared HTTP client**, created at startup and closed at shutdown, so upstream connections are reused across requests.
- **The prompt is read once at startup** from a file that contains nothing but the prompt.
