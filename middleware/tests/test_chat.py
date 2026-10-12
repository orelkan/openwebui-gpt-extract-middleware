import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.routes.chat import count_content_chars, stream_error_event, stream_upstream_body

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}}],
}

SSE_CHUNKS = [
    b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n',
    b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n',
    b"data: [DONE]\n\n",
]


async def sse_stream() -> AsyncIterator[bytes]:
    for chunk in SSE_CHUNKS:
        yield chunk


async def broken_sse_stream() -> AsyncIterator[bytes]:
    """An upstream stream that dies after its first chunk."""
    yield SSE_CHUNKS[0]
    raise httpx.ReadError("connection reset")


MINIMAL_REQUEST: dict[str, Any] = {"model": "gpt-4o-mini", "messages": []}


def mock_chat(upstream: respx.MockRouter, response: httpx.Response | None = None) -> respx.Route:
    """Make the fake upstream answer chat completions, by default with a 200 completion."""
    return upstream.post("/chat/completions").mock(
        return_value=response or httpx.Response(200, json=COMPLETION)
    )


def sse_response(stream: AsyncIterator[bytes]) -> httpx.Response:
    """A 200 upstream answer that streams the given chunks as server-sent events."""
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)


def forwarded_body(route: respx.Route) -> Any:
    """The JSON body the middleware sent upstream in its last call."""
    return json.loads(route.calls.last.request.content)


def test_chat_completion_returns_upstream_response(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    mock_chat(upstream)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == COMPLETION


def test_chat_completion_forwards_system_prompt_before_client_messages(
    client: TestClient, upstream: respx.MockRouter, system_prompt: str
) -> None:
    route = mock_chat(upstream)
    messages = [
        {"role": "system", "content": "Client prompt"},
        {"role": "user", "content": "Hello"},
    ]

    client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": messages})

    assert forwarded_body(route)["messages"] == [
        {"role": "system", "content": system_prompt},
        *messages,
    ]


def test_chat_completion_passes_extra_fields_through_unchanged(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    route = mock_chat(upstream)
    request_body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.2,
        "stop": None,
        "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
        "metadata": {"nested": {"key": [1, 2, 3]}},
    }

    client.post("/v1/chat/completions", json=request_body)

    sent = forwarded_body(route)
    sent_without_messages = {key: value for key, value in sent.items() if key != "messages"}
    expected = {key: value for key, value in request_body.items() if key != "messages"}
    assert sent_without_messages == expected


def test_chat_completion_calls_upstream_with_middleware_api_key(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    route = mock_chat(upstream)

    client.post(
        "/v1/chat/completions",
        json=MINIMAL_REQUEST,
        headers={"Authorization": "Bearer key-from-open-webui"},
    )

    upstream_request = route.calls.last.request
    assert str(upstream_request.url) == "http://upstream.test/v1/chat/completions"
    assert upstream_request.headers["Authorization"] == "Bearer sk-test"


def test_chat_completion_passes_through_upstream_error(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    error = {"error": {"message": "The server had an error", "type": "server_error"}}
    mock_chat(upstream, httpx.Response(500, json=error))

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST)

    assert response.status_code == 500
    assert response.json() == error


def test_chat_completion_rejects_request_without_messages(client: TestClient) -> None:
    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert "messages" in error["message"]


def test_streaming_chat_completion_forwards_whole_stream(
    client: TestClient, upstream: respx.MockRouter, system_prompt: str
) -> None:
    route = mock_chat(upstream, sse_response(sse_stream()))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    ) as response:
        body = response.read()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # TestClient hands the body over in one piece, so this checks content and
    # order; chunk-by-chunk relaying is covered by the stream_upstream_body test.
    assert body == b"".join(SSE_CHUNKS)
    assert body.endswith(b"data: [DONE]\n\n")
    assert forwarded_body(route)["stream"] is True
    assert forwarded_body(route)["messages"][0] == {"role": "system", "content": system_prompt}


def test_streaming_chat_completion_passes_through_upstream_error(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    error = {"error": {"message": "Rate limit reached", "type": "rate_limit_error"}}
    mock_chat(upstream, httpx.Response(429, json=error))

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST | {"stream": True})

    assert response.status_code == 429
    assert response.headers["content-type"] == "application/json"
    assert response.json() == error


def test_stream_upstream_body_relays_each_chunk_separately() -> None:
    upstream_response = httpx.Response(200, content=sse_stream())

    async def collect_chunks() -> list[bytes]:
        return [
            chunk async for chunk in stream_upstream_body(upstream_response, time.perf_counter())
        ]

    received_chunks = asyncio.run(collect_chunks())

    assert received_chunks == SSE_CHUNKS


def test_stream_upstream_body_closes_upstream_when_consumer_stops_early() -> None:
    upstream_response = httpx.Response(200, content=sse_stream())

    async def read_first_chunk_then_stop() -> bytes:
        body = stream_upstream_body(upstream_response, time.perf_counter())
        first_chunk = await anext(body)
        await body.aclose()
        return first_chunk

    first_chunk = asyncio.run(read_first_chunk_then_stop())

    assert first_chunk == SSE_CHUNKS[0]
    assert upstream_response.is_closed


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("upstream_failure", "expected_status", "expected_type"),
    [
        (httpx.ConnectTimeout("connect timed out"), 504, "upstream_timeout"),
        (httpx.ReadTimeout("read timed out"), 504, "upstream_timeout"),
        (httpx.ConnectError("connection refused"), 502, "upstream_unreachable"),
        (httpx.RemoteProtocolError("server disconnected"), 502, "upstream_unreachable"),
    ],
)
def test_chat_completion_maps_upstream_failure_to_gateway_error(
    client: TestClient,
    upstream: respx.MockRouter,
    log_entries: list[dict[str, Any]],
    stream: bool,
    upstream_failure: httpx.TransportError,
    expected_status: int,
    expected_type: str,
) -> None:
    upstream.post("/chat/completions").mock(side_effect=upstream_failure)

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST | {"stream": stream})

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["type"] == expected_type
    logged_error = next(entry for entry in log_entries if entry["event"] == "upstream_error")
    assert logged_error["error_type"] == type(upstream_failure).__name__
    assert logged_error["status_code"] == expected_status
    assert logged_error["mid_stream"] is False


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("upstream_status", [401, 429, 500])
def test_chat_completion_returns_upstream_json_error_as_json_even_if_labelled_text(
    client: TestClient, upstream: respx.MockRouter, stream: bool, upstream_status: int
) -> None:
    error = {"error": {"message": "Upstream said no", "type": "some_error"}}
    upstream.post("/chat/completions").mock(
        return_value=httpx.Response(
            upstream_status, headers={"content-type": "text/plain"}, content=json.dumps(error)
        )
    )

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST | {"stream": stream})

    assert response.status_code == upstream_status
    assert response.headers["content-type"] == "application/json"
    assert response.json() == error


