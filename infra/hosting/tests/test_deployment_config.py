import builtins
import os
import socket
import subprocess
import traceback
from collections import UserDict
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Literal, Never, cast
from unittest.mock import patch

import pytest
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from deployment_config import (
    REGION,
    DeploymentConfig,
    RuntimeConfig,
    parse_deployment_config,
)
from identity import _validate_hostname, _validate_prefix
from task_settings import image_from_digest

_ACCOUNT = "111122223333"
_CERTIFICATE = (
    f"arn:aws:acm:us-east-1:{_ACCOUNT}:certificate/12345678-1234-abcd-1234-123456789abc"
)
_BACKEND = "sha256:" + "0123456789abcdef" * 4
_FRONTEND = "sha256:" + "a" * 64
_FIELDS = (
    "hostname",
    "domain_prefix",
    "certificate_arn",
    "backend_digest",
    "frontend_digest",
)
_ERROR = "deployment configuration is invalid"


class _DictSubclass(dict[str, object]):
    pass


class _StringSubclass(str):
    pass


def _runtime() -> dict[str, str]:
    return {
        "hostname": "example.test",
        "domain_prefix": "fewia-dev",
        "certificate_arn": _CERTIFICATE,
        "backend_digest": _BACKEND,
        "frontend_digest": _FRONTEND,
    }


def _config(phase: str = "active") -> dict[str, object]:
    return {"account": _ACCOUNT, "phase": phase, "runtime": _runtime()}


def _assert_invalid(raw: object) -> None:
    with pytest.raises(ValueError) as error:
        parse_deployment_config(raw)
    assert type(error.value) is ValueError
    assert error.value.args == (_ERROR,)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.parametrize("include_runtime", [False, True])
def test_foundation_has_no_runtime(include_runtime: bool) -> None:
    raw: dict[str, object] = {"account": _ACCOUNT, "phase": "foundation"}
    if include_runtime:
        raw["runtime"] = None
    result = parse_deployment_config(raw)
    assert type(result) is DeploymentConfig
    assert result == DeploymentConfig(_ACCOUNT, "foundation", None)
    assert REGION == "us-east-1"


@pytest.mark.parametrize("phase", ["bootstrap", "active"])
def test_runtime_phases_return_exact_frozen_values(
    phase: Literal["bootstrap", "active"],
) -> None:
    result = parse_deployment_config(_config(phase))
    expected = RuntimeConfig(
        "example.test", "fewia-dev", _CERTIFICATE, _BACKEND, _FRONTEND
    )
    assert type(result) is DeploymentConfig
    assert type(result.runtime) is RuntimeConfig
    assert result == DeploymentConfig(_ACCOUNT, phase, expected)
    assert result.runtime is not None
    assert not hasattr(result, "__dict__")
    assert not hasattr(result.runtime, "__dict__")
    for field in ("account", "phase", "runtime"):
        with pytest.raises(FrozenInstanceError):
            setattr(result, field, None)
    for field in _FIELDS:
        with pytest.raises(FrozenInstanceError):
            setattr(result.runtime, field, "changed")


def test_input_mutation_cannot_change_parsed_values() -> None:
    raw = _config()
    runtime = cast(dict[str, object], raw["runtime"])
    result = parse_deployment_config(raw)
    for field in _FIELDS:
        runtime[field] = "changed"
    runtime.clear()
    raw.clear()
    assert result == DeploymentConfig(
        _ACCOUNT,
        "active",
        RuntimeConfig("example.test", "fewia-dev", _CERTIFICATE, _BACKEND, _FRONTEND),
    )


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        False,
        12,
        1.5,
        "{}",
        b"{}",
        [],
        (),
        list(_config().items()),
        _DictSubclass(_config()),
        UserDict(_config()),
    ],
)
def test_non_exact_top_level_dictionary_is_rejected(raw: object) -> None:
    _assert_invalid(raw)


@pytest.mark.parametrize("field", ["account", "phase"])
def test_top_level_required_fields_cannot_be_missing(field: str) -> None:
    raw = _config()
    del raw[field]
    _assert_invalid(raw)


@pytest.mark.parametrize(
    "field",
    ["region", "hostname", "certificate_arn", "digest", "credentials", 1, None],
)
def test_top_level_unknown_and_nonstring_keys_are_rejected(field: object) -> None:
    raw: dict[object, object] = {key: value for key, value in _config().items()}
    raw[field] = {"private_input": "SYNTHETIC_PRIVATE_INPUT"}
    _assert_invalid(raw)


def test_string_subclass_keys_are_rejected_at_both_levels() -> None:
    raw: dict[object, object] = {key: value for key, value in _config().items()}
    del raw["account"]
    raw[_StringSubclass("account")] = _ACCOUNT
    _assert_invalid(raw)
    runtime: dict[object, object] = {key: value for key, value in _runtime().items()}
    del runtime["hostname"]
    runtime[_StringSubclass("hostname")] = "example.test"
    _assert_invalid({"account": _ACCOUNT, "phase": "active", "runtime": runtime})


