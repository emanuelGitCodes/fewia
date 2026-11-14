"""Validate authentication settings and ALB identities."""

import http.client
import math
import re
import socket
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal, Self
from urllib.parse import SplitResult, urlsplit

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SIGNER = re.compile(
    r"arn:aws:elasticloadbalancing:(?P<region>[a-z]{2}-[a-z]+-[1-9]):"
    r"[0-9]{12}:loadbalancer/app/"
    r"(?:[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9-]{0,30}[A-Za-z0-9])/"
    r"[0-9a-f]{16}"
)
_KID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]+={0,2}\.[A-Za-z0-9_-]+={0,2}\.[A-Za-z0-9_-]+={0,2}")
_MAX_TOKEN_BYTES = 32768
_MAX_KEY_BYTES = 16384
_KEY_TIMEOUT_SECONDS = 2.0
_CACHE_TTL_SECONDS = 300.0
_REFRESH_INTERVAL_SECONDS = 30.0
_FETCH_WINDOW_SECONDS = 60.0
_MAX_FETCHES_PER_WINDOW = 8
_MAX_CACHE_KEYS = 16
_KEY_FETCH_SLOTS = threading.BoundedSemaphore(_MAX_FETCHES_PER_WINDOW)


class AuthConfigurationError(Exception):
    def __init__(self) -> None:
        super().__init__("Authentication configuration is invalid.")


class AuthenticationError(Exception):
    def __init__(self) -> None:
        super().__init__("Authentication is invalid.")


class AuthKeyUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Authentication key service is unavailable.")


def _clean_text(value: str) -> bool:
    return bool(value) and not any(
        char.isspace() or unicodedata.category(char).startswith("C") for char in value
    )


def _url(value: str) -> SplitResult:
    if not _clean_text(value) or len(value) > 2048 or "\\" in value:
        raise ValueError("URL is invalid.")
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or "#" in value
        or parts.netloc.endswith(":")
        or (parts.port is not None and not 1 <= parts.port <= 65535)
    ):
        raise ValueError("URL is invalid.")
    host = parts.hostname
    authority = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        authority += f":{parts.port}"
    if parts.netloc.lower() != authority.lower():
        raise ValueError("URL is invalid.")
    try:
        ip_address(host)
    except ValueError:
        if len(host) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("URL is invalid.") from None
    return parts


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FEWIA_",
        env_file=None,
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    auth_mode: Literal["local_demo", "alb"] = "local_demo"
    database_mode: Literal["local", "aws"] = "local"
    transport_mode: Literal["local", "aws"] = "local"
    public_origin: str = "http://127.0.0.1:5173"
    alb_signer_arn: str | None = None
    auth_issuer: str | None = None
    auth_client_id: str | None = None
    auth_logout_url: str | None = None

    @field_validator("public_origin")
    @classmethod
    def _origin(cls, value: str) -> str:
        parts = _url(value)
        if parts.path not in ("", "/") or parts.query or "?" in value:
            raise ValueError("Public origin is invalid.")
        return value

    @field_validator("auth_issuer", "auth_logout_url")
    @classmethod
    def _https_url(cls, value: str | None) -> str | None:
        if value is not None:
            parts = _url(value)
            if parts.scheme != "https":
                raise ValueError("Authentication URL is invalid.")
        return value

    @field_validator("auth_issuer")
    @classmethod
    def _issuer(cls, value: str | None) -> str | None:
        if value is not None and "?" in value:
            raise ValueError("Authentication issuer is invalid.")
        return value

    @field_validator("alb_signer_arn")
    @classmethod
    def _signer(cls, value: str | None) -> str | None:
        if value is not None and _SIGNER.fullmatch(value) is None:
            raise ValueError("ALB signer is invalid.")
        return value

    @field_validator("auth_client_id")
    @classmethod
    def _client(cls, value: str | None) -> str | None:
        if value is not None and (not _clean_text(value) or len(value) > 256):
            raise ValueError("Authentication client is invalid.")
        return value

    @model_validator(mode="after")
    def _mode_contract(self) -> Self:
        alb_values = (
            self.alb_signer_arn,
            self.auth_issuer,
            self.auth_client_id,
            self.auth_logout_url,
        )
        origin = _url(self.public_origin)
        if (
            self.database_mode == "aws" or self.transport_mode == "aws"
        ) and self.auth_mode != "alb":
            raise ValueError("AWS settings require ALB authentication.")
        if self.auth_mode == "local_demo":
            if any(value is not None for value in alb_values) or not _loopback(
                origin.hostname or ""
            ):
                raise ValueError("Local demo settings are invalid.")
        elif any(value is None for value in alb_values) or origin.scheme != "https":
            raise ValueError("ALB settings are incomplete.")
        return self

    def require_runtime(self, *, aws_runtime: bool, aws_database: bool) -> None:
        """Reject local demo mode for an AWS runtime or database."""
        if (aws_runtime or aws_database) and self.auth_mode != "alb":
            raise AuthConfigurationError()


