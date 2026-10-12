import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.logging import JsonFormatter
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_app_logging() -> Iterator[None]:
    """Drop the stdout handler that create_app installs, so it never outlives its test."""
    yield
    logging.getLogger("app").handlers = []


class JsonListHandler(logging.Handler):
    """Collect every log record as the parsed JSON line the app would print."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        super().__init__()
        self.entries = entries
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.entries.append(json.loads(self.format(record)))


@pytest.fixture
def log_entries() -> Iterator[list[dict[str, Any]]]:
    """The app's log lines, as dicts, in the order they were written.

    Lines are formatted when they are logged, so each one carries the request
    ID that was active at that moment.
    """
    entries: list[dict[str, Any]] = []
    handler = JsonListHandler(entries)
    logging.getLogger().addHandler(handler)
    yield entries
    logging.getLogger().removeHandler(handler)


@pytest.fixture
def system_prompt() -> str:
    return "TEST SYSTEM PROMPT"


@pytest.fixture
def settings(tmp_path: Path, system_prompt: str) -> Settings:
    prompt_file = tmp_path / "system_prompt.md"
    prompt_file.write_text(system_prompt, encoding="utf-8")
    return Settings(
        openai_api_key=SecretStr("sk-test"),
        openai_base_url="http://upstream.test/v1",
        system_prompt_path=prompt_file,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def upstream(settings: Settings) -> Iterator[respx.MockRouter]:
    """Mocked OpenAI API. Routes are declared relative to the upstream base URL."""
    with respx.mock(base_url=settings.openai_base_url) as router:
        yield router
