import asyncio
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.upstream import create_upstream_client


def test_upstream_client_uses_configured_base_url_key_and_timeouts(settings: Settings) -> None:
    settings.upstream_connect_timeout_seconds = 3.0
    settings.upstream_read_timeout_seconds = 45.0

    client = create_upstream_client(settings)

    assert client.base_url == "http://upstream.test/v1/"
    assert client.headers["Authorization"] == "Bearer sk-test"
    assert client.timeout.connect == 3.0
    assert client.timeout.read == 45.0
    asyncio.run(client.aclose())


def test_upstream_client_transport_gets_configured_connect_retries(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.upstream_connect_retries = 5
    transport_options: dict[str, Any] = {}
    real_transport = httpx.AsyncHTTPTransport

    def recording_transport(**options: Any) -> httpx.AsyncHTTPTransport:
        transport_options.update(options)
        return real_transport(**options)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", recording_transport)

    client = create_upstream_client(settings)

    assert transport_options == {"retries": 5}
    asyncio.run(client.aclose())
