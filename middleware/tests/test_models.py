from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


def test_list_models_returns_upstream_body(client: TestClient, upstream: respx.MockRouter) -> None:
    models = {"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model"}]}
    upstream.get("/models").mock(return_value=httpx.Response(200, json=models))

    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == models


def test_list_models_calls_upstream_with_middleware_api_key(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    route = upstream.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))

    client.get("/v1/models", headers={"Authorization": "Bearer key-from-open-webui"})

    upstream_request = route.calls.last.request
    assert str(upstream_request.url) == "http://upstream.test/v1/models"
    assert upstream_request.headers["Authorization"] == "Bearer sk-test"


def test_list_models_passes_through_upstream_error(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    error = {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
    upstream.get("/models").mock(return_value=httpx.Response(401, json=error))

    response = client.get("/v1/models")

    assert response.status_code == 401
    assert response.json() == error


@pytest.mark.parametrize(
    ("upstream_failure", "expected_status", "expected_type"),
    [
        (httpx.ReadTimeout("read timed out"), 504, "upstream_timeout"),
        (httpx.ConnectError("connection refused"), 502, "upstream_unreachable"),
    ],
)
def test_list_models_maps_upstream_failure_to_gateway_error(
    client: TestClient,
    upstream: respx.MockRouter,
    upstream_failure: httpx.TransportError,
    expected_status: int,
    expected_type: str,
) -> None:
    upstream.get("/models").mock(side_effect=upstream_failure)

    response = client.get("/v1/models")

    assert response.status_code == expected_status
    assert response.json()["error"]["type"] == expected_type


def test_list_models_logs_the_upstream_call(
    client: TestClient, upstream: respx.MockRouter, log_entries: list[dict[str, Any]]
) -> None:
    upstream.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))

    client.get("/v1/models")

    assert [entry["event"] for entry in log_entries] == [
        "request_received",
        "upstream_request_sent",
        "upstream_response_received",
        "request_completed",
    ]
    assert log_entries[1]["path"] == "/models"
    assert log_entries[2]["status_code"] == 200
