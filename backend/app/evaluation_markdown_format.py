"""Format allowlisted scalar report fields.

Callers MUST exclude answers, errors, credentials, and other secret fields.
These functions do not detect or redact arbitrary secrets.
"""

from __future__ import annotations

import math
import re
import string
import unicodedata
from urllib.parse import quote, urlsplit, urlunsplit

_CELL_ERROR = "Invalid Markdown cell."
_TABLE_ERROR = "Invalid Markdown table."
_LINK_ERROR = "Invalid source link."
_LIMIT = 256
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def cell(value: object) -> str:
    """Return one bounded, escaped plain table cell."""
    if value is None:
        return "Unknown"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        try:
            rendered = str(value)
        except ValueError:
            raise ValueError(_CELL_ERROR) from None
        if len(rendered) > _LIMIT:
            raise ValueError(_CELL_ERROR)
        return rendered
    if type(value) is float and math.isfinite(value):
        return str(value)
    if type(value) is not str:
        raise ValueError(_CELL_ERROR)
    text = re.sub(r"[\r\n\t\u2028\u2029]+", " ", value)
    tokens = [
        "\\" + char if char in string.punctuation else char
        for char in text
        if unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
    ]
    escaped = "".join(tokens)
    if len(escaped) <= _LIMIT:
        return escaped
    prefix: list[str] = []
    length = 0
    for token in tokens:
        if length + len(token) > _LIMIT - 1:
            break
        prefix.append(token)
        length += len(token)
    return "".join(prefix) + "…"


def table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    """Return a Markdown table without changing the inputs."""
    if (
        type(headers) is not tuple
        or not headers
        or any(type(header) is not str for header in headers)
        or type(rows) is not list
        or any(type(row) is not tuple or len(row) != len(headers) for row in rows)
    ):
        raise ValueError(_TABLE_ERROR)
    lines = ["| " + " | ".join(cell(header) for header in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def source_link(label: str, url: str) -> str:
    """Return an escaped HTTPS link without fetching the source.

    This function does not certify that a source is official or current.
    """
    if (
        type(label) is not str
        or type(url) is not str
        or not url.lower().startswith("https://")
        or "\\" in url
        or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in url)
        or re.search(r"%(?![0-9a-fA-F]{2})", url) is not None
    ):
        raise ValueError(_LINK_ERROR)
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise ValueError(_LINK_ERROR) from None
    if (
        parts.scheme != "https"
        or host is None
        or parts.username is not None
        or parts.password is not None
        or re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", parts.netloc) is None
        or len(host) > 253
        or any(
            _DNS_LABEL.fullmatch(part) is None
            for part in host.removesuffix(".").split(".")
        )
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError(_LINK_ERROR)
    authority = host if port is None else f"{host}:{port}"
    safe = "/?:@&=+$,;-%"
    target = urlunsplit(
        (
            "https",
            authority,
            quote(parts.path, safe=safe),
            quote(parts.query, safe=safe),
            quote(parts.fragment, safe=safe),
        )
    )
    return f"[{cell(label)}]({target})"
