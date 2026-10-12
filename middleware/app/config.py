"""Application configuration, read from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import NonNegativeInt, SecretStr
from pydantic_settings import BaseSettings

# Resolved from this file's location so it works from any working directory.
DEFAULT_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"


class Settings(BaseSettings):
    """Middleware settings. Field names map to upper-case environment variables."""

    # SecretStr keeps the key out of reprs, so it cannot leak through logs or tracebacks.
    openai_api_key: SecretStr
    openai_base_url: str = "https://api.openai.com/v1"
    system_prompt_path: Path = DEFAULT_SYSTEM_PROMPT_PATH
    upstream_connect_timeout_seconds: float = 10.0
    # Time allowed between two chunks from upstream, not for the whole response.
    upstream_read_timeout_seconds: float = 120.0
    # Extra attempts when a connection to upstream cannot be opened.
    upstream_connect_retries: NonNegativeInt = 2
    # How long /ready waits for upstream before answering "not ready".
    readiness_timeout_seconds: float = 5.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_settings() -> Settings:
    """Build the settings from environment variables.

    Fails with a validation error when a required variable is missing.
    """
    # pydantic-settings fills the required fields from the environment when the
    # class is called with no arguments. mypy knows this through the pydantic
    # plugin; Pyright (VS Code's Pylance) does not, so it is told here, once.
    return Settings()  # pyright: ignore[reportCallIssue]
