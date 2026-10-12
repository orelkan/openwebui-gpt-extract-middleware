from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.prompt import PromptLoadError


def test_create_app_stores_given_settings(settings: Settings) -> None:
    app = create_app(settings)

    assert app.state.settings is settings


def test_startup_loads_system_prompt(settings: Settings, system_prompt: str) -> None:
    app = create_app(settings)

    with TestClient(app):
        assert app.state.system_prompt == system_prompt


def test_startup_fails_when_prompt_file_is_missing(settings: Settings, tmp_path: Path) -> None:
    settings.system_prompt_path = tmp_path / "missing.md"
    app = create_app(settings)

    with pytest.raises(PromptLoadError), TestClient(app):
        pass


def test_shutdown_closes_upstream_client(settings: Settings) -> None:
    app = create_app(settings)

    with TestClient(app):
        upstream_client = app.state.upstream_client
        assert not upstream_client.is_closed

    assert upstream_client.is_closed
