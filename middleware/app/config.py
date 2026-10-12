"""Application configuration, read from environment variables."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings

# Resolved from this file's location so it works from any working directory.
DEFAULT_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"


class Settings(BaseSettings):
    """Middleware settings. Field names map to upper-case environment variables."""

    # SecretStr keeps the key out of reprs, so it cannot leak through logs or tracebacks.
    openai_api_key: SecretStr
    openai_base_url: str = "https://api.openai.com/v1"
    system_prompt_path: Path = DEFAULT_SYSTEM_PROMPT_PATH
