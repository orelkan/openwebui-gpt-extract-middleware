from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_makes_no_upstream_call(client: TestClient, upstream: respx.MockRouter) -> None:
    client.get("/health")

    assert upstream.calls.call_count == 0


def test_ready_returns_ready_when_upstream_accepts_our_key(
    client: TestClient, upstream: respx.MockRouter
) -> None:
    route = upstream.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


def test_ready_returns_503_when_upstream_rejects_our_key(
    client: TestClient, upstream: respx.MockRouter, log_entries: list[dict[str, Any]]
) -> None:
    upstream.get("/models").mock(return_value=httpx.Response(401, json={"error": {}}))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "upstream returned 401"}
    logged_failure = next(e for e in log_entries if e["event"] == "readiness_check_failed")
    assert logged_failure["reason"] == "upstream returned 401"


@pytest.mark.parametrize(
    ("upstream_failure", "expected_reason"),
    [
        (httpx.ConnectTimeout("connect timed out"), "upstream unreachable: ConnectTimeout"),
        (httpx.ConnectError("connection refused"), "upstream unreachable: ConnectError"),
    ],
)
def test_ready_returns_503_when_upstream_is_unreachable(
    client: TestClient,
    upstream: respx.MockRouter,
    upstream_failure: httpx.TransportError,
    expected_reason: str,
) -> None:
    upstream.get("/models").mock(side_effect=upstream_failure)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": expected_reason}


def test_ready_returns_503_before_startup_has_completed(settings: Settings) -> None:
    # Without the `with` block TestClient does not run the app's startup.
    client = TestClient(create_app(settings))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "startup not completed"}
