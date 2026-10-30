import logging

import httpx


def _drop_below_warning(record: logging.LogRecord) -> bool:
    return record.levelno >= logging.WARNING


# httpx logs full request URLs at INFO, which would leak query parameters.
# A logger filter survives a later setLevel call, unlike the level alone.
for _name in ("httpx", "httpcore"):
    _logger = logging.getLogger(_name)
    _logger.setLevel(logging.WARNING)
    _logger.addFilter(_drop_below_warning)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=3.0, read=20.0, write=20.0, pool=3.0)


def build_http_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        transport=httpx.HTTPTransport(retries=0, trust_env=False),
    )
