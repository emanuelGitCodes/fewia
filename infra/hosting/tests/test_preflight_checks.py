import builtins
import os
import socket
import subprocess
import traceback
from collections import UserDict
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Never, cast

import pytest
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from deployment_config import DeploymentConfig, RuntimeConfig
from preflight_checks import (
    PreflightError,
    check_caller,
    check_certificate,
    check_image,
)

_ACCOUNT = "111122223333"
_ARN = (
    f"arn:aws:acm:us-east-1:{_ACCOUNT}:certificate/12345678-1234-abcd-1234-123456789abc"
)
_DIGEST = "sha256:" + "a" * 64
_REPOSITORY = "fewia/backend"
_NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
_MARKER = "SYNTHETIC_PRIVATE_INPUT"
_ERROR = "preflight metadata is invalid"


class _DictSubclass(dict[str, object]):
    pass


class _StringSubclass(str):
    pass


class _ListSubclass(list[object]):
    pass


class _Unreadable:
    def __str__(self) -> str:
        raise AssertionError("extra metadata was read")

    def __repr__(self) -> str:
        raise AssertionError("extra metadata was read")


def _config(hostname: str = "app.example.test") -> DeploymentConfig:
    return DeploymentConfig(
        _ACCOUNT,
        "active",
        RuntimeConfig(hostname, "fewia-dev", _ARN, _DIGEST, _DIGEST),
    )


def _certificate() -> dict[str, object]:
    return {
        "CertificateArn": _ARN,
        "Status": "ISSUED",
        "Type": "AMAZON_ISSUED",
        "SubjectAlternativeNames": ["app.example.test"],
        "NotBefore": "2026-10-03T11:00:00Z",
        "NotAfter": "2026-10-03T13:00:00Z",
    }


def _image() -> dict[str, object]:
    return {
        "imageDigest": _DIGEST,
        "repositoryName": _REPOSITORY,
        "registryId": _ACCOUNT,
    }


def _check_image(response: object) -> None:
    check_image(_config(), response, repository_name=_REPOSITORY, digest=_DIGEST)


def _assert_invalid(call: Callable[[], None]) -> None:
    with pytest.raises(PreflightError) as error:
        call()
    assert type(error.value) is PreflightError
    assert isinstance(error.value, RuntimeError)
    assert error.value.args == (_ERROR,)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    assert _MARKER not in str(error.value)
    assert _MARKER not in repr(error.value)
    assert _MARKER not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
def test_caller_and_image_accept_exact_values_without_runtime_dependency(
    phase: Literal["foundation", "bootstrap", "active"],
) -> None:
    config = DeploymentConfig(_ACCOUNT, phase, None)
    expected_config = deepcopy(config)
    check_caller(config, {"Account": _ACCOUNT, "extra": _Unreadable()})
    check_image(
        config,
        {"imageDetails": [_image()], "extra": _Unreadable()},
        repository_name=_REPOSITORY,
        digest=_DIGEST,
    )
    assert config == expected_config
    assert config.runtime is None


@pytest.mark.parametrize(
    "response",
    [
        None,
        True,
        123,
        1.5,
        "{}",
        b"{}",
        [],
        (),
        _DictSubclass(),
        UserDict(),
        {1: _MARKER},
        {_StringSubclass("extra"): _MARKER},
    ],
)
def test_each_check_rejects_nonexact_response_objects(response: object) -> None:
    _assert_invalid(lambda: check_caller(_config(), response))
    _assert_invalid(lambda: check_certificate(_config(), response, now=_NOW))
    _assert_invalid(lambda: _check_image(response))


@pytest.mark.parametrize(
    "account",
    [
        None,
        True,
        False,
        111122223333,
        111122223333.0,
        [],
        {},
        b"111122223333",
        _StringSubclass(_ACCOUNT),
        "999900001111",
        "prefix" + _ACCOUNT,
        _ACCOUNT + "suffix",
        " " + _ACCOUNT,
        _ACCOUNT + "\n",
        _MARKER,
    ],
)
def test_caller_requires_exact_account_string(account: object) -> None:
    _assert_invalid(lambda: check_caller(_config(), {"Account": account}))


def test_caller_requires_account_field() -> None:
    _assert_invalid(lambda: check_caller(_config(), {"Arn": _ACCOUNT}))


@pytest.mark.parametrize("kind", ["AMAZON_ISSUED", "IMPORTED"])
@pytest.mark.parametrize(
    "names",
    [
        ["app.example.test"],
        ["APP.Example.Test"],
        ["*.example.test"],
        ["*.EXAMPLE.TEST"],
        ["other.example.test", "*.example.test"],
    ],
)
def test_certificate_accepts_exact_and_single_label_wildcard_sans(
    kind: str, names: list[str]
) -> None:
    certificate = _certificate()
    certificate.update(Type=kind, SubjectAlternativeNames=names, extra=_Unreadable())
    expected_certificate = certificate.copy()
    check_certificate(
        _config(), {"Certificate": certificate, "extra": _Unreadable()}, now=_NOW
    )
    assert certificate == expected_certificate