@pytest.mark.parametrize("field", ["account", "phase", *_FIELDS])
@pytest.mark.parametrize(
    "value", [None, True, False, 123, 1.5, b"value", [], {}, _StringSubclass("value")]
)
def test_all_fields_require_exact_strings(field: str, value: object) -> None:
    raw = _config()
    if field in ("account", "phase"):
        raw[field] = value
    else:
        cast(dict[str, object], raw["runtime"])[field] = value
    _assert_invalid(raw)


@pytest.mark.parametrize(
    "account",
    [
        "",
        "123",
        _ACCOUNT[:-1],
        _ACCOUNT + "0",
        " " + _ACCOUNT,
        _ACCOUNT + "\n",
        "１２３４５６７８９０１２",
        "١٢٣٤٥٦٧٨٩٠١٢",
        "${Token[Account.1]}",
    ],
)
def test_account_requires_twelve_ascii_digits(account: str) -> None:
    _assert_invalid({"account": account, "phase": "foundation"})


@pytest.mark.parametrize("phase", ["", "Active", "active ", "active\n", "deploy"])
def test_only_explicit_staged_phases_are_accepted(phase: str) -> None:
    _assert_invalid(_config(phase))


@pytest.mark.parametrize("phase", ["bootstrap", "active"])
def test_runtime_cannot_be_omitted_or_null(phase: str) -> None:
    raw = _config(phase)
    del raw["runtime"]
    _assert_invalid(raw)
    raw["runtime"] = None
    _assert_invalid(raw)


@pytest.mark.parametrize(
    "runtime", [True, False, 123, "runtime", [], {}, _runtime(), UserDict(_runtime())]
)
def test_foundation_rejects_every_nonnull_runtime(runtime: object) -> None:
    _assert_invalid({"account": _ACCOUNT, "phase": "foundation", "runtime": runtime})


@pytest.mark.parametrize(
    "runtime",
    [True, False, 123, "runtime", [], _DictSubclass(_runtime()), UserDict(_runtime())],
)
def test_runtime_requires_an_exact_dictionary(runtime: object) -> None:
    _assert_invalid({"account": _ACCOUNT, "phase": "active", "runtime": runtime})


@pytest.mark.parametrize("field", _FIELDS)
def test_each_runtime_field_is_required(field: str) -> None:
    raw = _config()
    del cast(dict[str, object], raw["runtime"])[field]
    _assert_invalid(raw)


@pytest.mark.parametrize(
    "field", ["credentials", "region", "account", "phase", "digest", "extra", 1, None]
)
def test_runtime_rejects_unknown_and_nonstring_keys(field: object) -> None:
    runtime: dict[object, object] = {key: value for key, value in _runtime().items()}
    runtime[field] = {"private_input": "SYNTHETIC_PRIVATE_INPUT"}
    _assert_invalid({"account": _ACCOUNT, "phase": "active", "runtime": runtime})


@pytest.mark.parametrize(
    ("field", "validator", "values"),
    [
        (
            "hostname",
            _validate_hostname,
            [
                "",
                "localhost",
                "Example.test",
                "example.test.",
                "*.example.test",
                "https://example.test",
                "example.test/path",
                "example.test:443",
                "127.0.0.1",
                "127.1",
                " example.test",
                "example.test\n",
                "example..test",
                "-example.test",
                "example-.test",
                "éxample.test",
                "a" * 64 + ".test",
                ".".join(["a" * 63] * 4),
            ],
        ),
        (
            "domain_prefix",
            _validate_prefix,
            [
                "",
                "ab",
                "a" * 64,
                "-abc",
                "abc-",
                "Fewia",
                "fewia.dev",
                "fewia_dev",
                "fewia/dev",
                " fewia",
                "fewia\n",
                "féwia",
                "aws",
                "amazon",
                "cognito",
                "fewia-aws-dev",
                "mycognitoapp",
            ],
        ),
    ],
)
def test_invalid_names_agree_with_identity_validators(
    field: str, validator: Callable[[str], None], values: list[str]
) -> None:
    for value in values:
        with pytest.raises(ValueError):
            validator(value)
        raw = _config()
        cast(dict[str, object], raw["runtime"])[field] = value
        _assert_invalid(raw)


@pytest.mark.parametrize(
    ("hostname", "prefix"),
    [
        ("example.test", "abc"),
        ("a.b", "a0b"),
        ("0app.my-app.test", "fewia--dev"),
        ("a" * 63 + ".test", "a" * 63),
        (".".join(["a" * 63] * 3 + ["a" * 61]), "fewia-dev"),
    ],
)
def test_valid_names_agree_with_identity_validators(hostname: str, prefix: str) -> None:
    _validate_hostname(hostname)
    _validate_prefix(prefix)
    runtime = _runtime()
    runtime.update(hostname=hostname, domain_prefix=prefix)
    result = parse_deployment_config(
        {"account": _ACCOUNT, "phase": "bootstrap", "runtime": runtime}
    )
    assert result.runtime is not None
    assert result.runtime.hostname == hostname
    assert result.runtime.domain_prefix == prefix