def load_auth_settings(
    *, aws_runtime: bool = False, aws_database: bool = False
) -> AuthSettings:
    try:
        settings = AuthSettings()
    except ValidationError:
        raise AuthConfigurationError() from None
    settings.require_runtime(aws_runtime=aws_runtime, aws_database=aws_database)
    return settings


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    issuer: str
    subject: str


def fetch_alb_public_key(
    region: str, kid: str, *, clock: Callable[[], float] = time.monotonic
) -> bytes:
    """Fetch a bounded key from the regional ALB key service."""
    if re.fullmatch(r"[a-z]{2}-[a-z]+-[1-9]", region) is None or not _KID.fullmatch(
        kid
    ):
        raise AuthKeyUnavailableError()
    deadline = clock() + _KEY_TIMEOUT_SECONDS
    cancelled = threading.Event()
    completed = threading.Event()
    slots = _KEY_FETCH_SLOTS
    sockets: list[socket.socket] = []
    result: list[bytes] = []

    def remaining() -> float:
        budget = deadline - clock()
        if cancelled.is_set() or budget <= 0:
            raise AuthKeyUnavailableError()
        return budget

    connection = http.client.HTTPSConnection(
        f"public-keys.auth.elb.{region}.amazonaws.com", timeout=remaining()
    )

    def fetch() -> None:
        response: http.client.HTTPResponse | None = None
        try:
            connection.timeout = remaining()
            connection.connect()
            transport = connection.sock
            if transport is None:
                raise AuthKeyUnavailableError()
            sockets.append(transport)
            transport.settimeout(remaining())
            connection.request(
                "GET", f"/{kid}", headers={"Accept": "application/x-pem-file"}
            )
            transport.settimeout(remaining())
            response = connection.getresponse()
            remaining()
            if response.status != 200:
                raise AuthKeyUnavailableError()
            length = response.getheader("Content-Length")
            if length is not None and (not length.isascii() or not length.isdigit()):
                raise AuthKeyUnavailableError()
            if length is not None and int(length) > _MAX_KEY_BYTES:
                raise AuthKeyUnavailableError()
            key = bytearray()
            while len(key) <= _MAX_KEY_BYTES:
                transport.settimeout(remaining())
                chunk = response.read1(_MAX_KEY_BYTES + 1 - len(key))
                remaining()
                if not chunk:
                    break
                key.extend(chunk)
            if (
                not key
                or len(key) > _MAX_KEY_BYTES
                or (length is not None and len(key) != int(length))
            ):
                raise AuthKeyUnavailableError()
            result.append(bytes(key))
        except (
            OSError,
            ValueError,
            http.client.HTTPException,
            AuthKeyUnavailableError,
        ):
            pass
        finally:
            with suppress(OSError):
                if response is not None:
                    response.close()
            with suppress(OSError):
                connection.close()
            slots.release()
            completed.set()

    if not slots.acquire(blocking=False):
        connection.close()
        raise AuthKeyUnavailableError()
    try:
        threading.Thread(target=fetch, daemon=True).start()
    except RuntimeError:
        slots.release()
        connection.close()
        raise AuthKeyUnavailableError() from None
    try:
        if not completed.wait(remaining()) or clock() >= deadline or not result:
            raise AuthKeyUnavailableError()
        return result[0]
    finally:
        cancelled.set()
        if not completed.is_set():
            for transport in sockets:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


@dataclass(frozen=True, slots=True)
class _CachedKey:
    key: ec.EllipticCurvePublicKey
    fetched_at: float


@dataclass(slots=True)
class _KeyFetch:
    completed: threading.Event
    deadline: float
    cached: _CachedKey | None = None


