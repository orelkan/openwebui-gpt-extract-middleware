"""HTTP client for the upstream OpenAI API."""

import json

import httpx
from fastapi import Response

from app.config import Settings
from app.errors import openai_error_response
from app.logging import elapsed_ms, log_event


def create_upstream_client(settings: Settings) -> httpx.AsyncClient:
    """Build the client shared by all requests.

    It always authenticates with the middleware's own API key; credentials sent
    by the caller are never forwarded.

    The transport retries only failed attempts to open a connection. Nothing
    has reached upstream at that point, so a retry can never duplicate a
    request. Failures after that are not retried.
    """
    return httpx.AsyncClient(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=httpx.Timeout(
            settings.upstream_read_timeout_seconds,
            connect=settings.upstream_connect_timeout_seconds,
        ),
        transport=httpx.AsyncHTTPTransport(retries=settings.upstream_connect_retries),
    )


def log_upstream_response(upstream_response: httpx.Response, sent_at: float) -> None:
    """Log the status upstream answered with and how long it took to answer.

    `sent_at` is the time.perf_counter() reading taken when the request was sent.
    """
    log_event(
        "upstream_response_received",
        status_code=upstream_response.status_code,
        latency_ms=elapsed_ms(sent_at),
    )


def is_json(body: bytes) -> bool:
    """Tell whether a response body parses as JSON."""
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


def passthrough_response(upstream_response: httpx.Response) -> Response:
    """Turn a fully read upstream response into our response.

    Status code and body are kept as they are. Error answers are always
    labelled as JSON: OpenAI sends some of its JSON errors as text/plain, and
    Open WebUI only reads `error.message` from a response declared as JSON.
    An error body that is not JSON at all (a gateway's HTML page, say) is
    replaced by an OpenAI-shaped error with the same status.
    """
    if upstream_response.is_success:
        media_type = upstream_response.headers.get("content-type")
    elif is_json(upstream_response.content):
        media_type = "application/json"
    else:
        return openai_error_response(
            upstream_response.status_code,
            f"The upstream API returned HTTP {upstream_response.status_code}",
            "upstream_error",
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=media_type,
    )