@pytest.mark.parametrize(
    "certificate",
    [
        "",
        " " + _CERTIFICATE,
        _CERTIFICATE + " ",
        _CERTIFICATE + "\n",
        _CERTIFICATE.replace("arn:aws:", "arn:aws-cn:"),
        _CERTIFICATE.replace("us-east-1", "us-west-2"),
        _CERTIFICATE.replace(_ACCOUNT, "999900001111"),
        _CERTIFICATE.replace(_ACCOUNT, "11112222333"),
        _CERTIFICATE.replace("certificate/", "certificate:"),
        _CERTIFICATE.replace("abcd", "ABCD"),
        _CERTIFICATE.replace("abcd", "abcg"),
        _CERTIFICATE.replace("12345678-", "1234567-", 1),
        _CERTIFICATE.replace("1234-abcd", "123-abcd"),
        _CERTIFICATE.replace("abcd-1234", "abcd-123"),
        _CERTIFICATE[:-1],
        _CERTIFICATE + "/extra",
        _CERTIFICATE.replace("acm:", "iam:"),
        "${Token[Certificate.1]}",
        "https://example.test/" + _CERTIFICATE,
    ],
)
def test_certificate_matches_edge_account_region_and_uuid_contract(
    certificate: str,
) -> None:
    raw = _config()
    cast(dict[str, object], raw["runtime"])["certificate_arn"] = certificate
    _assert_invalid(raw)


@pytest.mark.parametrize("field", ["backend_digest", "frontend_digest"])
@pytest.mark.parametrize(
    "digest",
    [
        "",
        "latest",
        "v1.0",
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "１" * 64,
        "sha384:" + "a" * 64,
        " " + _BACKEND,
        _BACKEND + " ",
        "\t" + _BACKEND,
        _BACKEND + "\n",
        "sha256: " + "a" * 64,
        "https://example.invalid/repository@" + _BACKEND,
        "111122223333.dkr.ecr.us-east-1.amazonaws.com/backend@" + _BACKEND,
        "backend:" + _BACKEND,
        "${Token[Digest.1]}",
    ],
)
def test_invalid_digests_agree_with_task_settings(field: str, digest: str) -> None:
    with patch.object(ecs.ContainerImage, "from_ecr_repository") as constructor:
        with pytest.raises(ValueError):
            image_from_digest(cast(ecr.IRepository, object()), digest)
        constructor.assert_not_called()
    raw = _config()
    cast(dict[str, object], raw["runtime"])[field] = digest
    _assert_invalid(raw)


@pytest.mark.parametrize("digest", [_BACKEND, _FRONTEND, "sha256:" + "0" * 64])
def test_valid_digests_agree_without_constructing_resources(digest: str) -> None:
    repository = cast(ecr.IRepository, object())
    with patch.object(ecs.ContainerImage, "from_ecr_repository") as constructor:
        image_from_digest(repository, digest)
        constructor.assert_called_once_with(repository, digest)
    runtime = _runtime()
    runtime.update(backend_digest=digest, frontend_digest=digest)
    result = parse_deployment_config(
        {"account": _ACCOUNT, "phase": "active", "runtime": runtime}
    )
    assert result.runtime is not None
    assert result.runtime.backend_digest == result.runtime.frontend_digest == digest


def test_identity_errors_cannot_expose_inputs_or_nested_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(hostname: str) -> Never:
        raise ValueError("SYNTHETIC_PRIVATE_INPUT: " + hostname)

    monkeypatch.setattr("deployment_config._validate_hostname", fail)
    with pytest.raises(ValueError) as error:
        parse_deployment_config(_config())
    assert str(error.value) == _ERROR
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    rendered = "".join(traceback.format_exception(error.value))
    assert "SYNTHETIC_PRIVATE_INPUT" not in rendered
    assert "example.test" not in rendered


def test_parser_uses_only_explicit_inputs_without_io_or_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("parser performed an external operation")

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(os, "getenv", forbidden)
        guarded.setattr(type(os.environ), "__getitem__", forbidden)
        guarded.setattr(socket, "socket", forbidden)
        guarded.setattr(subprocess, "Popen", forbidden)
        guarded.setattr(Construct, "__init__", forbidden)
        guarded.setattr(ecs.ContainerImage, "from_ecr_repository", forbidden)
        assert parse_deployment_config(_config()).phase == "active"
        assert parse_deployment_config(_config("bootstrap")).phase == "bootstrap"
        foundation = parse_deployment_config(
            {"account": _ACCOUNT, "phase": "foundation"}
        )
        assert foundation.runtime is None
        _assert_invalid({"account": _ACCOUNT})
        _assert_invalid({"account": _ACCOUNT, "phase": "active"})
