import logging

import httpx

# httpx logs full request URLs at INFO, which would leak query parameters.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=3.0, read=20.0, write=20.0, pool=3.0)


def build_http_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        transport=httpx.HTTPTransport(retries=0, trust_env=False),
    )
