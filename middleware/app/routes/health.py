"""Liveness and readiness endpoints."""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.logging import log_event

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Report that the process is alive. Makes no external calls."""
    return {"status": "ok"}


def not_ready(reason: str) -> JSONResponse:
    """Build the 503 answer of the readiness check and log why."""
    log_event("readiness_check_failed", level=logging.WARNING, reason=reason)
    return JSONResponse(status_code=503, content={"status": "not_ready", "reason": reason})


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Report whether the middleware can serve chat requests right now.

    Ready means startup has finished and upstream accepts our API key, checked
    with a real call to its model list. Unlike /health, this fails when the
    key is wrong or OpenAI cannot be reached.
    """
    state = request.app.state
    upstream_client: httpx.AsyncClient | None = getattr(state, "upstream_client", None)
    if upstream_client is None or not getattr(state, "system_prompt", None):
        return not_ready("startup not completed")

    settings: Settings = state.settings
    try:
        upstream_response = await upstream_client.get(
            "/models", timeout=settings.readiness_timeout_seconds
        )
    except httpx.TransportError as error:
        return not_ready(f"upstream unreachable: {type(error).__name__}")
    if not upstream_response.is_success:
        return not_ready(f"upstream returned {upstream_response.status_code}")
    return JSONResponse(content={"status": "ready"})
