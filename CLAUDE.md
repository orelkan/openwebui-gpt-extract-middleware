# CLAUDE.md

This file guides Claude Code on this repository. Read it fully before doing anything, and re-read the **Workflow** section at the start of every milestone.

---

## 1. Project Overview

A local LLM middleware stack. The goal is a local development environment with three services:

```
User → Open WebUI (v0.6.5) → Middleware (FastAPI) → OpenAI GPT
              │
              └── Database (PostgreSQL, Open WebUI persistence)
```

| Service | Purpose |
|---|---|
| **Open WebUI** | Chat UI, pinned to **v0.6.5** (`ghcr.io/open-webui/open-webui:v0.6.5`). Configured to use the middleware as its only OpenAI-compatible backend. |
| **PostgreSQL** | Persistence for Open WebUI (via `DATABASE_URL`). |
| **Middleware** | FastAPI, OpenAI-compatible proxy. Injects a system prompt into every chat completion request, forwards to OpenAI, and streams the response back. |

### Middleware requirements (all mandatory)
- OpenAI-compatible API proxy, exposing every endpoint Open WebUI needs (at minimum `POST /v1/chat/completions` and `GET /v1/models`).
- Prepends the system prompt to the messages of every chat completion request.
- Streams responses (SSE) back to Open WebUI, and supports non-streaming requests too.
- Structured logs for the full request lifecycle.
- Health and readiness endpoints.
- Graceful handling of upstream OpenAI failures.
- Unit tests covering the core logic.

### The system prompt (prompt engineering task)
The injected prompt turns GPT into a **structured data extractor**:
1. Identify the type of text pasted (email, receipt, job listing, medical report, legal text, anything).
2. Extract all key entities and data points into a **consistent JSON block**.
3. Flag uncertain fields with a **confidence score**.
4. The output format is **always the same, no exceptions**.
5. For follow-up questions (no new text pasted), answer normally but reference the extracted data.

The prompt is delivered in `SYSTEM_PROMPT.md`, together with a short explanation of design choices, edge cases considered, and iterations.

### Deliverables
- `README.md`: setup, configuration, how to run, how to verify end to end, design decisions.
- `SYSTEM_PROMPT.md`: the prompt and its explanation.
- Unit tests for the middleware core logic.
- All configuration needed to run locally (`docker-compose.yml`, `.env.example`, Dockerfile).

---

## 2. Workflow Rules (most important section)

The work happens in **milestones** (see section 7). Never try to solve everything in one go.

### For every milestone
1. **Plan first.** Enter plan mode and produce a plan that contains:
   - Goal and scope of the milestone (and what is explicitly out of scope).
   - Files to create or modify, with a one-line purpose for each.
   - Key design decisions and the alternatives considered.
   - Test plan: what will be tested and how.
   - Proposed commit breakdown (list of commit messages, in order).
   - Open questions for me.
2. **Wait for my explicit approval.** Do not write or modify any code before I approve. If I request changes, revise the plan and wait again.
3. **Implement only the approved milestone.** Follow the commit breakdown. If you need to deviate from the plan in a meaningful way (new dependency, changed design, extra scope), **stop and ask** before continuing.
4. **Verify.** Before declaring the milestone done, run formatting, linting, type checks, and the full test suite. Everything must pass.
5. **Report and stop.** Summarize what was done, list the commits, note anything left open, and update the milestone checklist in section 7. Then stop. Do not start the next milestone until I tell you to.

### General behavior
- Ask when a requirement is ambiguous; do not guess on anything that affects design.
- Prefer the simplest solution that meets the requirement. I must be able to explain every line of the code, so avoid clever abstractions, metaprogramming, and unnecessary dependencies.
- Do not add features that were not requested. Suggest them instead, as a note in your report.
- Never invent library APIs or config variables. If unsure about an Open WebUI 0.6.5 setting or a library behavior, say so and check the documentation or source.

---

## 3. Code Standards

### Language and stack
- **Python 3.11+**, **FastAPI**, **uvicorn**.
- **httpx** (`AsyncClient`) for upstream calls to OpenAI. A single shared client created in the app lifespan, not one per request.
- **pydantic-settings** for configuration from environment variables. No hard-coded secrets, URLs, or timeouts.
- Dependency management with **uv** and a single `pyproject.toml`.

