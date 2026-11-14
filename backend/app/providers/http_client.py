import asyncio
import logging
import socket
import time
import zlib
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from threading import BoundedSemaphore

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

REQUEST_SECONDS = 45.0
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = httpx.Timeout(45.0, connect=5.0)
_SUPPORTED_HTTPX_VERSION = "0.28.1"
DNS_WORKERS = 4
_resolver_executor = ThreadPoolExecutor(
    max_workers=DNS_WORKERS, thread_name_prefix="provider-dns"
)
_resolver_slots = BoundedSemaphore(DNS_WORKERS)
_deadline: ContextVar[float | None] = ContextVar("provider_deadline", default=None)


class _ResolverEventLoop(asyncio.SelectorEventLoop):
    _transports: Mapping[int, asyncio.Transport]

    async def getaddrinfo(
        self,
        host: str | bytes | None,
        port: str | bytes | int | None,
        *,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
        ]
    ]:
        slots = _resolver_slots
        if not slots.acquire(blocking=False):
            raise httpx.ConnectError("Provider resolver is at capacity")
        try:
            future = _resolver_executor.submit(
                socket.getaddrinfo, host, port, family, type, proto, flags
            )
        except BaseException:
            slots.release()
            raise
        # A cancelled request MUST retain its slot until its resolver work finishes.
        future.add_done_callback(lambda done: slots.release())
        resolution = asyncio.wrap_future(future, loop=self)
        resolution.add_done_callback(
            lambda done: None if done.cancelled() else done.exception()
        )
        return await asyncio.shield(resolution)

    async def abort_transports(self) -> None:
        # The CPython selector registry includes sockets from incomplete TLS handshakes.
        for transport in tuple(self._transports.values()):
            transport.abort()
        # Selector transports close sockets in scheduled connection_lost callbacks.
        await asyncio.sleep(0)


def _check_deadline(deadline: float | None = None) -> None:
    if deadline is None:
        deadline = _deadline.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise httpx.ReadTimeout("Provider request deadline exceeded")


class ResponseTooLarge(httpx.RequestError):
    def __init__(self, request: httpx.Request) -> None:
        super().__init__("Provider response exceeds the byte limit", request=request)


class _Body:
    def __init__(self, response: httpx.Response) -> None:
        self._request = response.request
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        if encoding not in ("identity", "gzip", "deflate"):
            raise httpx.DecodingError("Unsupported provider content encoding")
        self._decoder = (
            None
            if encoding == "identity"
            else zlib.decompressobj(31 if encoding == "gzip" else 15)
        )
        self._content = bytearray()

    def feed(self, chunk: bytes) -> None:
        if self._decoder is not None:
            chunk = self._decoder.decompress(
                chunk, MAX_RESPONSE_BYTES - len(self._content) + 1
            )
        if len(chunk) > MAX_RESPONSE_BYTES - len(self._content):
            raise ResponseTooLarge(self._request)
        self._content.extend(chunk)
        if self._decoder is not None and self._decoder.unused_data:
            raise httpx.DecodingError("Unexpected compressed provider data")

    def finish(self) -> bytes:
        if self._decoder is not None and not self._decoder.eof:
            raise httpx.DecodingError("Incomplete compressed provider data")
        return bytes(self._content)


def _decoded_response(response: httpx.Response, body: bytes) -> httpx.Response:
    result = httpx.Response(
        response.status_code, content=body, request=response.request
    )
    result.headers = response.headers.copy()
    result.headers.pop("content-encoding", None)
    result.headers.pop("content-length", None)
    result.headers.pop("transfer-encoding", None)
    result.headers["Content-Length"] = str(len(body))
    return result