@pytest.mark.parametrize(
    ("before", "after", "now"),
    [
        ("2026-10-03T12:00:00Z", "2026-10-03T13:00:00Z", _NOW),
        ("2026-10-03T07:00:00-04:00", "2026-10-03T15:00:00+02:00", _NOW),
        (
            "2026-10-03T11:00:00.123456Z",
            "2026-10-03T18:30:00+05:30",
            _NOW.astimezone(timezone(timedelta(hours=5, minutes=30))),
        ),
    ],
)
def test_certificate_compares_aware_instants_and_includes_not_before(
    before: str, after: str, now: datetime
) -> None:
    certificate = _certificate()
    certificate.update(NotBefore=before, NotAfter=after)
    expected_certificate = deepcopy(certificate)
    check_certificate(_config(), {"Certificate": certificate}, now=now)
    assert certificate == expected_certificate


@pytest.mark.parametrize("fraction", ["1", "12", "123", "1234", "12345", "123456"])
@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
def test_certificate_accepts_one_through_six_fractional_digits(
    fraction: str, suffix: str
) -> None:
    certificate = _certificate()
    certificate.update(
        NotBefore=f"2026-10-03T11:00:00.{fraction}{suffix}",
        NotAfter=f"2026-10-03T13:00:00.{fraction}{suffix}",
    )
    check_certificate(_config(), {"Certificate": certificate}, now=_NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("NotBefore", "2026-10-03T12:00:00.0000001"),
        ("NotAfter", "2026-10-03T12:00:00.0000001"),
        ("NotBefore", "2026-10-03T11:00:00.1234567"),
        ("NotAfter", "2026-10-03T13:00:00.1234567"),
    ],
)
@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
def test_certificate_rejects_precision_beyond_microseconds(
    field: str, value: str, suffix: str
) -> None:
    certificate = _certificate()
    certificate[field] = value + suffix
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize("fraction", ["0", "00", "000", "0000", "00000", "000000"])
@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
def test_certificate_rejects_fractional_not_after_at_now(
    fraction: str, suffix: str
) -> None:
    certificate = _certificate()
    certificate["NotAfter"] = f"2026-10-03T12:00:00.{fraction}{suffix}"
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize("field", list(_certificate()))
def test_certificate_requires_every_metadata_field(field: str) -> None:
    certificate = _certificate()
    del certificate[field]
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize(
    "certificate",
    [None, True, 1, "certificate", [], {}, _DictSubclass(), UserDict()],
)
def test_certificate_requires_exact_nested_object(certificate: object) -> None:
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


def test_certificate_requires_runtime_and_certificate_wrapper() -> None:
    foundation = DeploymentConfig(_ACCOUNT, "foundation", None)
    _assert_invalid(
        lambda: check_certificate(foundation, {"Certificate": _certificate()}, now=_NOW)
    )
    _assert_invalid(lambda: check_certificate(_config(), _certificate(), now=_NOW))


