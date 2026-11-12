from unittest.mock import patch

import httpx
import httpx._transports.default as httpx_transport
import pytest

from app.providers import http_client
from app.providers.aws_config import aws_client_config
from app.providers.http_client import (
    DEFAULT_TIMEOUT,
    REQUEST_SECONDS,
    build_http_client,
    request_bounded,
)


def test_build_http_client_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handle(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        assert transport._pool._retries == 0
        assert request.extensions["timeout"] == {
            "connect": 5.0,
            "read": 45.0,
            "write": 45.0,
            "pool": 45.0,
        }
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setenv("HTTPS_PROXY", "http://ambient-proxy.invalid")
    with (
        patch.object(
            httpx_transport,
            "create_ssl_context",
            wraps=httpx_transport.create_ssl_context,
        ) as create_ssl_context,
        build_http_client("https://example.com") as client,
    ):
        assert str(client.base_url).rstrip("/") == "https://example.com"
        assert client.timeout == DEFAULT_TIMEOUT
        assert client.timeout.connect == 5.0
        assert client.timeout.read == 45.0
        assert client.timeout.write == 45.0
        assert client.timeout.pool == 45.0
        assert REQUEST_SECONDS == 45.0
        assert client.follow_redirects is False
        assert client.trust_env is False
        assert type(client._transport) is http_client._DeadlineTransport
        assert client._mounts == {}
        create_ssl_context.assert_not_called()
        assert request_bounded(client, "GET", "/").content == b"ok"
        create_ssl_context.assert_called_once()
        assert create_ssl_context.call_args.kwargs["trust_env"] is False


def test_aws_client_config_local_policy() -> None:
    config = aws_client_config(5, local=True)
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries == {"total_max_attempts": 1}
    assert config.proxies == {}


def test_aws_client_config_remote_policy() -> None:
    config = aws_client_config(40, local=False)
    assert config.connect_timeout == 3
    assert config.read_timeout == 40
    assert config.retries == {"total_max_attempts": 1}
    assert config.proxies is None
