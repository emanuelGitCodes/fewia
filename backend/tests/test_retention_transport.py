from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app import retention_admin

_ARGS = ["preview", "--owner-id", "1", "--before", "2026-11-11T12:00:00+00:00"]
_LOCAL = "postgresql://operator@localhost/fewia_eval_retention"
_REMOTE = "postgresql://operator@db.example.test/fewia_eval_retention"
_TLS = "sslmode=verify-full&sslrootcert=%2Fpublic%2Fca.pem"
_REFUSED = '{"error":"operator_retention_refused"}\n'
_ENV_OVERRIDES = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGSSLMODE",
    "PGSSLROOTCERT",
    "PGREQUIRESSL",
    "PGGSSENCMODE",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FEWIA_DATABASE_MODE", "local")
    for key in retention_admin._LIBPQ_OVERRIDES:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture()
def engine_factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    engine = MagicMock(spec=sa.Engine)
    factory = MagicMock(return_value=engine)

    class PreviewOnly:
        def __init__(self, supplied_engine: sa.Engine) -> None:
            assert supplied_engine is engine

        def preview(self, *, owner_id: int, before: datetime) -> dict[str, object]:
            assert owner_id == 1
            assert before.isoformat() == "2026-11-11T12:00:00+00:00"
            return {"digest": "a" * 64}

    monkeypatch.setattr(retention_admin.sa, "create_engine", factory)
    monkeypatch.setattr(retention_admin, "OperatorRetention", PreviewOnly)
    return factory