### Style
- Formatting and linting: **ruff** (format + lint). Type checking: **mypy** (strict on the middleware package).
- Full type hints on all functions. Use `from __future__ import annotations` only if needed.
- Small, single-purpose functions and modules. Business logic as **pure functions** where possible (e.g. prompt injection takes messages and returns a new list, never mutating input).
- Clear names over comments. Comments explain *why*, not *what*. Docstrings for public functions and modules.
- No dead code, no commented-out code, no `print` (use the logger).
- Explicit error handling; never use a bare `except`.

### Suggested middleware layout (to be confirmed in Milestone 0's plan)
```
middleware/
  app/
    main.py            # app factory, lifespan, router registration
    config.py          # Settings (pydantic-settings)
    logging.py         # structured logging setup, request-id context
    prompt.py          # system prompt loading + injection (pure logic)
    upstream.py        # OpenAI client wrapper, error mapping
    routes/
      chat.py          # /v1/chat/completions
      models.py        # /v1/models
      health.py        # /health, /ready
  tests/
  Dockerfile
  pyproject.toml
```

### Proxy design principles
- **Pass through transparently.** Accept and forward unknown request fields (e.g. `stream_options`, `tools`, `temperature`) unchanged. Request models must allow extra fields; do not silently drop anything Open WebUI sends.
- The only modification to the request is the system prompt injection (and model mapping, if we decide to add it).
- Stream upstream bytes through without buffering the whole response.
- Return errors in OpenAI's error JSON shape so Open WebUI can display them.

### Points to resolve during planning (raise these in the relevant milestone plan)
- **Existing system messages:** Open WebUI can send its own system message (user or model-level system prompts). Decide whether to prepend ours before it, merge, or replace, and document why.
- **Open WebUI background tasks:** Open WebUI uses the same chat completions endpoint for title, tag, and follow-up generation. Injecting the extraction prompt into those calls will likely break them. Options: detect and skip them, or disable those features via Open WebUI env vars. Propose and document a choice.
- **Readiness semantics:** what makes the middleware "ready" (config loaded, prompt loaded, upstream reachable?) versus "healthy" (process alive).
- **Single source of truth for the prompt:** the prompt text must not be duplicated between `SYSTEM_PROMPT.md` and the code without a test that guarantees they match.

---

## 4. Observability and Resilience

### Structured logging
- JSON logs to stdout, one event per line.
- Every request gets a **request ID** (reuse an incoming `X-Request-ID` header or generate one), included in every log line and returned in the response headers.
- Log lifecycle events, for example: `request_received`, `prompt_injected`, `upstream_request_sent`, `upstream_first_byte`, `stream_completed`, `upstream_error`, `request_completed`. Include model, stream flag, status code, and latency.
- **Never log** the OpenAI API key or authorization headers. Do not log full message contents by default (log counts and lengths instead); make content logging an explicit opt-in debug setting if at all.

### Upstream failure handling
- Configurable connect and read timeouts.
- Map upstream failures to clear responses: timeouts → 504, connection errors → 502, upstream 4xx/5xx (including 401 and 429) → passed through in OpenAI error format with the original status code where it makes sense.
- Retries (if any) only for transient errors and only **before** the stream has started. Never retry mid-stream.
- If the upstream fails **mid-stream**, log it and terminate the stream cleanly in a way Open WebUI can handle (decide the exact behavior in the plan).

### Endpoints
- `GET /health`: liveness, cheap, no external calls.
- `GET /ready`: readiness, as defined during planning.

---

## 5. Testing Rules

- **pytest** with **pytest-asyncio**; **respx** (or an equivalent) to mock httpx calls to OpenAI.
- **Unit tests make no real network calls and need no API key.** An optional live end-to-end test may exist, but it must be marked and skipped unless explicitly enabled with an env var.
- Every milestone that adds logic adds tests for it in the same milestone. Tests are committed with (or right after) the code they cover, never deferred to "later".
- Required coverage of core logic, at minimum:
  - Prompt injection: no messages, existing system message, multiple messages, input not mutated, prompt always first.
  - Prompt loading: file found, file missing or empty (fails fast with a clear error), consistency with `SYSTEM_PROMPT.md`.
  - Chat completions: non-streaming success, streaming success (chunks forwarded in order, `[DONE]` preserved), extra request fields passed through, prompt present in the forwarded body.
  - Upstream failures: timeout, connection error, 401, 429, 500, failure mid-stream.
  - `/v1/models` passthrough and its failure case.
  - `/health` and `/ready`, including the not-ready case.
  - Request ID propagation and the presence of key log events (and absence of secrets in logs).