class AlbTokenVerifier:
    """Verify one ALB token without exposing its claims."""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        key_fetch: Callable[[str, str], bytes] = fetch_alb_public_key,
        clock: Callable[[], float] = time.time,
    ) -> None:
        signer = _SIGNER.fullmatch(settings.alb_signer_arn or "")
        if settings.auth_mode != "alb" or signer is None:
            raise AuthConfigurationError()
        self._settings = settings
        self._region = signer.group("region")
        self._fetch = key_fetch
        self._clock = clock
        self._cache: OrderedDict[str, _CachedKey] = OrderedDict()
        self._fetch_times: deque[float] = deque()
        self._refresh_times: OrderedDict[str, float] = OrderedDict()
        self._inflight: dict[str, _KeyFetch] = {}
        self._lock = threading.Lock()

    def verify_headers(self, headers: Sequence[tuple[bytes, bytes]]) -> AuthIdentity:
        values = [
            value for name, value in headers if name.lower() == b"x-amzn-oidc-data"
        ]
        if len(values) != 1 or not 0 < len(values[0]) <= _MAX_TOKEN_BYTES:
            raise AuthenticationError()
        try:
            token = values[0].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationError() from None
        if _TOKEN.fullmatch(token) is None:
            raise AuthenticationError()
        try:
            header = jwt.get_unverified_header(token)
        except (jwt.PyJWTError, ValueError, RecursionError):
            raise AuthenticationError() from None
        if (
            header.get("alg") != "ES256"
            or header.get("signer") != self._settings.alb_signer_arn
            or header.get("client") != self._settings.auth_client_id
            or header.get("iss") != self._settings.auth_issuer
            or header.get("crit")
        ):
            raise AuthenticationError()
        self._expiry(header.get("exp"))
        kid = header.get("kid")
        if not isinstance(kid, str) or not _KID.fullmatch(kid):
            raise AuthenticationError()
        cached = self._key(kid)
        try:
            claims = self._decode(token, cached.key)
        except jwt.InvalidSignatureError:
            refreshed = self._key(kid, refresh=True)
            try:
                claims = self._decode(token, refreshed.key)
            except (jwt.PyJWTError, ValueError, TypeError, RecursionError):
                raise AuthenticationError() from None
        except (jwt.PyJWTError, ValueError, TypeError, RecursionError):
            raise AuthenticationError() from None
        self._expiry(header.get("exp"))
        if "exp" in claims:
            self._expiry(claims["exp"])
        if "iss" in claims and claims["iss"] != self._settings.auth_issuer:
            raise AuthenticationError()
        for field in ("nbf", "iat"):
            if field in claims and self._numeric_date(claims[field]) > self._clock():
                raise AuthenticationError()
        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not _clean_text(subject)
            or len(subject) > 1024
        ):
            raise AuthenticationError()
        return AuthIdentity(issuer=self._settings.auth_issuer or "", subject=subject)

    @staticmethod
    def _decode(token: str, key: ec.EllipticCurvePublicKey) -> dict[str, object]:
        claims: dict[str, object] = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            options={
                "require": ["sub"],
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
                "verify_iss": False,
                "verify_aud": False,
                "verify_sub": False,
                "verify_jti": False,
            },
        )
        return claims

    @staticmethod
    def _numeric_date(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AuthenticationError()
        try:
            timestamp = float(value)
        except OverflowError:
            raise AuthenticationError() from None
        if not math.isfinite(timestamp):
            raise AuthenticationError()
        return timestamp

    def _expiry(self, value: object) -> None:
        if self._numeric_date(value) <= self._clock():
            raise AuthenticationError()

    def _key(self, kid: str, *, refresh: bool = False) -> _CachedKey:
        with self._lock:
            now = self._clock()
            cached = self._cache.get(kid)
            fresh = cached is not None and now - cached.fetched_at < _CACHE_TTL_SECONDS
            if cached is not None and fresh and not refresh:
                self._cache.move_to_end(kid)
                return cached
            pending = self._inflight.get(kid)
            owner = pending is None
            if pending is None:
                if fresh and cached is not None:
                    last_refresh = self._refresh_times.get(kid, cached.fetched_at)
                    if now - last_refresh < _REFRESH_INTERVAL_SECONDS:
                        raise AuthenticationError()
                while self._fetch_times and (
                    now - self._fetch_times[0] >= _FETCH_WINDOW_SECONDS
                ):
                    self._fetch_times.popleft()
                if (
                    len(self._fetch_times) >= _MAX_FETCHES_PER_WINDOW
                    or len(self._inflight) >= _MAX_FETCHES_PER_WINDOW
                ):
                    raise AuthKeyUnavailableError()
                self._fetch_times.append(now)
                self._refresh_times[kid] = now
                self._refresh_times.move_to_end(kid)
                while len(self._refresh_times) > _MAX_CACHE_KEYS:
                    self._refresh_times.popitem(last=False)
                pending = _KeyFetch(
                    completed=threading.Event(),
                    deadline=time.monotonic() + _KEY_TIMEOUT_SECONDS,
                )
                self._inflight[kid] = pending
        if not owner:
            remaining = pending.deadline - time.monotonic()
            if (
                remaining <= 0
                or not pending.completed.wait(remaining)
                or time.monotonic() >= pending.deadline
                or pending.cached is None
            ):
                raise AuthKeyUnavailableError()
            return pending.cached
        try:
            pem = self._fetch(self._region, kid)
            if not isinstance(pem, bytes) or not 0 < len(pem) <= _MAX_KEY_BYTES:
                raise ValueError
            public_material = load_pem_public_key(pem)
            if not isinstance(
                public_material, ec.EllipticCurvePublicKey
            ) or not isinstance(public_material.curve, ec.SECP256R1):
                raise ValueError
            if time.monotonic() >= pending.deadline:
                raise AuthKeyUnavailableError()
            cached = _CachedKey(key=public_material, fetched_at=self._clock())
            with self._lock:
                self._cache[kid] = cached
                self._cache.move_to_end(kid)
                while len(self._cache) > _MAX_CACHE_KEYS:
                    self._cache.popitem(last=False)
                pending.cached = cached
            return cached
        except (
            OSError,
            ValueError,
            KeyError,
            http.client.HTTPException,
            UnsupportedAlgorithm,
            AuthKeyUnavailableError,
        ):
            raise AuthKeyUnavailableError() from None
        finally:
            with self._lock:
                if pending.cached is None:
                    self._cache.pop(kid, None)
                self._inflight.pop(kid, None)
                pending.completed.set()
