from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


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
