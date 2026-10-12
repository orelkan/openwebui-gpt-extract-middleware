# openwebui-gpt-extract-middleware

A local stack that puts a FastAPI middleware between [Open WebUI](https://github.com/open-webui/open-webui) and OpenAI. The middleware is an OpenAI-compatible proxy that injects a system prompt into every chat completion request, turning GPT into a structured data extractor: paste any messy text and get back a consistent JSON block with confidence scores.

```
User → Open WebUI (v0.6.5) → Middleware (FastAPI) → OpenAI GPT
              │
              └── Database (PostgreSQL, Open WebUI persistence)
```

> **Status:** work in progress. The middleware, the extraction prompt and the Docker stack are complete. The smoke test script and the step-by-step verification guide are still to come.

The prompt, its design and how it was tested are described in [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md).

## Prerequisites

- Docker with the Compose plugin, to run the stack
- An OpenAI API key with credit
- GNU Make
- [uv](https://docs.astral.sh/uv/), only for development (it downloads the pinned Python 3.12 on its own)

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
| `make samples` | Run the prompt's sample inputs against the live API (needs `.env`, spends credits) |
| `make up` | Build and start the whole stack; returns when all three services are healthy |
| `make down` | Stop the stack (data is kept) |
| `make logs` | Follow the middleware's logs |

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
| `UPSTREAM_CONNECT_RETRIES` | no | `2` | Extra attempts when a connection to upstream cannot be opened |
| `READINESS_TIMEOUT_SECONDS` | no | `5` | How long `GET /ready` waits for upstream |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness. Makes no external calls. |
| `GET /ready` | Readiness. 200 when startup has finished and OpenAI accepts the API key (checked by listing models); otherwise 503 with the reason. |
| `GET /v1/models` | Upstream model list, passed through unchanged. |
| `POST /v1/chat/completions` | Chat completion with the system prompt prepended. With `"stream": true` the upstream SSE stream is relayed as it arrives. |

Every response carries an `X-Request-ID` header: the caller's own if it sent one, otherwise a generated one.

## Logging

Logs are written to stdout as one JSON object per line. Every line of a request carries the same `request_id`.

```json
{"timestamp": "2026-10-12T12:58:01.120+00:00", "level": "INFO", "event": "prompt_injected", "request_id": "3f2c...", "model": "gpt-4o-mini", "stream": true, "message_count": 1, "content_chars": 412}
```

| Event | Meaning |
|---|---|
| `request_received` | A request arrived (method, path). |
| `prompt_injected` | The system prompt was added (model, stream flag, message count, total text length). |
| `upstream_request_sent` | The request was sent to OpenAI. |
| `upstream_response_received` | OpenAI answered (status code, latency). |
| `upstream_first_byte` | First chunk of a stream arrived (latency). |
| `stream_completed` | A stream finished normally (chunk count, bytes, duration). |
| `upstream_error` | A timeout, connection failure or broken stream (error type, whether mid-stream). |
| `readiness_check_failed` | `GET /ready` answered 503 (reason). |
| `unhandled_error` | A bug in the middleware, with the traceback. |
| `request_completed` | The response was fully sent (status code, total latency). |

The API key, `Authorization` headers and message contents are never logged; only message counts and lengths are.

Requests to `/health` are logged at DEBUG, because the container healthcheck calls it every 30 seconds. Set `LOG_LEVEL=DEBUG` to see them.

## Failure handling

All errors use OpenAI's error format, `{"error": {"message", "type", "param", "code"}}`, so Open WebUI can display them.

| Situation | Response |
|---|---|
| Upstream does not connect or answer in time | `504`, type `upstream_timeout` |
| Upstream cannot be reached, or the connection breaks before an answer | `502`, type `upstream_unreachable` |
| Upstream answers with an error (401, 429, 5xx...) | Same status and body, always labelled `application/json` |
| Upstream answers with a non-JSON error (e.g. an HTML page) | Same status, type `upstream_error` |
| Upstream fails in the middle of a stream | The stream ends with a `data: {"error": ...}` event followed by `data: [DONE]` |
| Invalid request body | `400`, type `invalid_request_error` |
| Bug in the middleware | `500`, type `internal_error` |

Only failed attempts to open a connection are retried. A request that reached OpenAI is never sent twice.

## Running the middleware locally

```bash
OPENAI_API_KEY=sk-... make run
curl localhost:8000/health    # {"status":"ok"}
curl localhost:8000/ready     # {"status":"ready"}, or 503 with the reason
curl localhost:8000/v1/models
curl -N localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "gpt-4o-mini", "stream": true, "messages": [{"role": "user", "content": "Invoice 42 from ACME, total $310, due May 1"}]}'
```

The middleware refuses to start when `OPENAI_API_KEY` is missing or when the system prompt file is missing or empty.

## Evaluating the prompt

`make samples` sends fourteen sample texts (email, receipt, job listing, medical report, legal paragraph, payment confirmation, personal record and edge cases) to the live API with the system prompt injected, three times each. It checks every reply against the output format and per-sample expectations, and reports how much the repeats agree with each other.

```bash
cp .env.example .env          # then put your key in OPENAI_API_KEY
make samples ARGS="--reasoning-effort none --temperature 0"
make samples ARGS="--case receipt --runs 1 --verbose"
```

| Flag | Default | Meaning |
|---|---|---|
| `--model` | `gpt-6-luna` | Model to test |
| `--reasoning-effort` | not sent | Sent as `reasoning_effort` |
| `--temperature` | not sent | Sent as `temperature` |
| `--runs` | `3` | Repeats per sample |
| `--case` | all | Run a single sample by name |
| `--workers` | `8` | Requests sent at the same time |
| `--verbose` | off | Print every reply |

It calls OpenAI directly, so the middleware does not need to be running. It is not part of `make check`: it needs a key and costs a little on each run.

### Recommended model settings

The middleware does not set model parameters; they are chosen per model in Open WebUI. The prompt was tuned and measured on `gpt-6-luna` with **reasoning effort `none`** and **temperature `0`**, which makes repeated extractions of the same text agree about twice as often as the model's defaults. The measurements are in [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md).

## Running the full stack

```bash
cp .env.example .env          # then put your key in OPENAI_API_KEY
make up
```

`make up` builds the middleware image, starts the three services and returns when all of them are healthy. Then open **http://localhost:3000**. There is no login, and `gpt-6-luna` is preselected.

The first start takes a few minutes: Docker pulls the images (Open WebUI is about 6 GB) and Open WebUI downloads an embedding model into its volume. Later starts take about 20 seconds.

| Service | Image | Reachable at | Data |
|---|---|---|---|
| `open-webui` | `ghcr.io/open-webui/open-webui:v0.6.5` | http://localhost:3000 | volume `open_webui_data` (files, embedding model) |
| `middleware` | built from [middleware/Dockerfile](middleware/Dockerfile) | http://localhost:8000 | none |
| `postgres` | `postgres:17-alpine` | inside the compose network only | volume `postgres_data` (chats, users, settings) |

Open WebUI starts only after PostgreSQL and the middleware report healthy. Both published ports are bound to `127.0.0.1`.

```bash
make logs                     # follow the middleware's JSON logs
docker compose ps             # status of the three services
make down                     # stop; chats and settings are kept
docker compose down -v        # stop and delete all stored data
```

### Stack configuration

Everything is read from the same `.env`. Only `OPENAI_API_KEY` is required.

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_MODEL` | `gpt-6-luna` | Model preselected in Open WebUI |
| `WEBUI_PORT` | `3000` | Host port of Open WebUI |
| `MIDDLEWARE_PORT` | `8000` | Host port of the middleware |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `openwebui` | Database credentials and name |
| `WEBUI_SECRET_KEY` | `local-dev-secret` | Secret Open WebUI signs its session tokens with |

The middleware variables from the "Configuration" table above are passed to its container as well, except `SYSTEM_PROMPT_PATH`: the image always uses the prompt built into it.

### What is configured in Open WebUI, and why

These are set in [docker-compose.yml](docker-compose.yml):

- **The middleware is the only model backend**, and Ollama is disabled.
- **PostgreSQL instead of the built-in SQLite file**, through `DATABASE_URL`.
- **Background tasks are off** (title, tag, search query, retrieval query and autocomplete generation). Open WebUI sends them through the same chat endpoint, where they would receive the extraction prompt. The visible cost is that chats keep the title "New Chat".
- **No login**, with a single local admin user.
- **The compose file is applied on every start.** Open WebUI normally copies its settings into the database on first start and ignores the environment afterwards; that is switched off, so the repository always describes the running stack. Changes made in the admin Settings screens last until the next restart. Chats and per-model parameters are stored separately and persist.

The model list shows everything OpenAI returns, including models that are not chat models.

## Verifying end to end

To be written once the Docker stack exists.

## Design decisions

This section grows with the project.

- **The system prompt always goes first, and nothing the client sent is removed.** If Open WebUI sends its own system message, it stays in place after ours.
- **Every chat completion request gets the prompt, with no special cases.**
- **Transparent pass-through.** Request fields the middleware does not know are forwarded unchanged, and upstream answers, errors included, are returned with their original status code and body.
- **The middleware uses its own API key.** Any `Authorization` header sent by the caller is ignored and never forwarded. The middleware itself has no authentication, so it must only be reachable by Open WebUI.
- **One shared HTTP client**, created at startup and closed at shutdown, so upstream connections are reused across requests.
- **The prompt is read once at startup** from a file that contains nothing but the prompt.
- **The prompt has one runtime copy and one documented copy, kept equal by a test.** The middleware loads `middleware/prompts/system_prompt.md`; `SYSTEM_PROMPT.md` embeds the same text and a unit test fails if they differ.
- **The output format is enforced by the prompt alone.** The middleware does not validate or repair model replies; the format is checked by code only in the evaluation tooling under `middleware/prompt_eval`.
- **Open WebUI's background tasks are disabled rather than detected.** The alternative was to recognise title and tag requests in the middleware and skip the prompt for them, which would rest on guessing from prompt text and would break "every request gets the prompt".
- **PostgreSQL for persistence.** The assignment asks for a database service; Open WebUI supports PostgreSQL through one variable, and it keeps the data out of the application container.
- **The middleware image holds only what runs.** A build stage installs the locked dependencies with uv; the final image has the virtualenv, the app and the prompt, and runs as a non-root user.
- **Health probes are logged at DEBUG.** The container healthcheck calls `/health` every 30 seconds, which would otherwise bury real requests in the log.
- **Readiness checks OpenAI, liveness does not.** `/ready` makes a real (free) call to list models, so it catches a wrong API key or an unreachable upstream. `/health` only says the process is alive, which is what a container healthcheck should use: an OpenAI outage must not make the container look dead.
- **Upstream errors are always labelled as JSON.** OpenAI returns some JSON errors as `text/plain`. Open WebUI 0.6.5 only reads `error.message` from a response declared as JSON and otherwise shows the raw body.
- **A stream that breaks is ended with an error event, not silently.** The 200 status has already been sent, so the failure is reported inside the stream, in a form Open WebUI 0.6.5 displays as an error.
- **Retries only where they are provably safe.** httpx retries failed connection attempts; nothing was sent yet. Timeouts, 429s and 5xx answers are returned to the user, who can regenerate, instead of risking duplicate completions or long hidden waits.
- **Logging with the standard library.** A small JSON formatter and a context variable for the request ID, with no extra dependency. The request ID middleware is plain ASGI so that `request_completed` is logged when a streamed response has really finished.
