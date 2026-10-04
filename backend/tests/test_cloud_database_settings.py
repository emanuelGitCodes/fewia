from __future__ import annotations

import builtins
import os
import socket
import traceback
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy
from sqlalchemy.engine import URL, make_url

from app.cloud_database_settings import cloud_database_url

_ERROR = "Cloud database configuration is invalid"
_HOST = "fewia-db.abc123def456.us-east-1.rds.amazonaws.com"
_FIELDS = (
    "FEWIA_DATABASE_HOST",
    "FEWIA_DATABASE_NAME",
    "FEWIA_DATABASE_USER",
    "FEWIA_DATABASE_PASSWORD",
)
_FORBIDDEN = (
    "DATABASE_URL",
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSSLMODE",
    "PGSSLROOTCERT",
)


def aws_config() -> dict[str, str]:
    return {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": _HOST,
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_DATABASE_PASSWORD": "test-password",
    }


def assert_invalid(config: Mapping[str, object]) -> ValueError:
    with pytest.raises(ValueError) as caught:
        cloud_database_url(cast(Mapping[str, str], config))
    error = caught.value
    assert type(error) is ValueError
    assert error.args == (_ERROR,)
    assert error.__cause__ is None
    assert error.__context__ is None
    return error


@pytest.mark.parametrize("mode", [None, "local"])
def test_local_preserves_legacy_configuration(mode: str | None) -> None:
    config = {key: "legacy-value" for key in _FORBIDDEN}
    if mode is not None:
        config["FEWIA_DATABASE_MODE"] = mode
    before = config.copy()
    assert cloud_database_url(config) is None
    assert config == before


def test_default_environment_and_explicit_empty_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = aws_config()
    before = config.copy()
    monkeypatch.setattr(os, "environ", config)
    url = cloud_database_url()
    assert isinstance(url, URL)
    assert url.host == _HOST
    assert cloud_database_url({}) is None
    assert config == before


@pytest.mark.parametrize("mode", [None, "local"])
@pytest.mark.parametrize("field", _FIELDS)
def test_local_rejects_each_cloud_field(mode: str | None, field: str) -> None:
    config = {field: ""}
    if mode is not None:
        config["FEWIA_DATABASE_MODE"] = mode
    assert_invalid(config)


@pytest.mark.parametrize("mode", ["", "AWS", "Local", "Aws", " aws", "aws ", "other"])
def test_mode_is_exact(mode: str) -> None:
    config = aws_config()
    config["FEWIA_DATABASE_MODE"] = mode
    assert_invalid(config)


@pytest.mark.parametrize("field", _FIELDS)
def test_aws_requires_every_field(field: str) -> None:
    config = aws_config()
    del config[field]
    assert_invalid(config)


@pytest.mark.parametrize("field", _FIELDS)
def test_aws_rejects_empty_fields(field: str) -> None:
    config = aws_config()
    config[field] = ""
    assert_invalid(config)


@pytest.mark.parametrize("field", ("FEWIA_DATABASE_MODE", *_FIELDS, *_FORBIDDEN))
def test_invalid_configuration_does_not_mutate_input(field: str) -> None:
    config = aws_config()
    config[field] = ""
    before = config.copy()
    assert_invalid(config)
    assert config == before


@pytest.mark.parametrize("user", ["fewia_app", "fewia_admin"])
@pytest.mark.parametrize(
    "host",
    [
        _HOST,
        "a.b.us-east-1.rds.amazonaws.com",
        "a-1.0-b.us-east-1.rds.amazonaws.com",
        f"{'a' * 63}.{'b' * 63}.us-east-1.rds.amazonaws.com",
    ],
)
def test_valid_url_contract(user: str, host: str) -> None:
    config = aws_config()
    config.update(FEWIA_DATABASE_USER=user, FEWIA_DATABASE_HOST=host)
    before = config.copy()
    url = cloud_database_url(config)
    assert isinstance(url, URL)
    assert url.drivername == "postgresql+psycopg"
    assert url.username == user
    assert url.password == "test-password"
    assert url.host == host
    assert url.port == 5432
    assert url.database == "fewia"
    assert dict(url.query) == {
        "sslmode": "verify-full",
        "sslrootcert": "/app/infra/rds/us-east-1-bundle.pem",
    }
    assert config == before


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        f"https://{_HOST}",
        f"postgresql://{_HOST}",
        f"{_HOST}:5432",
        f"user@{_HOST}",
        f"{_HOST}?sslmode=disable",
        f"{_HOST}/fewia",
        f"{_HOST}.",
        f" {_HOST}",
        f"{_HOST}\n",
        f"{_HOST}\x00",
        _HOST.upper(),
        "fewia-db.abc123def456.us-west-2.rds.amazonaws.com",
        "fewia-db.abc123def456.us-east-1.rds.amazonaws.com.cn",
        "fewia-db.abc123def456.us-east-1.rds.amazonaws.com.evil.test",
        "fewia-db.us-east-1.rds.amazonaws.com",
        "extra.fewia-db.abc123def456.us-east-1.rds.amazonaws.com",
        "-a.b.us-east-1.rds.amazonaws.com",
        "a-.b.us-east-1.rds.amazonaws.com",
        "a.-b.us-east-1.rds.amazonaws.com",
        "a.b-.us-east-1.rds.amazonaws.com",
        "a_b.c.us-east-1.rds.amazonaws.com",
        "a.b_c.us-east-1.rds.amazonaws.com",
        "é.b.us-east-1.rds.amazonaws.com",
        ".b.us-east-1.rds.amazonaws.com",
        "a..us-east-1.rds.amazonaws.com",
        f"{'a' * 64}.b.us-east-1.rds.amazonaws.com",
        f"a.{'b' * 64}.us-east-1.rds.amazonaws.com",
        f"{'a' * 254}.b.us-east-1.rds.amazonaws.com",
    ],
)
def test_rejects_invalid_hosts(host: str) -> None:
    config = aws_config()
    config["FEWIA_DATABASE_HOST"] = host
    assert_invalid(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("FEWIA_DATABASE_NAME", "Fewia"),
        ("FEWIA_DATABASE_NAME", "fewia "),
        ("FEWIA_DATABASE_NAME", "postgres"),
        ("FEWIA_DATABASE_USER", "fewia"),
        ("FEWIA_DATABASE_USER", "FEWIA_APP"),
        ("FEWIA_DATABASE_USER", "fewia_app "),
    ],
)
def test_database_and_user_are_fixed(field: str, value: str) -> None:
    config = aws_config()
    config[field] = value
    assert_invalid(config)


