"""Model listing, passed through from upstream."""

import time

import httpx
from fastapi import APIRouter, Request, Response

from app.logging import log_event
from app.upstream import log_upstream_response, passthrough_response

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> Response:
    """Return the upstream model list unchanged."""
    upstream_client: httpx.AsyncClient = request.app.state.upstream_client
    log_event("upstream_request_sent", path="/models")
    sent_at = time.perf_counter()
    upstream_response = await upstream_client.get("/models")
    log_upstream_response(upstream_response, sent_at)
    return passthrough_response(upstream_response)
