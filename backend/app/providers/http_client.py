import logging

import httpx


def _drop_below_warning(record: logging.LogRecord) -> bool:
    return record.levelno >= logging.WARNING


# httpx logs full request URLs at INFO, which would leak query parameters.
# The WARNING level on "httpx" and "httpcore" protects their child loggers.
# The filter covers only records logged directly on those two loggers, and it
# survives a later setLevel call on them.
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