async def _send_async(request: httpx.Request, deadline: float) -> httpx.Response:
    try:
        _check_deadline(deadline)
        async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
            ) as client:
                _check_deadline(deadline)
                response = await client.send(
                    request, stream=True, auth=None, follow_redirects=False
                )
                try:
                    if response.is_stream_consumed:
                        _check_deadline(deadline)
                        return _decoded_response(response, _body(response))
                    body = _Body(response)
                    async for chunk in response.aiter_raw():
                        _check_deadline(deadline)
                        body.feed(chunk)
                    _check_deadline(deadline)
                    return _decoded_response(response, body.finish())
                finally:
                    await response.aclose()
    except TimeoutError:
        raise httpx.ReadTimeout("Provider request deadline exceeded") from None


def _run_request(request: httpx.Request, deadline: float) -> httpx.Response:
    loop = _ResolverEventLoop()
    try:
        return loop.run_until_complete(_send_async(request, deadline))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            try:
                loop.run_until_complete(loop.abort_transports())
            finally:
                loop.close()


class _DeadlineTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        deadline = _deadline.get()
        if deadline is None:
            deadline = time.monotonic() + REQUEST_SECONDS
        request.read()
        # A joined worker also permits calls from a thread with an active event loop.
        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="provider-request"
        ) as executor:
            return executor.submit(_run_request, request, deadline).result()


def _body(response: httpx.Response) -> bytes:
    if response.is_stream_consumed:
        content = response.content
        if len(content) > MAX_RESPONSE_BYTES:
            raise ResponseTooLarge(response.request)
        _check_deadline()
        return content
    body = _Body(response)
    for chunk in response.iter_raw():
        _check_deadline()
        body.feed(chunk)
    _check_deadline()
    return body.finish()


def _require_bounded_transports(client: httpx.Client) -> None:
    # HTTPX has no public API to inspect a client's transport or mounts.
    # These private fields require HTTPX 0.28.1. Other versions MUST fail closed.
    # Every route MUST use an owned transport or an exact fake transport type.
    if (
        httpx.__version__ != _SUPPORTED_HTTPX_VERSION
        or type(client) is not httpx.Client
    ):
        raise httpx.ConnectError("Unsupported provider HTTP client")
    transports = [client._transport, *client._mounts.values()]  # noqa: SLF001
    if any(
        transport is not None
        and type(transport) not in (_DeadlineTransport, httpx.MockTransport)
        for transport in transports
    ):
        raise httpx.ConnectError("Provider transport lacks a request deadline")


def request_bounded(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    data: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json: object = None,
    content: bytes | None = None,
) -> httpx.Response:
    token = _deadline.set(time.monotonic() + REQUEST_SECONDS)
    try:
        _require_bounded_transports(client)
        _check_deadline()
        request_headers = httpx.Headers(headers)
        request_headers.setdefault("Accept-Encoding", "gzip, deflate")
        with client.stream(
            method,
            url,
            headers=request_headers,
            auth=auth,
            data=data,
            params=params,
            json=json,
            content=content,
            follow_redirects=False,
            timeout=DEFAULT_TIMEOUT,
        ) as response:
            return _decoded_response(response, _body(response))
    except zlib.error:
        raise httpx.DecodingError("Invalid compressed provider data") from None
    finally:
        _deadline.reset(token)


def send_prepared_bounded(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str | bytes],
    body: bytes,
) -> httpx.Response:
    if httpx.__version__ != _SUPPORTED_HTTPX_VERSION:
        raise httpx.ConnectError("Unsupported provider HTTP client")
    raw_headers = [
        (
            name.encode("ascii"),
            value if isinstance(value, bytes) else value.encode("utf-8"),
        )
        for name, value in headers.items()
    ]
    request = httpx.Request(method, url, content=body)
    # Signed requests MUST bypass client defaults and automatic entity headers.
    prepared_headers = httpx.Headers(raw_headers)
    if "host" not in prepared_headers:
        prepared_headers["Host"] = request.headers["Host"]
    request.headers = prepared_headers
    if request.method != method or str(request.url) != url:
        raise httpx.RequestError("Unsupported prepared provider request")
    try:
        return _DeadlineTransport().handle_request(request)
    except zlib.error:
        raise httpx.DecodingError("Invalid compressed provider data") from None


def build_http_client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        transport=_DeadlineTransport(),
    )
