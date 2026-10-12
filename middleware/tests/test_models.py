import httpx
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
