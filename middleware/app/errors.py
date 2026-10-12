"""Error responses in OpenAI's JSON error format."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Answer a bug in the middleware with a generic 500. The request ID middleware logs it."""
    return openai_error_response(500, "Internal server error", "internal_error")


def register_exception_handlers(app: FastAPI) -> None:
    """Make every error the app produces itself use the OpenAI error format."""
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
