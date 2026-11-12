"""Tests for authentication settings and ALB signature verification."""

import base64
import json
import socket
import threading
import time
from dataclasses import dataclass, fields

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from pydantic import ValidationError

from app.auth import (
    AlbTokenVerifier,
    AuthConfigurationError,
    AuthenticationError,
    AuthIdentity,
    AuthKeyUnavailableError,
    AuthSettings,
    fetch_alb_public_key,
    load_auth_settings,
)

SIGNER = (
    "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
    "loadbalancer/app/fewia/0123456789abcdef"
)
ISSUER = "https://identity.example.test/pool"
CLIENT = "fewia-client"
KID = "11111111-1111-4111-8111-111111111111"
OTHER_KID = "22222222-2222-4222-8222-222222222222"
NOW = 1800000000.0
AUTH_ENV = (
    "FEWIA_AUTH_MODE",
    "FEWIA_PUBLIC_ORIGIN",
    "FEWIA_ALB_SIGNER_ARN",
    "FEWIA_AUTH_ISSUER",
    "FEWIA_AUTH_CLIENT_ID",
    "FEWIA_AUTH_LOGOUT_URL",
    "FEWIA_DATABASE_MODE",
    "FEWIA_TRANSPORT_MODE",
)


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in AUTH_ENV:
        monkeypatch.delenv(name, raising=False)


def alb_values() -> dict[str, str]:
    return {
        "auth_mode": "alb",
        "public_origin": "https://fewia.example.test",
        "alb_signer_arn": SIGNER,
        "auth_issuer": ISSUER,
        "auth_client_id": CLIENT,
        "auth_logout_url": "https://identity.example.test/logout?client_id=fewia-client",
    }


@pytest.fixture
def settings() -> AuthSettings:
    return AuthSettings.model_validate(alb_values())


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def signed_token(
    key: ec.EllipticCurvePrivateKey,
    *,
    header_changes: dict[str, object] | None = None,
    claims: dict[str, object] | None = None,
    omit_header: str | None = None,
) -> bytes:
    header: dict[str, object] = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": KID,
        "signer": SIGNER,
        "client": CLIENT,
        "iss": ISSUER,
        "exp": NOW + 3600,
    }
    header.update(header_changes or {})
    if omit_header is not None:
        header.pop(omit_header)
    payload = {"sub": "subject-1", "email": "private@example.test"}
    segments = [
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).rstrip(b"=")
        for value in (header, payload if claims is None else claims)
    ]
    signing_input = b".".join(segments)
    r, s = utils.decode_dss_signature(
        key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    )
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")


@dataclass
class Clock:
    now: float = NOW

    def __call__(self) -> float:
        return self.now


class KeyService:
    def __init__(self, key: ec.EllipticCurvePrivateKey) -> None:
        self.keys = {KID: public_pem(key)}
        self.calls: list[tuple[str, str]] = []
        self.unavailable = False

    def __call__(self, region: str, kid: str) -> bytes:
        self.calls.append((region, kid))
        if self.unavailable:
            raise OSError("Key service failed.")
        return self.keys[kid]


def headers(token: bytes) -> list[tuple[bytes, bytes]]:
    return [(b"x-amzn-oidc-data", token)]


def test_local_demo_defaults_and_aws_guards() -> None:
    settings = load_auth_settings()
    assert settings.auth_mode == "local_demo"
    assert settings.public_origin == "http://127.0.0.1:5173"
    settings.require_runtime(aws_runtime=False, aws_database=False)
    for runtime, database in ((True, False), (False, True), (True, True)):
        with pytest.raises(AuthConfigurationError):
            load_auth_settings(aws_runtime=runtime, aws_database=database)