@pytest.mark.parametrize("field", list(_certificate()))
@pytest.mark.parametrize(
    "value", [None, True, False, 123, 1.5, {}, (), b"value", _StringSubclass(_MARKER)]
)
def test_certificate_rejects_hostile_required_field_types(
    field: str, value: object
) -> None:
    certificate = _certificate()
    certificate[field] = value
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("CertificateArn", _ARN.replace(_ACCOUNT, "999900001111")),
        ("CertificateArn", _ARN + "/extra"),
        ("CertificateArn", _MARKER),
        ("Status", "PENDING_VALIDATION"),
        ("Status", "EXPIRED"),
        ("Status", "REVOKED"),
        ("Status", "issued"),
        ("Type", "PRIVATE"),
        ("Type", "IMPORTED "),
        ("NotBefore", "2026-10-03T12:00:01Z"),
        ("NotAfter", "2026-10-03T12:00:00Z"),
        ("NotAfter", "2026-10-03T11:59:59Z"),
    ],
)
def test_certificate_rejects_wrong_identity_state_and_validity(
    field: str, value: str
) -> None:
    certificate = _certificate()
    certificate[field] = value
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize(
    ("hostname", "names"),
    [
        ("app.example.test", []),
        ("app.example.test", _ListSubclass(["app.example.test"])),
        ("app.example.test", [None]),
        ("app.example.test", [True]),
        ("app.example.test", [123]),
        ("app.example.test", [_StringSubclass("app.example.test")]),
        ("app.example.test", ["app.example.test", _MARKER + "\n"]),
        ("app.example.test", ["app.example.test", "192.0.2.1"]),
        ("app.example.test", ["app.example.test", "K.example.test"]),
        ("app.example.test", ["192.0.2.1"]),
        ("app.example.test", ["*.192.0.2.1"]),
        ("app.example.test", ["2001:db8::1"]),
        ("app.example.test", ["https://app.example.test"]),
        ("app.example.test", ["app.example.test\n"]),
        ("app.example.test", ["app.example.test\x00"]),
        ("app.example.test", [" app.example.test"]),
        ("app.example.test", ["app. example.test"]),
        ("app.example.test", ["app.example.test."]),
        ("app.example.test", ["app..example.test"]),
        ("app.example.test", ["-app.example.test"]),
        ("app.example.test", ["app-.example.test"]),
        ("app.example.test", ["app_example.test"]),
        ("app.example.test", ["ápp.example.test"]),
        ("app.example.test", ["a" * 64 + ".example.test"]),
        ("app.example.test", [".".join(["a" * 63] * 4)]),
        ("app.example.test", ["app.*.test"]),
        ("app.example.test", ["*app.example.test"]),
        ("app.example.test", ["*.*.example.test"]),
        ("app.example.test", ["example.test"]),
        ("app.example.test", ["*.test"]),
        ("deep.app.example.test", ["*.example.test"]),
        ("example.test", ["*.example.test"]),
        ("test", ["*.test"]),
        ("evil-example.test", ["*.example.test"]),
        ("app.example.test.evil", ["*.example.test"]),
        ("evilapp.example.test", ["app.example.test"]),
    ],
)
def test_certificate_rejects_bad_sans_and_partial_or_multilabel_matches(
    hostname: str, names: object
) -> None:
    certificate = _certificate()
    certificate["SubjectAlternativeNames"] = names
    _assert_invalid(
        lambda: check_certificate(
            _config(hostname), {"Certificate": certificate}, now=_NOW
        )
    )


@pytest.mark.parametrize("field", ["NotBefore", "NotAfter"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        _MARKER,
        "2026-10-03",
        "2026-10-03T11:00:00",
        "2026-10-03 11:00:00Z",
        "2026-10-03T11:00:00Z\n",
        "2026-10-03T11:00:00+00:99",
        "2026-10-03T11:00:00+24:00",
        "2026-10-03T25:00:00Z",
        "2026-10-03T11:60:00Z",
        "2026-10-03T11:00:60Z",
        "2026-02-30T11:00:00Z",
        "0000-10-03T11:00:00Z",
    ],
)
def test_certificate_rejects_naive_and_malformed_timestamps(
    field: str, value: str
) -> None:
    certificate = _certificate()
    certificate[field] = value
    _assert_invalid(
        lambda: check_certificate(_config(), {"Certificate": certificate}, now=_NOW)
    )


@pytest.mark.parametrize(
    "now", [None, True, False, 123, 1.5, _MARKER, _NOW.replace(tzinfo=None)]
)
def test_certificate_requires_aware_datetime_now(now: object) -> None:
    _assert_invalid(
        lambda: check_certificate(
            _config(), {"Certificate": _certificate()}, now=cast(datetime, now)
        )
    )


@pytest.mark.parametrize(
    "details",
    [
        None,
        True,
        1,
        _MARKER,
        {},
        (),
        [],
        [_image(), _image()],
        [_MARKER],
        [None],
        [_DictSubclass(_image())],
        [UserDict(_image())],
        _ListSubclass([_image()]),
    ],
)
def test_image_requires_exactly_one_exact_metadata_object(details: object) -> None:
    _assert_invalid(lambda: _check_image({"imageDetails": details}))


def test_image_requires_details_field() -> None:
    _assert_invalid(lambda: _check_image(_image()))


@pytest.mark.parametrize("field", list(_image()))
def test_image_requires_all_metadata_fields(field: str) -> None:
    image = _image()
    del image[field]
    _assert_invalid(lambda: _check_image({"imageDetails": [image]}))


@pytest.mark.parametrize("field", list(_image()))
@pytest.mark.parametrize(
    "value",
    [None, True, False, 123, 1.5, [], {}, b"value", _StringSubclass(_MARKER), _MARKER],
)
def test_image_rejects_hostile_metadata_field_types(field: str, value: object) -> None:
    image = _image()
    image[field] = value
    _assert_invalid(lambda: _check_image({"imageDetails": [image]}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("imageDigest", "sha256:" + "b" * 64),
        ("imageDigest", _DIGEST + "\n"),
        ("repositoryName", "fewia/frontend"),
        ("repositoryName", _REPOSITORY + "/extra"),
        ("registryId", "999900001111"),
        ("registryId", 111122223333),
        ("registryId", _ACCOUNT + "\n"),
    ],
)
def test_image_requires_exact_digest_repository_and_registry(
    field: str, value: object
) -> None:
    image = _image()
    image[field] = value
    _assert_invalid(lambda: _check_image({"imageDetails": [image]}))


