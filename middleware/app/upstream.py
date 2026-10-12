"""HTTP client for the upstream OpenAI API."""

import httpx

from app.config import Settings


def create_upstream_client(settings: Settings) -> httpx.AsyncClient:
    """Build the client shared by all requests.

    It always authenticates with the middleware's own API key; credentials sent
    by the caller are never forwarded.
    """
    return httpx.AsyncClient(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=httpx.Timeout(
            settings.upstream_read_timeout_seconds,
            connect=settings.upstream_connect_timeout_seconds,
        ),
    )
