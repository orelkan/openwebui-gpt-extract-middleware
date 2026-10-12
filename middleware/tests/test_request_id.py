from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_response_gets_a_generated_request_id(client: TestClient) -> None:
    response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert int(request_id, 16) >= 0


def test_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "caller-id-1"})

    assert response.headers["X-Request-ID"] == "caller-id-1"


def test_error_response_also_has_request_id(client: TestClient) -> None:
    response = client.get("/no-such-path", headers={"X-Request-ID": "caller-id-2"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "caller-id-2"


def test_request_is_logged_at_start_and_end_with_its_request_id(
    client: TestClient, log_entries: list[dict[str, Any]]
) -> None:
    client.get("/no-such-path", headers={"X-Request-ID": "caller-id-3"})

    received, completed = log_entries
    assert received["event"] == "request_received"
    assert received["level"] == "INFO"
    assert received["method"] == "GET"
    assert received["path"] == "/no-such-path"
    assert completed["event"] == "request_completed"
    assert completed["status_code"] == 404
    assert completed["latency_ms"] >= 0
    assert received["request_id"] == completed["request_id"] == "caller-id-3"


def test_each_request_gets_its_own_request_id(
    client: TestClient, log_entries: list[dict[str, Any]]
) -> None:
    client.get("/no-such-path")
    client.get("/no-such-path")

    request_ids = [entry["request_id"] for entry in log_entries]
    assert request_ids[0] == request_ids[1]
    assert request_ids[2] == request_ids[3]
    assert request_ids[0] != request_ids[2]


def test_health_probe_is_not_logged_at_the_default_level(
    client: TestClient, log_entries: list[dict[str, Any]]
) -> None:
    client.get("/health")

    assert log_entries == []


def test_health_probe_is_logged_at_debug_level(
    settings: Settings, log_entries: list[dict[str, Any]]
) -> None:
    settings.log_level = "DEBUG"

    with TestClient(create_app(settings)) as client:
        log_entries.clear()  # drop the startup log
        client.get("/health")

    assert [entry["event"] for entry in log_entries] == ["request_received", "request_completed"]
    assert all(entry["level"] == "DEBUG" for entry in log_entries)