- Tests must be readable: Arrange / Act / Assert structure, descriptive test names (`test_inject_prompt_keeps_existing_system_message_after_ours`), shared setup in fixtures in `conftest.py`.
- Target meaningful coverage of the middleware package (report the number; aim for 90%+ on core modules) but do not write tests only to raise the percentage.

---

## 6. Git Practices

- Initialize the repo in Milestone 0 with a proper `.gitignore` (Python, `.venv`, `.env`, caches, IDE files).
- **Branch per milestone:** `m<N>-<short-name>` (e.g. `m1-proxy-core`), created from `main`. Ask me before merging into `main`.
- **Small, atomic commits.** One logical change per commit. Each commit should leave the project in a working state with tests passing.
- **Conventional Commits** format: `<type>(<scope>): <summary>` in the imperative mood, max ~72 characters.
  - Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `build`, `ci`.
  - Example: `feat(middleware): inject system prompt into chat requests`
  - Add a body when the *why* is not obvious from the summary.
- Never commit secrets. Only `.env.example` with placeholder values is committed.
- Never force-push, rewrite published history, or amend commits I have already reviewed, unless I ask.
- Stage files explicitly (no `git add -A` without checking `git status` first).

---

## 7. Milestones (proposed, subject to my changes)

Update the checkboxes as milestones are completed.

### [x] Milestone 0: Project scaffolding
- `git init`, `.gitignore`, `README.md` skeleton, `.env.example`.
- Middleware `pyproject.toml` with uv, ruff, mypy, pytest config.
- Minimal FastAPI app with app factory, config via pydantic-settings, and `GET /health`.
- First test (health endpoint) and a `Makefile` (or equivalent) with `install`, `lint`, `format`, `typecheck`, `test`, `up`, `down` targets.
- Optional: pre-commit hooks for ruff.

### [x] Milestone 1: Proxy core
- Shared httpx client in the app lifespan.
- System prompt loading (from a file path in settings) and the pure injection function.
- `POST /v1/chat/completions` for non-streaming and streaming (SSE passthrough).
- `GET /v1/models` passthrough.
- Unit tests for all of the above with mocked upstream.

### [x] Milestone 2: Observability and resilience
- Structured JSON logging with request ID middleware and lifecycle events.
- Timeouts, upstream error mapping, mid-stream failure handling, optional retry policy.
- `GET /ready` with agreed readiness semantics.
- Unit tests for every failure path and for logging behavior.

### [ ] Milestone 3: Prompt engineering
- Design the extraction system prompt: output format, JSON schema, confidence scoring, text type detection, follow-up behavior.
- A small set of sample inputs (email, receipt, job listing, medical report, legal paragraph, edge cases such as empty input, non-English text, mixed content, prompt-injection attempts inside the pasted text).
- An optional script to run the samples against the live API to iterate on the prompt (not part of unit tests).
- `SYSTEM_PROMPT.md`: the prompt, design choices, edge cases, and iteration notes.
- Test guaranteeing the prompt used by the middleware matches `SYSTEM_PROMPT.md`.

### [ ] Milestone 4: Containerization and local stack
- Middleware `Dockerfile` (slim image, non-root user, healthcheck).
- `docker-compose.yml` with Open WebUI **v0.6.5**, PostgreSQL, and middleware: healthchecks, `depends_on` with `condition: service_healthy`, named volumes, single `.env` for configuration.
- Open WebUI configured to use the middleware as its OpenAI base URL, with Ollama disabled and background task behavior handled per the decision from planning.
- Verify the whole stack starts with one command.

### [ ] Milestone 5: End-to-end verification and documentation
- Smoke test script (e.g. `scripts/smoke_test.sh`) that checks health/readiness and sends a real chat completion through the middleware.
- Manual verification steps through the Open WebUI interface.
- Complete `README.md`: architecture, prerequisites, setup, configuration reference, run, verify, run tests, design decisions and trade-offs, known limitations, possible improvements.
- Final review pass: dead code, naming, consistency, all checks green.

---

## 8. Commands

Run from the repository root. Keep this section accurate as commands change.

```bash
make install      # uv sync in middleware/
make format       # ruff format + ruff check --fix
make lint         # ruff format --check + ruff check
make typecheck    # mypy (strict) on app, prompt_eval and tests
make test         # pytest with coverage report
make check        # lint + typecheck + test
make run          # run the middleware locally with reload (needs OPENAI_API_KEY)
make samples      # run prompt samples against the live API (needs .env, spends credits)
# run stack:      TBD (Milestone 4)
# stop stack:     TBD (Milestone 4)
```
