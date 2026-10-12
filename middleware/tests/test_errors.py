import json
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import openai_error_response
from app.main import create_app


def test_openai_error_response_has_openai_error_shape() -> None:
    response = openai_error_response(504, "Upstream timed out", "upstream_timeout", "timeout")

    assert response.status_code == 504
    assert json.loads(bytes(response.body)) == {
        "error": {
            "message": "Upstream timed out",
            "type": "upstream_timeout",
            "param": None,
            "code": "timeout",
        }
    }


def test_invalid_request_body_returns_400_in_openai_format(client: TestClient) -> None:
    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": "hi"})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "body.messages: Input should be a valid list",
            "type": "invalid_request_error",
            "param": None,
            "code": None,
        }
    }


def test_unexpected_error_returns_500_in_openai_format_and_is_logged(
    settings: Settings, log_entries: list[dict[str, Any]]
) -> None:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("a bug")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "caller-id-5"})

    assert response.status_code == 500
    assert response.json()["error"] == {
        "message": "Internal server error",
        "type": "internal_error",
        "param": None,
        "code": None,
    }
    logged_error = next(entry for entry in log_entries if entry["event"] == "unhandled_error")
    assert logged_error["level"] == "ERROR"
    assert logged_error["request_id"] == "caller-id-5"
    assert "RuntimeError: a bug" in logged_error["exception"]
