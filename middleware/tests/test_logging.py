import json
import logging

import pytest

from app.logging import JsonFormatter, configure_logging, log_event, request_id_var


def make_record(**extra: object) -> logging.LogRecord:
    return logging.makeLogRecord(
        {"name": "app.test", "levelname": "INFO", "levelno": logging.INFO, "msg": "it_happened"}
        | extra
    )


def test_json_formatter_writes_one_json_object_per_line() -> None:
    record = make_record()

    line = JsonFormatter().format(record)

    assert "\n" not in line
    entry = json.loads(line)
    assert entry["event"] == "it_happened"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["timestamp"].endswith("+00:00")
    assert entry["request_id"] is None


def test_json_formatter_includes_event_fields() -> None:
    record = make_record(fields={"status_code": 200, "latency_ms": 12.5})

    entry = json.loads(JsonFormatter().format(record))

    assert entry["status_code"] == 200
    assert entry["latency_ms"] == 12.5


def test_json_formatter_includes_request_id_from_context() -> None:
    token = request_id_var.set("req-123")

    try:
        entry = json.loads(JsonFormatter().format(make_record()))
    finally:
        request_id_var.reset(token)

    assert entry["request_id"] == "req-123"


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError as error:
        record = make_record(exc_info=(type(error), error, error.__traceback__))

    entry = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in entry["exception"]


def test_configure_logging_writes_app_events_to_stdout_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")

    log_event(logging.getLogger("app.test"), "something_happened", count=3)

    entry = json.loads(capsys.readouterr().out)
    assert entry["event"] == "something_happened"
    assert entry["count"] == 3


def test_configure_logging_drops_events_below_the_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("WARNING")

    log_event(logging.getLogger("app.test"), "something_happened")

    assert capsys.readouterr().out == ""
