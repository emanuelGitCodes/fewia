"""Instacart development products_link adapter."""

import json
import unicodedata
from urllib.parse import SplitResult, urlsplit

import httpx

from app.providers.http_client import DEFAULT_TIMEOUT, build_http_client

PRODUCTS_LINK_URL = "https://connect.dev.instacart.tools/idp/v1/products/products_link"
_DEV_BASE_URL = "https://connect.dev.instacart.tools"
_ALLOWED_HOSTS = frozenset(
    {
        "www.instacart.com",
        "instacart.com",
        "www.instacart.ca",
        "instacart.ca",
    }
)
_REJECTED_STATUSES = frozenset({400, 401, 403, 422})
_INVALID_LINK = "Instacart link URL is invalid"
_ENCODED_ASCII_CONTROLS = frozenset(f"%{code:02x}" for code in (*range(0x20), 0x7F))


class InstacartUncertain(Exception):
    def __init__(self) -> None:
        super().__init__("Instacart products_link result is uncertain")


class InstacartRejected(Exception):
    def __init__(self) -> None:
        super().__init__("Instacart rejected the products_link request")


def _require_api_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("api_key MUST be a nonblank string")
    if any(unicodedata.category(ch) == "Cc" or ch == "\x7f" for ch in value):
        raise ValueError("api_key MUST NOT contain control characters")
    return value


def _parse_url(value: str) -> SplitResult | None:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        _ = parsed.hostname
        _ = parsed.username
        _ = parsed.password
    except ValueError:
        return None
    return parsed


def _url_is_allowed(value: str, parsed: SplitResult) -> bool:
    if not value or len(value) > 2048:
        return False
    if any(
        ch.isspace() or ch == "\\" or unicodedata.category(ch) == "Cc" for ch in value
    ):
        return False
    lowered = value.lower()
    if "#" in value or any(marker in lowered for marker in _ENCODED_ASCII_CONTROLS):
        return False
    host = parsed.hostname
    if host is None or parsed.scheme.lower() != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if "@" in parsed.netloc:
        return False
    if parsed.port not in (None, 443):
        return False
    if parsed.fragment:
        return False
    return host.lower() in _ALLOWED_HOSTS


def validate_link_url(value: object) -> str:
    parsed: SplitResult | None = None
    if isinstance(value, str):
        parsed = _parse_url(value)
    if not isinstance(value, str) or parsed is None:
        raise ValueError(_INVALID_LINK)
    if not _url_is_allowed(value, parsed):
        raise ValueError(_INVALID_LINK)
    return value


def _parse_create_link_response(response: httpx.Response) -> str:
    status = response.status_code
    if status in _REJECTED_STATUSES:
        raise InstacartRejected()
    if status != 200:
        raise InstacartUncertain()
    body: object | None = None
    try:
        body = json.loads(response.content)
    except Exception:  # noqa: BLE001
        pass
    url: str | None = None
    if isinstance(body, dict):
        try:
            url = validate_link_url(body.get("products_link_url"))
        except ValueError:
            url = None
    if url is None:
        raise InstacartUncertain()
    return url


class InstacartDevelopmentProvider:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = _require_api_key(api_key)
        if client is None:
            self._client = build_http_client(_DEV_BASE_URL)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def create_link(self, payload: dict[str, object]) -> str:
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                PRODUCTS_LINK_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
                follow_redirects=False,
                timeout=DEFAULT_TIMEOUT,
            )
        except (httpx.RequestError, httpx.InvalidURL, TypeError, ValueError):
            pass
        if response is None:
            raise InstacartUncertain()
        try:
            return _parse_create_link_response(response)
        except (InstacartRejected, InstacartUncertain):
            raise
        except Exception:  # noqa: BLE001
            raise InstacartUncertain() from None
