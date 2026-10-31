"""Instacart link checks and error types.

The module holds only the link checks and the error types that the frozen
evaluation and the handoff services use. It makes no Instacart API call.
"""

import unicodedata
from urllib.parse import SplitResult, urlsplit

_ALLOWED_HOSTS = frozenset(
    {
        "www.instacart.com",
        "instacart.com",
        "www.instacart.ca",
        "instacart.ca",
    }
)
_INVALID_LINK = "Instacart link URL is invalid"
_ENCODED_ASCII_CONTROLS = frozenset(f"%{code:02x}" for code in (*range(0x20), 0x7F))


class InstacartUncertain(Exception):
    def __init__(self) -> None:
        super().__init__("Instacart products_link result is uncertain")


class InstacartRejected(Exception):
    def __init__(self) -> None:
        super().__init__("Instacart rejected the products_link request")


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