class StringSubclass(str):
    pass


class UnprintableValue:
    def __repr__(self) -> str:
        raise AssertionError("Do not format invalid values")

    def __str__(self) -> str:
        raise AssertionError("Do not format invalid values")


@pytest.mark.parametrize("field", ("FEWIA_DATABASE_MODE", *_FIELDS))
@pytest.mark.parametrize("value", [None, True, 42, [], {}, UnprintableValue()])
def test_rejects_non_string_values(field: str, value: object) -> None:
    config: dict[str, object] = dict(aws_config())
    config[field] = value
    assert_invalid(config)


@pytest.mark.parametrize("field", ("FEWIA_DATABASE_MODE", *_FIELDS))
def test_rejects_string_subclasses(field: str) -> None:
    config = aws_config()
    config[field] = StringSubclass(config[field])
    assert_invalid(config)


@pytest.mark.parametrize(
    "password",
    ["x", "x" * 128, " @:/?#[]%+&='\"\\;!$(){}<>|`~ ", "résumé🔐"],
)
def test_password_round_trip_and_redaction(password: str) -> None:
    config = aws_config()
    config["FEWIA_DATABASE_PASSWORD"] = password
    url = cloud_database_url(config)
    assert isinstance(url, URL)
    assert url.password == password
    assert make_url(url.render_as_string(hide_password=False)) == url
    assert "***@" in str(url)
    assert "***@" in repr(url)
    assert password not in str(url)
    assert password not in repr(url)


@pytest.mark.parametrize("password", ["", "x" * 129])
def test_password_length_bounds(password: str) -> None:
    config = aws_config()
    config["FEWIA_DATABASE_PASSWORD"] = password
    assert_invalid(config)


@pytest.mark.parametrize("control", [*(chr(code) for code in range(32)), "\x7f"])
def test_password_rejects_ascii_controls(control: str) -> None:
    config = aws_config()
    config["FEWIA_DATABASE_PASSWORD"] = f"before{control}after"
    assert_invalid(config)


class DefaultContainsForbiddenValueMapping(Mapping[str, str]):
    def __init__(self, key: str) -> None:
        self.values_by_key = aws_config()
        self.values_by_key[key] = ""
        self.forbidden_key = key
        self.forbidden_reads = 0

    def __getitem__(self, key: str) -> str:
        if key == self.forbidden_key:
            self.forbidden_reads += 1
            raise AssertionError("Do not read forbidden values")
        return self.values_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values_by_key)

    def __len__(self) -> int:
        return len(self.values_by_key)


class ForbiddenValueMapping(DefaultContainsForbiddenValueMapping):
    def __contains__(self, key: object) -> bool:
        return key in self.values_by_key


@pytest.mark.parametrize("key", _FORBIDDEN)
def test_forbidden_keys_use_presence_only(key: str) -> None:
    config = ForbiddenValueMapping(key)
    assert_invalid(config)
    assert config.forbidden_reads == 0


@pytest.mark.parametrize("key", _FORBIDDEN)
def test_forbidden_keys_use_presence_only_with_default_contains(key: str) -> None:
    config = DefaultContainsForbiddenValueMapping(key)
    assert_invalid(config)
    assert config.forbidden_reads == 0


def test_errors_hide_input_and_mapping_exception_context() -> None:
    secret = "private-test-marker"
    config = aws_config()
    config["FEWIA_DATABASE_HOST"] = secret
    config["FEWIA_DATABASE_PASSWORD"] = secret
    error = assert_invalid(config)
    assert secret not in repr(error)
    assert secret not in "".join(traceback.format_exception(error))

    class FailingMapping(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise RuntimeError(secret)

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    error = assert_invalid(FailingMapping())
    assert secret not in "".join(traceback.format_exception(error))


def test_invalid_values_precede_url_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def reject_construction(*args: object, **kwargs: object) -> URL:
        calls.append((args, kwargs))
        raise AssertionError("Do not construct an invalid URL")

    monkeypatch.setattr(URL, "create", reject_construction)
    config = aws_config()
    config["FEWIA_DATABASE_PASSWORD"] = ""
    assert_invalid(config)
    assert calls == []


def test_no_filesystem_network_or_engine_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def reject_io(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("Do not access files or network")

    monkeypatch.setattr(builtins, "open", reject_io)
    monkeypatch.setattr(os, "open", reject_io)
    monkeypatch.setattr(Path, "open", reject_io)
    monkeypatch.setattr(socket, "socket", reject_io)
    monkeypatch.setattr(socket, "create_connection", reject_io)
    monkeypatch.setattr(sqlalchemy, "create_engine", reject_io)
    assert cloud_database_url({}) is None
    assert isinstance(cloud_database_url(aws_config()), URL)
    assert calls == []
