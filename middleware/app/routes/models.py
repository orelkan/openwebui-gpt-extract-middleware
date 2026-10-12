"""Model listing, passed through from upstream."""

import httpx
from fastapi import APIRouter, Request, Response

from app.upstream import passthrough_response

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> Response:
    """Return the upstream model list unchanged."""
    upstream_client: httpx.AsyncClient = request.app.state.upstream_client
    upstream_response = await upstream_client.get("/models")
    return passthrough_response(upstream_response)
