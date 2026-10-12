"""ASGI middleware that gives every request an ID and logs its start and end."""

import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging import elapsed_ms, log_event, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Tag each HTTP request with an ID, reusing the caller's X-Request-ID if sent.

    Written as plain ASGI middleware because it must stay around until the last
    byte of a streamed response is sent: only then is request_completed logged,
    with the real total latency.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        context_token = request_id_var.set(request_id)
        started_at = time.perf_counter()
        # Reported if the app fails before it sends any response.
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        log_event(logger, "request_received", method=scope["method"], path=scope["path"])
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log_event(
                logger,
                "request_completed",
                status_code=status_code,
                latency_ms=elapsed_ms(started_at),
            )
            request_id_var.reset(context_token)
