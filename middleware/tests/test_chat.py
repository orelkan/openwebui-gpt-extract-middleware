import json
from typing import Any

import httpx
import respx
from fastapi.testclient import TestClient

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}}],
}


def forwarded_body(route: respx.Route) -> Any:
    """The JSON body the middleware sent upstream in its last call."""
    return json.loads(route.calls.last.request.content)


def test_chat_completion_returns_upstream_response(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, json=COMPLETION))

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
    route = upstream.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=COMPLETION)
    )
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
    route = upstream.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=COMPLETION)
    )
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
    route = upstream.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=COMPLETION)
    )

    client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": []},
        headers={"Authorization": "Bearer key-from-open-webui"},
    )

    upstream_request = route.calls.last.request
    assert str(upstream_request.url) == "http://upstream.test/v1/chat/completions"
    assert upstream_request.headers["Authorization"] == "Bearer sk-test"


def test_chat_completion_passes_through_upstream_error(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    error = {"error": {"message": "The server had an error", "type": "server_error"}}
    upstream.post("/chat/completions").mock(return_value=httpx.Response(500, json=error))

    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": []})

    assert response.status_code == 500
    assert response.json() == error


def test_chat_completion_rejects_request_without_messages(client: TestClient) -> None:
    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini"})

    assert response.status_code == 422