@pytest.mark.parametrize(
    "repository",
    ["ab", "a" * 256, "a0/b1", "fewia/app.backend_v1-dev"],
)
def test_image_accepts_bounded_repository_names(repository: str) -> None:
    image = _image()
    image.update(repositoryName=repository, extra=_Unreadable())
    expected_image = image.copy()
    check_image(
        _config(),
        {"imageDetails": [image]},
        repository_name=repository,
        digest=_DIGEST,
    )
    assert image == expected_image


@pytest.mark.parametrize(
    "repository",
    [
        None,
        True,
        123,
        [],
        _StringSubclass(_REPOSITORY),
        "",
        "a",
        "a" * 257,
        "--help",
        "-backend",
        "backend --profile private",
        "$(private-command)",
        "backend;private-command",
        "`private-command`",
        "https://example.test/backend",
        "backend@" + _DIGEST,
        " backend",
        "backend\n",
        "backend\x00",
        "Backend",
        "báckend",
        "/backend",
        "backend/",
        "fewia//backend",
        "fewia/-backend",
        "fewia/backend-",
        "fewia/.backend",
        "fewia/backend_",
        "fewia/backend..dev",
        _MARKER,
    ],
)
def test_image_rejects_bad_or_command_like_repository_arguments(
    repository: object,
) -> None:
    image = _image()
    image["repositoryName"] = repository
    _assert_invalid(
        lambda: check_image(
            _config(),
            {"imageDetails": [image]},
            repository_name=cast(str, repository),
            digest=_DIGEST,
        )
    )


@pytest.mark.parametrize(
    "digest",
    [
        None,
        True,
        123,
        [],
        _StringSubclass(_DIGEST),
        "",
        "latest",
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "１" * 64,
        "SHA256:" + "a" * 64,
        "sha384:" + "a" * 64,
        " " + _DIGEST,
        _DIGEST + "\n",
        "--help",
        _MARKER,
    ],
)
def test_image_validates_digest_argument_even_when_response_matches(
    digest: object,
) -> None:
    image = _image()
    image["imageDigest"] = digest
    _assert_invalid(
        lambda: check_image(
            _config(),
            {"imageDetails": [image]},
            repository_name=_REPOSITORY,
            digest=cast(str, digest),
        )
    )


def test_all_checks_preserve_inputs_on_success_and_failure() -> None:
    config = _config()
    expected_config = deepcopy(config)
    caller: dict[str, object] = {"Account": _ACCOUNT, "extra": ["retained"]}
    certificate: dict[str, object] = {"Certificate": _certificate()}
    image: dict[str, object] = {"imageDetails": [_image()]}
    expected = deepcopy((caller, certificate, image))
    check_caller(config, caller)
    check_certificate(config, certificate, now=_NOW)
    _check_image(image)
    assert (caller, certificate, image) == expected
    caller["Account"] = _MARKER
    cast(dict[str, object], certificate["Certificate"])["NotAfter"] = _MARKER
    cast(list[dict[str, object]], image["imageDetails"])[0]["registryId"] = _MARKER
    expected = deepcopy((caller, certificate, image))
    _assert_invalid(lambda: check_caller(config, caller))
    _assert_invalid(lambda: check_certificate(config, certificate, now=_NOW))
    _assert_invalid(lambda: _check_image(image))
    assert (caller, certificate, image) == expected
    assert config == expected_config


def test_all_checks_use_explicit_inputs_without_io_or_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("preflight performed an external operation")

    config = _config()
    caller: dict[str, object] = {"Account": _ACCOUNT}
    certificate: dict[str, object] = {"Certificate": _certificate()}
    image: dict[str, object] = {"imageDetails": [_image()]}
    expected = deepcopy((config, caller, certificate, image))
    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(os, "getenv", forbidden)
        guarded.setattr(type(os.environ), "__getitem__", forbidden)
        guarded.setattr(socket, "socket", forbidden)
        guarded.setattr(subprocess, "Popen", forbidden)
        guarded.setattr(Construct, "__init__", forbidden)
        guarded.setattr(ecs.ContainerImage, "from_ecr_repository", forbidden)
        check_caller(config, caller)
        check_certificate(config, certificate, now=_NOW)
        _check_image(image)
        assert (config, caller, certificate, image) == expected
        with pytest.raises(PreflightError, match=f"^{_ERROR}$"):
            check_caller(_config(), {"Account": _MARKER})
        with pytest.raises(PreflightError, match=f"^{_ERROR}$"):
            check_certificate(_config(), {}, now=_NOW)
        with pytest.raises(PreflightError, match=f"^{_ERROR}$"):
            _check_image({"imageDetails": []})