@pytest.mark.parametrize("name", ["FEWIA_DATABASE_MODE", "FEWIA_TRANSPORT_MODE"])
@pytest.mark.parametrize("value", ["", "AWS", " aws", "unknown"])
def test_runtime_modes_reject_unknown_values(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(AuthConfigurationError) as caught:
        load_auth_settings()
    assert str(caught.value) == "Authentication configuration is invalid."


@pytest.mark.parametrize("name", ["FEWIA_DATABASE_MODE", "FEWIA_TRANSPORT_MODE"])
def test_aws_runtime_modes_require_alb_from_environment(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "aws")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()
    for field, value in alb_values().items():
        monkeypatch.setenv(f"FEWIA_{field.upper()}", value)
    assert load_auth_settings().auth_mode == "alb"


@pytest.mark.parametrize(
    "origin", ["http://localhost:8010", "https://127.0.0.1", "http://[::1]:8010"]
)
def test_local_demo_accepts_loopback_only(origin: str) -> None:
    assert AuthSettings(public_origin=origin).public_origin == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://0.0.0.0:8010",
        "http://api:8010",
        "http://localhost.example.test",
        "https://fewia.example.test",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:",
        "http://[::1]evil",
        "http://localhost/path",
        "http://localhost?",
        "http://localhost#",
        "http://user@localhost",
        "http://localhost\\@example.test",
        "http://local%68ost",
        " http://localhost",
        "http://localhost\n",
        "ftp://localhost",
    ],
)
def test_local_demo_rejects_remote_or_malformed_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        AuthSettings(public_origin=origin)


def test_alb_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in alb_values().items():
        monkeypatch.setenv(f"FEWIA_{name.upper()}", value)
    settings = load_auth_settings(aws_runtime=True, aws_database=True)
    assert settings.auth_mode == "alb"
    assert settings.auth_issuer == ISSUER


@pytest.mark.parametrize("missing", list(alb_values()))
def test_alb_settings_reject_partial_configuration(missing: str) -> None:
    values = alb_values()
    values.pop(missing)
    with pytest.raises(ValidationError):
        AuthSettings.model_validate(values)


@pytest.mark.parametrize(
    "field", ["alb_signer_arn", "auth_issuer", "auth_client_id", "auth_logout_url"]
)
def test_local_demo_rejects_alb_settings(field: str) -> None:
    with pytest.raises(ValidationError):
        AuthSettings.model_validate({field: alb_values()[field]})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth_mode", "ALB"),
        ("auth_mode", " alb"),
        ("public_origin", "http://fewia.example.test"),
        ("alb_signer_arn", SIGNER.replace("/app/", "/net/")),
        ("alb_signer_arn", SIGNER.replace("us-east-1", "us-east-1.evil")),
        ("alb_signer_arn", SIGNER + "/../key"),
        ("auth_issuer", "http://identity.example.test"),
        ("auth_issuer", ISSUER + "?issuer=other"),
        ("auth_client_id", ""),
        ("auth_client_id", "client\nvalue"),
        ("auth_logout_url", "//identity.example.test/logout"),
        ("auth_logout_url", "https://user:password@example.test/logout"),
        ("auth_logout_url", "https://identity.example.test/logout#fragment"),
    ],
)
def test_alb_settings_reject_invalid_values(field: str, value: str) -> None:
    values = alb_values()
    values[field] = value
    with pytest.raises(ValidationError):
        AuthSettings.model_validate(values)


def test_settings_error_is_stable_and_hides_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_AUTH_CLIENT_ID", "private-value")
    with pytest.raises(AuthConfigurationError) as caught:
        load_auth_settings()
    assert str(caught.value) == "Authentication configuration is invalid."
    assert caught.value.__suppress_context__


def test_verifier_rejects_local_demo_settings() -> None:
    with pytest.raises(AuthConfigurationError):
        AlbTokenVerifier(AuthSettings())


