"""Structured JSON logging with a per-request ID."""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set by the request ID middleware. A context variable follows the request
# through every await, so log calls do not need the ID passed to them.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Format each log record as one JSON object on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_var.get(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Send the app's and uvicorn's logs to stdout as JSON.

    The root logger is left alone, so other libraries keep their defaults.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    for name in ("app", "uvicorn"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(level)
    # Our request_completed event carries the same information as uvicorn's
    # access log, in JSON and with the request ID.
    logging.getLogger("uvicorn.access").disabled = True


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Log a named event with structured fields."""
    logger.log(level, event, exc_info=exc_info, extra={"fields": fields})


def elapsed_ms(started_at: float) -> float:
    """Milliseconds passed since a time.perf_counter() reading."""
    return round((time.perf_counter() - started_at) * 1000, 1)
