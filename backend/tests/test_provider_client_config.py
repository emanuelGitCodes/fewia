from unittest.mock import patch

import httpx
import httpx._transports.default as httpx_transport

from app.providers.aws_config import aws_client_config
from app.providers.http_client import DEFAULT_TIMEOUT, build_http_client


def test_build_http_client_policy() -> None:
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
        assert client.timeout.connect == 3.0
        assert client.timeout.read == 20.0
        assert client.timeout.write == 20.0
        assert client.timeout.pool == 3.0
        assert client.follow_redirects is False
        assert client.trust_env is False
        assert isinstance(client._transport, httpx.HTTPTransport)
        assert client._transport._pool._retries == 0
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
