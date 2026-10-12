from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, load_settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_settings_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://upstream.test/v1")

    settings = load_settings()

    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.openai_base_url == "http://upstream.test/v1"


def test_settings_uses_default_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = load_settings()

    assert settings.openai_base_url == "https://api.openai.com/v1"


def test_settings_fails_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        load_settings()


def test_settings_repr_hides_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings()

    assert "sk-test" not in repr(settings)


def test_settings_rejects_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        load_settings()


def test_settings_rejects_negative_connect_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("UPSTREAM_CONNECT_RETRIES", "-1")

    with pytest.raises(ValidationError):
        load_settings()


def test_every_setting_is_documented_in_env_example() -> None:
    documented = ENV_EXAMPLE.read_text(encoding="utf-8")

    for field_name in Settings.model_fields:
        assert f"{field_name.upper()}=" in documented
