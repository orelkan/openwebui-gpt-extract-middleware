"""Error responses in OpenAI's JSON error format."""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging import log_event

logger = logging.getLogger(__name__)


def openai_error_response(
    status_code: int, message: str, error_type: str, code: str | None = None
) -> JSONResponse:
    """Build an error response shaped like the ones OpenAI returns.

    Clients of an OpenAI-compatible API, Open WebUI included, read the
    message from `error.message`.
    """
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": code}},
    )


async def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    """Answer an invalid request body with 400, as OpenAI does, instead of FastAPI's 422."""
    # Starlette types every handler as taking Exception; this one is only
    # registered for RequestValidationError.
    assert isinstance(error, RequestValidationError)
    problems = [
        f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
        for problem in error.errors()
    ]
    return openai_error_response(400, "; ".join(problems), "invalid_request_error")


async def handle_upstream_timeout(request: Request, error: Exception) -> JSONResponse:
    """Answer 504 when upstream did not connect or respond within the configured timeouts."""
    log_event(
        logger,
        "upstream_error",
        level=logging.ERROR,
        error_type=type(error).__name__,
        status_code=504,
        mid_stream=False,
    )
    return openai_error_response(
        504, "The upstream API did not respond in time", "upstream_timeout"
    )


async def handle_upstream_unreachable(request: Request, error: Exception) -> JSONResponse:
    """Answer 502 when the connection to upstream failed or broke before a response arrived."""
    log_event(
        logger,
        "upstream_error",
        level=logging.ERROR,
        error_type=type(error).__name__,
        status_code=502,
        mid_stream=False,
    )
    return openai_error_response(502, "Could not reach the upstream API", "upstream_unreachable")


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Answer a bug in the middleware with a generic 500. The request ID middleware logs it."""
    return openai_error_response(500, "Internal server error", "internal_error")


def register_exception_handlers(app: FastAPI) -> None:
    """Make every error the app produces itself use the OpenAI error format."""
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    # httpx timeouts are a kind of TransportError; Starlette picks the handler
    # of the most specific class, so timeouts get 504 and the rest 502.
    app.add_exception_handler(httpx.TimeoutException, handle_upstream_timeout)
    app.add_exception_handler(httpx.TransportError, handle_upstream_unreachable)
    app.add_exception_handler(Exception, handle_unexpected_error)
