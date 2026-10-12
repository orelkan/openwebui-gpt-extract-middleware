"""Error responses in OpenAI's JSON error format."""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging import log_event


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


async def handle_upstream_failure(request: Request, error: Exception) -> JSONResponse:
    """Answer a request that failed before upstream gave any response.

    504 when upstream did not connect or respond within the configured
    timeouts, 502 for every other failure to reach it.
    """
    if isinstance(error, httpx.TimeoutException):
        status_code = 504
        message = "The upstream API did not respond in time"
        error_type = "upstream_timeout"
    else:
        status_code = 502
        message = "Could not reach the upstream API"
        error_type = "upstream_unreachable"
    log_event(
        "upstream_error",
        level=logging.ERROR,
        error_type=type(error).__name__,
        status_code=status_code,
        mid_stream=False,
    )
    return openai_error_response(status_code, message, error_type)


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Answer a bug in the middleware with a generic 500. The request ID middleware logs it."""
    return openai_error_response(500, "Internal server error", "internal_error")


def register_exception_handlers(app: FastAPI) -> None:
    """Make every error the app produces itself use the OpenAI error format."""
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    # TransportError covers timeouts, refused connections and broken connections.
    app.add_exception_handler(httpx.TransportError, handle_upstream_failure)
    app.add_exception_handler(Exception, handle_unexpected_error)