def _refuses(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("FEWIA_RETENTION_DATABASE_URL", database_url)
    assert retention_admin.main(_ARGS) == 2
    captured = capsys.readouterr()
    assert captured.out == _REFUSED
    assert captured.err == ""
    engine_factory.assert_not_called()


@pytest.mark.parametrize(
    "mode", [None, "disable", "allow", "prefer", "require", "verify-ca"]
)
def test_remote_requires_explicit_verified_tls(
    mode: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    query = "sslrootcert=/public/ca.pem"
    if mode is not None:
        query += f"&sslmode={mode}"
    _refuses(f"{_REMOTE}?{query}", monkeypatch, capsys, engine_factory)


@pytest.mark.parametrize(
    "database_url",
    [
        _REMOTE,
        f"{_REMOTE}?sslmode=verify-full",
        "postgresql://operator@/database",
        "postgresql://operator@/database?host=/var/run/postgresql",
        "postgresql://localhost/database",
        "postgresql://@localhost/database",
        "postgresql://operator@localhost/",
        "postgresql://fewia_app@localhost/database",
        "postgresql://fewia_maintenance@localhost/database",
        "postgresql+psycopg2://operator@localhost/database",
        "sqlite:///database",
        "postgresql://operator@localhost,remote/database",
        "postgresql://operator@localhost:5432,remote:5432/database",
        "postgresql://operator@[::1],remote/database",
        "postgresql://operator@[::1]ignored/database",
        "postgresql://operator@::1/database",
        "postgresql://operator@localhost:/database",
        "postgresql://operator@localhost:0/database",
        "postgresql://operator@localhost:65536/database",
        "postgresql://operator@localhost:invalid/database",
        "postgresql://private-operator:synthetic-password@localhost:invalid/private-db",
        "postgresql://operator@localhost%2Fremote/database",
        "postgresql://operator@/var/run/postgresql/database",
        "postgresql://operator@localhost\\remote/database",
        "postgresql://operator@local host/database",
        "postgresql://operator@localhost\n/database",
        "postgresql://operator@localhost%00/database",
        "postgresql://operator@localhost/database/other",
        "postgresql://operator@localhost/host=remote",
        "postgresql://operator@localhost/postgresql%3A%2F%2Fremote%2Fdatabase",
        "postgresql://oper%20ator@localhost/database",
        "postgresql://operator@localhost/database?",
    ],
)
def test_invalid_targets_refuse_before_engine_creation(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    _refuses(database_url, monkeypatch, capsys, engine_factory)


@pytest.mark.parametrize(
    "query",
    [
        "host=remote",
        "hostaddr=192.0.2.1",
        "port=5433",
        "user=other",
        "service=other",
        "dbname=other",
        "sslcert=/private/client.pem",
        "gssencmode=require",
        "options=-csearch_path=other",
        "host=",
        "sslmode=",
        "sslmode",
        "sslmode=verify-full&sslmode=disable",
        "sslmode=verify-full&sslmode=verify-full",
        "sslmode=verify-full&sslmode=",
        "sslrootcert=/public/a.pem&sslrootcert=/public/b.pem",
        "sslrootcert=/public/a.pem&sslrootcert=/public/a.pem",
        "sslrootcert=",
        "sslrootcert=relative.pem",
        "sslrootcert=system",
        "sslrootcert=/",
        "sslrootcert=//public/ca.pem",
        "sslrootcert=/public/../ca.pem",
        "sslrootcert=/public/./ca.pem",
        "sslrootcert=/public//ca.pem",
        "sslrootcert=/public/ca.pem/",
        "sslrootcert=/public/ca%00.pem",
        "sslrootcert=/public/ca%0A.pem",
        "sslrootcert=/public/ca%20file.pem",
        "sslrootcert=/public%5Cca.pem",
        "sslrootcert=/public/ca.pem#fragment",
        "sslrootcert=/public/%ZZ.pem",
        "sslrootcert=/public/%FF.pem",
    ],
)
def test_query_overrides_and_ambiguous_tls_options_refuse(
    query: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    _refuses(f"{_LOCAL}?{query}", monkeypatch, capsys, engine_factory)


@pytest.mark.parametrize("key", _ENV_OVERRIDES)
@pytest.mark.parametrize("value", ["", "private-override"])
def test_libpq_environment_overrides_refuse_by_presence(
    key: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv(key, value)
    _refuses(f"{_REMOTE}?{_TLS}", monkeypatch, capsys, engine_factory)


def test_environment_override_values_are_not_read(
    monkeypatch: pytest.MonkeyPatch, engine_factory: MagicMock
) -> None:
    class PresenceOnly(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError("Environment values MUST NOT be read.")

        def __iter__(self) -> Iterator[str]:
            yield "PGHOST"

        def __len__(self) -> int:
            return 1

        def __contains__(self, key: object) -> bool:
            return key == "PGHOST"

    with monkeypatch.context() as patch:
        patch.setattr(retention_admin.os, "environ", PresenceOnly())
        with pytest.raises(retention_admin.RetentionError):
            retention_admin._operator_url(_LOCAL)
    engine_factory.assert_not_called()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "postgres"])
def test_exact_local_targets_allow_plaintext(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.delenv("FEWIA_DATABASE_MODE", raising=False)
    monkeypatch.setenv(
        "FEWIA_RETENTION_DATABASE_URL", f"postgresql://operator@{host}:5432/database"
    )
    assert retention_admin.main(_ARGS) == 0
    assert capsys.readouterr().err == ""
    engine_factory.assert_called_once()
    url = engine_factory.call_args.args[0]
    assert isinstance(url, URL)
    assert url.drivername == "postgresql+psycopg"
    assert not url.query
    assert engine_factory.call_args.kwargs == {
        "poolclass": NullPool,
        "hide_parameters": True,
        "connect_args": {"connect_timeout": 3, "gssencmode": "disable"},
    }
    engine_factory.return_value.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "[::1]", "postgres", "db.example.test", "localhost."],
)
@pytest.mark.parametrize("mode", ["local", "aws"])
def test_verified_tls_passes_explicit_ca_to_engine(
    host: str,
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("FEWIA_DATABASE_MODE", mode)
    monkeypatch.setenv(
        "FEWIA_RETENTION_DATABASE_URL",
        f"postgresql+psycopg://operator:synthetic%40password@{host}/database?{_TLS}",
    )
    assert retention_admin.main(_ARGS) == 0
    assert capsys.readouterr().out == '{"digest":"' + "a" * 64 + '"}\n'
    engine_factory.assert_called_once()
    url = engine_factory.call_args.args[0]
    assert url.query == {"sslmode": "verify-full", "sslrootcert": "/public/ca.pem"}
    assert url.password == "synthetic@password"
    assert engine_factory.call_args.kwargs["connect_args"] == {
        "connect_timeout": 3,
        "gssencmode": "disable",
    }


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "postgres"])
@pytest.mark.parametrize("query", ["", "?sslmode=disable", "?sslmode=require"])
def test_aws_mode_requires_tls_for_local_names(
    host: str,
    query: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("FEWIA_DATABASE_MODE", "aws")
    _refuses(
        f"postgresql://operator@{host}/database{query}",
        monkeypatch,
        capsys,
        engine_factory,
    )


@pytest.mark.parametrize(
    "host", ["localhost.", "LOCALHOST", "postgres.example", "127.0.0.2"]
)
def test_local_exception_requires_exact_host(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    _refuses(
        f"postgresql://operator@{host}/database", monkeypatch, capsys, engine_factory
    )


def test_password_environment_remains_available(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("PGPASSWORD", "synthetic-password")
    monkeypatch.setenv("PGPASSFILE", "/synthetic/password-file")
    monkeypatch.setenv("FEWIA_RETENTION_DATABASE_URL", _LOCAL)
    assert retention_admin.main(_ARGS) == 0
    assert capsys.readouterr().err == ""
    assert engine_factory.call_args.args[0].password is None


@pytest.mark.parametrize("stage", ["engine", "service"])
def test_connection_failures_have_fixed_output(
    stage: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("FEWIA_RETENTION_DATABASE_URL", f"{_REMOTE}?{_TLS}")
    error = sa.exc.OperationalError(
        "private-dsn", {"password": "synthetic-password"}, OSError("private-ca-path")
    )
    if stage == "engine":
        engine_factory.side_effect = error
    else:
        monkeypatch.setattr(
            retention_admin, "OperatorRetention", MagicMock(side_effect=error)
        )
    assert retention_admin.main(_ARGS) == 2
    captured = capsys.readouterr()
    assert captured.out == _REFUSED
    assert captured.err == ""


def test_unknown_database_mode_refuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine_factory: MagicMock,
) -> None:
    monkeypatch.setenv("FEWIA_DATABASE_MODE", "unknown")
    _refuses(_LOCAL, monkeypatch, capsys, engine_factory)
