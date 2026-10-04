from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_PASSWORD = "test-marker:@/%?#[]+&='\"\\"


def _aws_env() -> dict[str, str]:
    return {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": "fewia-db.abc123.us-east-1.rds.amazonaws.com",
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_DATABASE_PASSWORD": _PASSWORD,
    }


def _run(source: str, environ: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", dedent(source)],
        cwd=_BACKEND,
        env={"PYTHONPATH": str(_BACKEND), **environ},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("mode", [None, "local"])
@pytest.mark.parametrize("legacy", [None, "sqlite:///legacy%25.db"])
def test_legacy_settings(mode: str | None, legacy: str | None) -> None:
    environ = {
        "EXPECTED": legacy or "postgresql+psycopg://fewia:fewia@localhost:5432/fewia",
    }
    if mode is not None:
        environ["FEWIA_DATABASE_MODE"] = mode
    if legacy is not None:
        environ["DATABASE_URL"] = legacy
    result = _run(
        """
        import os
        from app.config import Settings, settings
        assert settings.database_url == os.environ['EXPECTED']
        assert Settings().database_url == settings.database_url
        assert settings.model_dump() == {}
        assert 'database_url' not in repr(settings)
        """,
        environ,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("user", ["fewia_app", "fewia_admin"])
def test_cloud_settings_round_trip_and_redaction(user: str) -> None:
    environ = _aws_env()
    environ["FEWIA_DATABASE_USER"] = user
    result = _run(
        """
        import os
        from pydantic import ValidationError
        from sqlalchemy.engine import make_url
        from app.config import Settings, settings
        assert isinstance(settings.database_url, str)
        url = make_url(settings.database_url)
        assert url.password == os.environ['FEWIA_DATABASE_PASSWORD']
        assert url.host == os.environ['FEWIA_DATABASE_HOST']
        assert url.username == os.environ['FEWIA_DATABASE_USER']
        assert url.database == 'fewia' and url.port == 5432
        assert url.drivername == 'postgresql+psycopg'
        assert dict(url.query) == {
            'sslmode': 'verify-full',
            'sslrootcert': '/app/infra/rds/us-east-1-bundle.pem',
        }
        assert '%25' in settings.database_url
        assert settings.model_dump() == {}
        assert settings.model_dump_json() == '{}'
        assert 'database_url' not in repr(settings)
        try:
            Settings(database_url={'secret': 'test-marker'})
        except ValidationError as error:
            assert 'test-marker' not in str(error)
            assert 'input_value' not in str(error)
        else:
            raise AssertionError('Expected a validation error')
        """,
        environ,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("FEWIA_DATABASE_MODE", "test-marker"),
        ("FEWIA_DATABASE_HOST", "test-marker"),
        ("FEWIA_DATABASE_PASSWORD", "test-marker\n"),
        ("FEWIA_DATABASE_USER", ""),
        ("FEWIA_DATABASE_USER", None),
        ("DATABASE_URL", "test-marker"),
        ("FEWIA_DATABASE_MODE", "local"),
    ],
)
def test_invalid_cloud_settings_hide_context(field: str, value: str | None) -> None:
    environ = _aws_env()
    if value is None:
        del environ[field]
    else:
        environ[field] = value
    result = _run(
        """
        try:
            import app.config
        except ValueError as error:
            assert error.args == ('Cloud database configuration is invalid',)
            assert error.__cause__ is None and error.__context__ is None
            raise
        else:
            raise AssertionError('Expected invalid cloud configuration')
        """,
        environ,
    )
    assert result.returncode != 0
    assert result.stderr.endswith(
        "ValueError: Cloud database configuration is invalid\n"
    )
    assert result.stdout == ""
    assert "test-marker" not in result.stderr


def test_alembic_offline_percent_round_trip() -> None:
    result = _run(
        """
        from io import StringIO
        from unittest.mock import patch
        from alembic import command, context
        from alembic.config import Config
        from app.config import settings
        output = StringIO()
        config = Config('alembic.ini', output_buffer=output)
        with patch.object(context, 'configure', wraps=context.configure) as configure:
            command.upgrade(config, 'head', sql=True)
        assert config.get_main_option('sqlalchemy.url') == settings.database_url
        assert configure.call_args.kwargs['url'] == settings.database_url
        assert 'CREATE TABLE' in output.getvalue()
        assert 'test-marker' not in output.getvalue()
        """,
        _aws_env(),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "test-marker" not in result.stderr


def test_public_ca_bundle_matches_provenance() -> None:
    directory = _BACKEND.parent / "infra" / "rds"
    bundle = (directory / "us-east-1-bundle.pem").read_bytes()
    provenance = json.loads((directory / "provenance.json").read_text())
    assert bundle.count(b"-----BEGIN CERTIFICATE-----") == 3
    assert bundle.count(b"-----END CERTIFICATE-----") == 3
    assert b"PRIVATE KEY" not in bundle
    assert hashlib.sha256(bundle).hexdigest() == provenance["sha256"]
    assert len(bundle) == provenance["bytes"]
    assert provenance["certificate_count"] == 3
