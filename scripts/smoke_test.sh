#!/usr/bin/env bash
# End-to-end smoke test for the running stack. Start the stack with `make up`
# first, then run `make smoke`.
#
# Prints one PASS or FAIL line per check and exits non-zero if any check fails.
# It sends three real chat requests, so it needs a working OPENAI_API_KEY in
# the stack and costs a fraction of a cent per run.

# No `set -e`: a failing check must be reported, not stop the script.
set -u -o pipefail

cd "$(dirname "$0")/.."

# Use the same ports and model as the stack. Every variable has a default, so
# the file is optional here.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

MIDDLEWARE="http://localhost:${MIDDLEWARE_PORT:-8000}"
WEBUI="http://localhost:${WEBUI_PORT:-3000}"
MODEL="${DEFAULT_MODEL:-gpt-6-luna}"
SAMPLE_TEXT='Invoice 42 from ACME Ltd, total 310.50 USD, due May 1.'
# Seconds to wait for one request. Chat completions can be slow.
TIMEOUT=120

failures=0

# check "description" command [arguments...]
check() {
    local description="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS  $description"
    else
        echo "FAIL  $description"
        failures=$((failures + 1))
    fi
}

# Succeeds when GET <url> answers with <status>.
status_is() {
    local url="$1" expected="$2"
    [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$url")" = "$expected" ]
}

# The JSON body of a chat completion request; $1 is "true" or "false" for streaming.
chat_body() {
    printf '{"model": "%s", "stream": %s, "messages": [{"role": "user", "content": "%s"}]}' \
        "$MODEL" "$1" "$SAMPLE_TEXT"
}

# POSTs a chat completion to <base url><path> and prints the response body.
# --fail makes an error status count as a failure. Extra arguments go to curl.
post_chat() {
    local url="$1" stream="$2"
    shift 2
    curl -s --fail --max-time "$TIMEOUT" "$url" \
        -H 'Content-Type: application/json' -d "$(chat_body "$stream")" "$@"
}

models_include_the_model() {
    curl -s --fail --max-time "$TIMEOUT" "$MIDDLEWARE/v1/models" | grep -q "\"$MODEL\""
}

# An extraction names its first key; an error body would not contain it.
middleware_chat_returns_extraction() {
    post_chat "$MIDDLEWARE/v1/chat/completions" false | grep -q 'document_type'
}

request_id_is_echoed() {
    curl -s -o /dev/null -D - --max-time "$TIMEOUT" "$MIDDLEWARE/health" \
        -H 'X-Request-ID: smoke-test-id' | grep -qi '^x-request-id: smoke-test-id'
}

stream_ends_with_done() {
    post_chat "$MIDDLEWARE/v1/chat/completions" true | grep -v '^[[:space:]]*$' | tail -n 1 |
        grep -q 'data: \[DONE\]'
}

# Open WebUI runs without login, and its sign-in endpoint then hands out a
# token for the single local user. That token lets us send a chat through
# Open WebUI itself, exactly as the page does.
webui_chat_returns_extraction() {
    local token
    token="$(curl -s --fail --max-time "$TIMEOUT" "$WEBUI/api/v1/auths/signin" \
        -H 'Content-Type: application/json' -d '{"email": "", "password": ""}' |
        grep -o '"token":"[^"]*"' | cut -d'"' -f4)"
    [ -n "$token" ] || return 1
    post_chat "$WEBUI/api/chat/completions" false -H "Authorization: Bearer $token" |
        grep -q 'document_type'
}

# to_regclass prints the table name when the table exists, and nothing otherwise.
postgres_has_chat_table() {
    docker compose exec -T postgres sh -c \
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "select to_regclass('\''public.chat'\'')"' |
        grep -qx 'chat'
}

echo "Smoke test: middleware $MIDDLEWARE, Open WebUI $WEBUI, model $MODEL"

check "middleware is alive (GET /health)" status_is "$MIDDLEWARE/health" 200
check "middleware is ready: OpenAI accepts the API key (GET /ready)" status_is "$MIDDLEWARE/ready" 200
check "middleware lists the model $MODEL (GET /v1/models)" models_include_the_model
check "chat through the middleware returns an extraction" middleware_chat_returns_extraction
check "middleware echoes X-Request-ID" request_id_is_echoed
check "streaming chat through the middleware ends with [DONE]" stream_ends_with_done
check "Open WebUI is up (GET /health)" status_is "$WEBUI/health" 200
check "chat through Open WebUI returns an extraction" webui_chat_returns_extraction
check "PostgreSQL holds Open WebUI's chat table" postgres_has_chat_table

if [ "$failures" -eq 0 ]; then
    echo "All checks passed."
else
    echo "$failures check(s) failed."
    exit 1
fi