def test_chat_completion_wraps_non_json_upstream_error_in_openai_format(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    mock_chat(upstream, httpx.Response(502, html="<html><body>Bad Gateway</body></html>"))

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"] == {
        "message": "The upstream API returned HTTP 502",
        "type": "upstream_error",
        "param": None,
        "code": None,
    }


def test_streaming_chat_completion_reports_mid_stream_failure_inside_the_stream(
    client: TestClient, upstream: respx.MockRouter, log_entries: list[dict[str, Any]]
) -> None:
    mock_chat(upstream, sse_response(broken_sse_stream()))

    response = client.post("/v1/chat/completions", json=MINIMAL_REQUEST | {"stream": True})

    assert response.status_code == 200
    assert response.content.startswith(SSE_CHUNKS[0])
    events = [line[len("data: ") :] for line in response.text.splitlines() if line]
    assert json.loads(events[-2])["error"]["type"] == "upstream_error"
    assert events[-1] == "[DONE]"
    logged_error = next(entry for entry in log_entries if entry["event"] == "upstream_error")
    assert logged_error["error_type"] == "ReadError"
    assert logged_error["mid_stream"] is True


def test_stream_upstream_body_closes_upstream_after_mid_stream_failure() -> None:
    upstream_response = httpx.Response(200, content=broken_sse_stream())

    async def collect_chunks() -> list[bytes]:
        return [
            chunk async for chunk in stream_upstream_body(upstream_response, time.perf_counter())
        ]

    received_chunks = asyncio.run(collect_chunks())

    assert received_chunks == [SSE_CHUNKS[0], stream_error_event()]
    assert upstream_response.is_closed


def test_count_content_chars_adds_up_text_contents_only() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "12345"},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]},
        {"role": "user", "content": "123"},
    ]

    assert count_content_chars(messages) == 8


def test_chat_completion_logs_its_lifecycle_in_order(
    client: TestClient, upstream: respx.MockRouter, log_entries: list[dict[str, Any]]
) -> None:
    mock_chat(upstream)

    client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]},
        headers={"X-Request-ID": "caller-id-6"},
    )

    assert [entry["event"] for entry in log_entries] == [
        "request_received",
        "prompt_injected",
        "upstream_request_sent",
        "upstream_response_received",
        "request_completed",
    ]
    assert all(entry["request_id"] == "caller-id-6" for entry in log_entries)
    prompt_injected = log_entries[1]
    assert prompt_injected["model"] == "gpt-4o-mini"
    assert prompt_injected["stream"] is False
    assert prompt_injected["message_count"] == 1
    assert prompt_injected["content_chars"] == 5
    assert log_entries[3]["status_code"] == 200
    assert log_entries[3]["latency_ms"] >= 0


def test_streaming_chat_completion_logs_its_lifecycle_in_order(
    client: TestClient, upstream: respx.MockRouter, log_entries: list[dict[str, Any]]
) -> None:
    mock_chat(upstream, sse_response(sse_stream()))

    client.post("/v1/chat/completions", json=MINIMAL_REQUEST | {"stream": True})

    assert [entry["event"] for entry in log_entries] == [
        "request_received",
        "prompt_injected",
        "upstream_request_sent",
        "upstream_response_received",
        "upstream_first_byte",
        "stream_completed",
        "request_completed",
    ]
    assert len({entry["request_id"] for entry in log_entries}) == 1
    stream_completed = log_entries[5]
    assert stream_completed["chunk_count"] == len(SSE_CHUNKS)
    assert stream_completed["bytes"] == len(b"".join(SSE_CHUNKS))


def test_logs_contain_no_secrets_and_no_message_content(
    client: TestClient,
    upstream: respx.MockRouter,
    log_entries: list[dict[str, Any]],
    system_prompt: str,
) -> None:
    error = {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
    upstream.post("/chat/completions").mock(
        side_effect=[
            sse_response(sse_stream()),
            httpx.Response(401, json=error),
        ]
    )
    request_body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "my private pasted text"}],
    }
    headers = {"Authorization": "Bearer key-from-open-webui"}

    client.post("/v1/chat/completions", json=request_body | {"stream": True}, headers=headers)
    client.post("/v1/chat/completions", json=request_body, headers=headers)

    all_log_text = json.dumps(log_entries).lower()
    assert len(log_entries) > 0
    assert "sk-test" not in all_log_text
    assert "key-from-open-webui" not in all_log_text
    assert "authorization" not in all_log_text
    assert "bearer" not in all_log_text
    assert "my private pasted text" not in all_log_text
    assert system_prompt.lower() not in all_log_text