def test_valid_signed_claim_exposes_only_identity(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    identity = verifier.verify_headers(headers(signed_token(signing_key)))
    assert identity == AuthIdentity(issuer=ISSUER, subject="subject-1")
    assert {field.name for field in fields(identity)} == {"issuer", "subject"}
    assert service.calls == [("us-east-1", KID)]


def test_forged_signature_is_rejected_without_refetch(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    forged = signed_token(ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(AuthenticationError, match=r"^Authentication is invalid\.$"):
        verifier.verify_headers(headers(forged))
    assert service.calls == [("us-east-1", KID)]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exp", NOW),
        ("exp", NOW - 1),
        ("exp", str(NOW + 3600)),
        ("exp", True),
        ("exp", float("nan")),
        ("exp", float("inf")),
        ("exp", 10**1000),
        ("signer", SIGNER.replace("0123456789abcdef", "ffffffffffffffff")),
        ("client", "another-client"),
        ("iss", "https://other.example.test/pool"),
        ("kid", "../../key"),
        ("kid", "https://attacker.example.test/key"),
        ("kid", 12),
        ("crit", ["unsupported"]),
    ],
)
def test_invalid_signed_header_is_rejected_before_key_fetch(
    settings: AuthSettings,
    signing_key: ec.EllipticCurvePrivateKey,
    field: str,
    value: object,
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    token = signed_token(signing_key, header_changes={field: value})
    with pytest.raises(AuthenticationError):
        verifier.verify_headers(headers(token))
    assert service.calls == []


@pytest.mark.parametrize("field", ["kid", "signer", "client", "iss", "exp"])
def test_missing_signed_header_field_is_rejected(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey, field: str
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    with pytest.raises(AuthenticationError):
        verifier.verify_headers(headers(signed_token(signing_key, omit_header=field)))
    assert not service.calls


def test_algorithm_allowlist_rejects_hs256(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    token = jwt.encode({"sub": "subject-1"}, b"a" * 64, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        verifier.verify_headers(headers(token.encode("ascii")))
    assert not service.calls


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": ""},
        {"sub": 123},
        {"sub": "subject\nvalue"},
        {"sub": "s" * 1025},
        {"sub": "subject-1", "iss": "https://other.example.test"},
        {"sub": "subject-1", "exp": NOW},
        {"sub": "subject-1", "nbf": NOW + 1},
        {"sub": "subject-1", "iat": NOW + 1},
    ],
)
def test_invalid_signed_payload_is_rejected(
    settings: AuthSettings,
    signing_key: ec.EllipticCurvePrivateKey,
    claims: dict[str, object],
) -> None:
    verifier = AlbTokenVerifier(
        settings, key_fetch=KeyService(signing_key), clock=Clock()
    )
    with pytest.raises(AuthenticationError):
        verifier.verify_headers(headers(signed_token(signing_key, claims=claims)))


def test_missing_duplicate_and_combined_headers_are_rejected(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    token = signed_token(signing_key)
    for inputs in (
        [],
        headers(token) + [(b"X-Amzn-Oidc-Data", token)],
        headers(token + b"," + token),
        headers(b" " + token),
        headers(b"\xff"),
        headers(b"bad.token.value"),
        headers(b"x" * 32769),
    ):
        with pytest.raises(AuthenticationError):
            verifier.verify_headers(inputs)
    assert not service.calls


def test_header_name_is_case_insensitive_and_other_headers_do_not_select_keys(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    identity = verifier.verify_headers(
        [
            (b"X-Amzn-Oidc-Data", signed_token(signing_key)),
            (b"x-forwarded-host", b"attacker.example.test"),
            (b"x-amzn-oidc-identity", b"forged-subject"),
        ]
    )
    assert identity.subject == "subject-1"
    assert service.calls == [("us-east-1", KID)]


def test_cache_hit_and_rotation_to_new_kid(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    token = signed_token(signing_key)
    verifier.verify_headers(headers(token))
    verifier.verify_headers(headers(token))
    rotated = ec.generate_private_key(ec.SECP256R1())
    service.keys[OTHER_KID] = public_pem(rotated)
    verifier.verify_headers(
        headers(signed_token(rotated, header_changes={"kid": OTHER_KID}))
    )
    assert service.calls == [("us-east-1", KID), ("us-east-1", OTHER_KID)]


def test_same_kid_refresh_is_bounded_and_accepts_rotated_key(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    clock = Clock()
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=clock)
    verifier.verify_headers(headers(signed_token(signing_key)))
    rotated = ec.generate_private_key(ec.SECP256R1())
    service.keys[KID] = public_pem(rotated)
    rotated_token = signed_token(rotated)
    with pytest.raises(AuthenticationError):
        verifier.verify_headers(headers(rotated_token))
    assert len(service.calls) == 1
    clock.now += 30
    verifier.verify_headers(headers(rotated_token))
    assert len(service.calls) == 2
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            verifier.verify_headers(headers(signed_token(signing_key)))
    assert len(service.calls) == 2


def test_unavailable_service_fails_closed_and_does_not_use_expired_cache(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    clock = Clock()
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=clock)
    token = signed_token(signing_key)
    service.unavailable = True
    with pytest.raises(AuthKeyUnavailableError) as caught:
        verifier.verify_headers(headers(token))
    assert str(caught.value) == "Authentication key service is unavailable."
    assert caught.value.__suppress_context__
    service.unavailable = False
    verifier.verify_headers(headers(token))
    service.unavailable = True
    clock.now += 300
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(headers(token))


def test_failed_rotation_refresh_discards_cached_key(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    clock = Clock()
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=clock)
    original = signed_token(signing_key)
    verifier.verify_headers(headers(original))
    clock.now += 30
    service.unavailable = True
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(
            headers(signed_token(ec.generate_private_key(ec.SECP256R1())))
        )
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(headers(original))


def test_key_service_fetch_budget_resets_after_window(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    clock = Clock()
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=clock)
    for number in range(8):
        kid = f"{number:08x}-3333-4333-8333-333333333333"
        with pytest.raises(AuthKeyUnavailableError):
            verifier.verify_headers(
                headers(signed_token(signing_key, header_changes={"kid": kid}))
            )
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(headers(signed_token(signing_key)))
    assert len(service.calls) == 8
    clock.now += 60
    verifier.verify_headers(headers(signed_token(signing_key)))
    assert len(service.calls) == 9


def test_cache_size_is_bounded(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    clock = Clock()
    service = KeyService(signing_key)
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=clock)
    for number in range(17):
        kid = f"{number:08x}-3333-4333-8333-333333333333"
        service.keys[kid] = public_pem(signing_key)
        verifier.verify_headers(
            headers(signed_token(signing_key, header_changes={"kid": kid}))
        )
        clock.now += 10
    first = "00000000-3333-4333-8333-333333333333"
    verifier.verify_headers(
        headers(signed_token(signing_key, header_changes={"kid": first}))
    )
    assert len(service.calls) == 18


@pytest.mark.parametrize("pem", [b"invalid", b"x" * 16385, b""])
def test_invalid_or_oversized_key_fails_closed(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey, pem: bytes
) -> None:
    service = KeyService(signing_key)
    service.keys[KID] = pem
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(headers(signed_token(signing_key)))


def test_wrong_curve_key_fails_closed(
    settings: AuthSettings, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    service = KeyService(signing_key)
    service.keys[KID] = public_pem(ec.generate_private_key(ec.SECP384R1()))
    verifier = AlbTokenVerifier(settings, key_fetch=service, clock=Clock())
    with pytest.raises(AuthKeyUnavailableError):
        verifier.verify_headers(headers(signed_token(signing_key)))


class FakeResponse:
    def __init__(self, status: int, body: bytes, length: str | None = None) -> None:
        self.status = status
        self.body = body
        self.length = length
        self.read_sizes: list[int] = []
        self.clock: Clock | None = None
        self.read_seconds = 0.0
        self.chunk_size = 16385
        self.closed = False
        self.blocked = False
        self.release = threading.Event()

    def getheader(self, name: str) -> str | None:
        assert name == "Content-Length"
        return self.length

    def read1(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if self.blocked:
            self.release.wait(timeout=1.0)
        if self.clock is not None:
            self.clock.now += self.read_seconds
        chunk = self.body[: min(size, self.chunk_size)]
        self.body = self.body[len(chunk) :]
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeSocket:
    def __init__(self, release: threading.Event) -> None:
        self.release = release
        self.timeouts: list[float] = []
        self.interrupted = False

    def settimeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)

    def shutdown(self, how: int) -> None:
        assert how == socket.SHUT_RDWR
        self.interrupted = True
        self.release.set()


class FakeConnection:
    def __init__(self, response: FakeResponse, clock: Clock | None = None) -> None:
        self.response = response
        self.clock = clock
        self.closed = False
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.costs: dict[str, float] = {}
        self.blocked_stage: str | None = None
        self.release = threading.Event()
        response.release = self.release
        self.finished = threading.Event()
        self.transport = FakeSocket(self.release)
        self.sock: FakeSocket | None = None
        self.timeout = 2.0

    def _advance(self, stage: str) -> None:
        if self.clock is not None:
            self.clock.now += self.costs.get(stage, 0.0)
        if stage == self.blocked_stage:
            self.release.wait(timeout=1.0)

    def connect(self) -> None:
        self._advance("connect")
        self.sock = self.transport

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, path, headers))
        self._advance("request")

    def getresponse(self) -> FakeResponse:
        self._advance("headers")
        return self.response

    def close(self) -> None:
        self.closed = True
        self.finished.set()


def install_fake_connection(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    clock: Clock | None = None,
) -> FakeConnection:
    connection = FakeConnection(response, clock)
    response.clock = clock

    def connect(host: str, *, timeout: float) -> FakeConnection:
        assert host == "public-keys.auth.elb.us-east-1.amazonaws.com"
        assert 0 < timeout <= 2.0
        return connection

    monkeypatch.setattr("app.auth.http.client.HTTPSConnection", connect)
    return connection


def test_key_transport_uses_fixed_origin_and_ignores_ambient_proxy(
    monkeypatch: pytest.MonkeyPatch, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.example.test")
    pem = public_pem(signing_key)
    response = FakeResponse(200, pem, str(len(pem)))
    connection = install_fake_connection(monkeypatch, response)
    assert fetch_alb_public_key("us-east-1", KID) == pem
    assert connection.requests == [
        ("GET", f"/{KID}", {"Accept": "application/x-pem-file"})
    ]
    assert response.read_sizes == [16385, 16385 - len(pem)]
    assert response.closed
    assert connection.closed


@pytest.mark.parametrize(
    ("status", "body", "length"),
    [
        (302, b"redirect", None),
        (503, b"unavailable", None),
        (200, b"x" * 16385, None),
        (200, b"", None),
        (200, b"key", "16385"),
        (200, b"key", "-1"),
        (200, b"key", "invalid"),
        (200, b"key", "4"),
        (200, b"key", "0"),
    ],
)
def test_key_transport_rejects_redirects_and_bad_responses(
    monkeypatch: pytest.MonkeyPatch, status: int, body: bytes, length: str | None
) -> None:
    connection = install_fake_connection(
        monkeypatch, FakeResponse(status, body, length)
    )
    with pytest.raises(AuthKeyUnavailableError):
        fetch_alb_public_key("us-east-1", KID)
    assert connection.closed
    assert len(connection.requests) == 1


@pytest.mark.parametrize(
    "costs",
    [
        {"connect": 2.0},
        {"connect": 1.0, "request": 1.0},
        {"connect": 0.5, "request": 0.5, "headers": 1.0},
        {"connect": 0.5, "request": 0.5, "headers": 0.5, "body": 0.5},
    ],
)
def test_key_transport_enforces_one_deadline_across_all_stages(
    monkeypatch: pytest.MonkeyPatch, costs: dict[str, float]
) -> None:
    clock = Clock(now=0.0)
    response = FakeResponse(200, b"key")
    connection = install_fake_connection(monkeypatch, response, clock)
    connection.costs = costs
    response.read_seconds = costs.get("body", 0.0)
    try:
        with pytest.raises(AuthKeyUnavailableError) as caught:
            fetch_alb_public_key("us-east-1", KID, clock=clock)
        assert str(caught.value) == "Authentication key service is unavailable."
    finally:
        assert connection.finished.wait(timeout=1.0)
    assert connection.closed


def test_key_transport_reduces_each_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(now=0.0)
    response = FakeResponse(200, b"key", "3")
    response.read_seconds = 0.25
    connection = install_fake_connection(monkeypatch, response, clock)
    connection.costs = {"connect": 0.25, "request": 0.25, "headers": 0.25}
    assert fetch_alb_public_key("us-east-1", KID, clock=clock) == b"key"
    assert connection.transport.timeouts == [1.75, 1.5, 1.25, 1.0]


def test_key_transport_rejects_body_that_trickles_past_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(now=0.0)
    response = FakeResponse(200, b"slow-key")
    response.read_seconds = 0.5
    response.chunk_size = 1
    connection = install_fake_connection(monkeypatch, response, clock)
    try:
        with pytest.raises(AuthKeyUnavailableError):
            fetch_alb_public_key("us-east-1", KID, clock=clock)
    finally:
        assert connection.finished.wait(timeout=1.0)
    assert len(response.read_sizes) == 4
    assert response.closed


def test_key_transport_reads_fragmented_body_within_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(now=0.0)
    response = FakeResponse(200, b"key", "3")
    response.chunk_size = 1
    response.read_seconds = 0.25
    install_fake_connection(monkeypatch, response, clock)
    assert fetch_alb_public_key("us-east-1", KID, clock=clock) == b"key"
    assert response.read_sizes == [16385, 16384, 16383, 16382]
    assert response.closed


@pytest.mark.parametrize("stage", ["connect", "request", "headers", "body"])
def test_key_transport_deadline_interrupts_a_blocked_operation(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    monkeypatch.setattr("app.auth._KEY_TIMEOUT_SECONDS", 0.05)
    connection = install_fake_connection(monkeypatch, FakeResponse(200, b"key"))
    connection.blocked_stage = stage
    connection.response.blocked = stage == "body"
    started = time.monotonic()
    try:
        with pytest.raises(AuthKeyUnavailableError):
            fetch_alb_public_key("us-east-1", KID)
        assert time.monotonic() - started < 0.5
        if stage != "connect":
            assert connection.transport.interrupted
    finally:
        connection.release.set()
        assert connection.finished.wait(timeout=1.0)
    assert connection.closed
    if stage == "connect":
        assert not connection.requests


def test_key_transport_rejects_fetch_when_workers_are_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = threading.BoundedSemaphore(0)
    monkeypatch.setattr("app.auth._KEY_FETCH_SLOTS", slots)
    connection = install_fake_connection(monkeypatch, FakeResponse(200, b"key"))
    with pytest.raises(AuthKeyUnavailableError):
        fetch_alb_public_key("us-east-1", KID)
    assert connection.sock is None
    assert not connection.requests
    assert connection.closed


@pytest.mark.parametrize(
    ("region", "kid"),
    [("us-east-1.evil.test", KID), ("us-east-1", "../key")],
)
def test_key_transport_rejects_invalid_destination_before_connection(
    monkeypatch: pytest.MonkeyPatch, region: str, kid: str
) -> None:
    connection = install_fake_connection(monkeypatch, FakeResponse(200, b"unused"))
    with pytest.raises(AuthKeyUnavailableError):
        fetch_alb_public_key(region, kid)
    assert not connection.requests
