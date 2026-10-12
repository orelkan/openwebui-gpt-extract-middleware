"""Application configuration, read from environment variables."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Middleware settings. Field names map to upper-case environment variables."""

    # SecretStr keeps the key out of reprs, so it cannot leak through logs or tracebacks.
    openai_api_key: SecretStr
    openai_base_url: str = "https://api.openai.com/v1"
