"""Model listing, passed through from upstream."""

import time

import httpx
from fastapi import APIRouter, Request, Response

from app.logging import elapsed_ms, log_event
from app.upstream import passthrough_response

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> Response:
    """Return the upstream model list unchanged."""
    upstream_client: httpx.AsyncClient = request.app.state.upstream_client
    log_event("upstream_request_sent", path="/models")
    sent_at = time.perf_counter()
    upstream_response = await upstream_client.get("/models")
    log_event(
        "upstream_response_received",
        status_code=upstream_response.status_code,
        latency_ms=elapsed_ms(sent_at),
    )
    return passthrough_response(upstream_response)
