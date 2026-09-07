"""Tests for grocery provider settings and secret-file access."""

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    TokenFileResolver,
    load_provider_settings,
    read_secret_file,
)

CLIENT_MARKER = "TEST_PLAID_CLIENT_MARKER"
SECRET_MARKER = "TEST_SECRET_FILE_MARKER"
TOKEN_MARKER = "TEST_ACCESS_TOKEN_MARKER"
REF = "item-ref"


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


def _static(exc: BaseException, *markers: str) -> None:
    assert isinstance(exc, ProviderConfigurationError)
    assert str(exc) == "Provider configuration is invalid"
    assert exc.__cause__ is None
    assert exc.__context__ is None
    rendered = f"{exc!s}{exc!r}{exc.args!r}"
    for marker in markers:
        assert marker not in rendered


def test_defaults_from_env_prefix() -> None:
    settings = load_provider_settings()
    assert settings.spending_source == "fixture"
    assert settings.bedrock_model_id is None
    assert settings.bedrock_region == "us-east-1"
    assert settings.aws_profile is None
    assert settings.plaid_client_id is None
    assert settings.plaid_secret_file is None
    assert settings.plaid_tokens_file is None
    assert settings.instacart_key_file is None


def test_reads_prefixed_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "plaid.secret"
    tokens = tmp_path / "plaid.tokens.json"
    key = tmp_path / "instacart.key"
    monkeypatch.setenv("FEWIA_SPENDING_SOURCE", "plaid_sandbox")
    monkeypatch.setenv("FEWIA_BEDROCK_MODEL_ID", "anthropic.model")
    monkeypatch.setenv("FEWIA_BEDROCK_REGION", "us-west-2")
    monkeypatch.setenv("FEWIA_AWS_PROFILE", "operator")
    monkeypatch.setenv("FEWIA_PLAID_CLIENT_ID", CLIENT_MARKER)
    monkeypatch.setenv("FEWIA_PLAID_SECRET_FILE", str(secret))
    monkeypatch.setenv("FEWIA_PLAID_TOKENS_FILE", str(tokens))
    monkeypatch.setenv("FEWIA_INSTACART_KEY_FILE", str(key))
    settings = load_provider_settings()
    assert settings.spending_source == "plaid_sandbox"
    assert settings.bedrock_model_id == "anthropic.model"
    assert settings.bedrock_region == "us-west-2"
    assert settings.aws_profile == "operator"
    assert settings.plaid_client_id is not None
    assert settings.plaid_client_id.get_secret_value() == CLIENT_MARKER
    assert settings.plaid_secret_file == secret
    assert settings.plaid_tokens_file == tokens
    assert settings.instacart_key_file == key
    assert CLIENT_MARKER not in repr(settings)
    assert CLIENT_MARKER not in str(settings)


def test_ignores_dotenv_and_unprefixed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "FEWIA_SPENDING_SOURCE=plaid_sandbox\nFEWIA_AWS_PROFILE=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPENDING_SOURCE", "plaid_sandbox")
    monkeypatch.setenv("FEWIA_UNKNOWN", "ignore-me")
    settings = load_provider_settings()
    assert settings.spending_source == "fixture"
    assert settings.aws_profile is None


def test_load_rejects_invalid_values_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_SPENDING_SOURCE", "live_plaid")
    monkeypatch.setenv("FEWIA_BEDROCK_REGION", "eu-west-1")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value, "live_plaid", "eu-west-1")


def test_load_rejects_blank_and_overlong_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_MODEL_ID", "   ")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value)
    monkeypatch.setenv("FEWIA_BEDROCK_MODEL_ID", "m" * 257)
    with pytest.raises(ProviderConfigurationError) as overlong:
        load_provider_settings()
    _static(overlong.value, "m" * 257)


def test_load_rejects_blank_secret_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEWIA_PLAID_SECRET_FILE", "   ")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value)


def test_settings_are_frozen() -> None:
    settings = GroceryProviderSettings()
    with pytest.raises(ValidationError):
        settings.spending_source = "plaid_sandbox"


def test_read_secret_file_strips_and_redacts(tmp_path: Path) -> None:
    path = tmp_path / "secret.txt"
    path.write_text(f"  {SECRET_MARKER}  \n", encoding="utf-8")
    secret = read_secret_file(path)
    assert secret.get_secret_value() == SECRET_MARKER
    assert SECRET_MARKER not in repr(secret)
    assert SECRET_MARKER not in str(secret)


@pytest.mark.parametrize(
    ("writer", "marker"),
    [
        (lambda path: None, "missing-secret"),
        (lambda path: path.write_bytes(b"a" * 65537), "a" * 32),
        (lambda path: path.write_bytes(b"\xff\xfe"), "\xff"),
        (lambda path: path.write_text("   \n", encoding="utf-8"), None),
        (lambda path: path.write_text("bad\x00secret", encoding="utf-8"), "bad"),
    ],
)
def test_read_secret_file_rejects_invalid(
    tmp_path: Path,
    writer: Callable[[Path], object],
    marker: str | None,
) -> None:
    path = tmp_path / "secret.txt"
    writer(path)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        read_secret_file(path)
    markers = (str(path),) if marker is None else (marker, str(path))
    _static(exc_info.value, *markers)


def test_token_resolver_returns_exact_known_key(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(
        json.dumps({"other-ref": "other-token", REF: TOKEN_MARKER}, indent=2),
        encoding="utf-8",
    )
    resolver = TokenFileResolver(path)
    assert resolver(REF) == TOKEN_MARKER
    path.write_text(json.dumps({REF: "rotated-token"}), encoding="utf-8")
    assert resolver(REF) == "rotated-token"


def test_token_resolver_ignores_sibling_files(tmp_path: Path) -> None:
    sibling = tmp_path / "tokens.json"
    sibling.write_text(json.dumps({REF: TOKEN_MARKER}), encoding="utf-8")
    missing = tmp_path / "operator-tokens.json"
    with pytest.raises(ProviderConfigurationError) as exc_info:
        TokenFileResolver(missing)(REF)
    _static(exc_info.value, TOKEN_MARKER)


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        json.dumps({REF: 1}),
        json.dumps({REF: {"token": TOKEN_MARKER}}),
        json.dumps({REF: "   "}),
        json.dumps({REF: "tok\x07en"}),
        json.dumps({"": TOKEN_MARKER}),
    ],
)
def test_token_resolver_rejects_invalid_json(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        TokenFileResolver(path)(REF)
    _static(exc_info.value, TOKEN_MARKER, "tok", payload)


def test_token_resolver_rejects_unknown_and_wrong_type_ref(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({REF: TOKEN_MARKER}), encoding="utf-8")
    resolver = TokenFileResolver(path)
    with pytest.raises(ProviderConfigurationError) as missing:
        resolver("other-ref")
    _static(missing.value, TOKEN_MARKER, "other-ref")
    with pytest.raises(ProviderConfigurationError) as wrong_type:
        resolver(1)  # type: ignore[arg-type]
    _static(wrong_type.value, TOKEN_MARKER)


def test_token_file_oversize_and_invalid_encoding(tmp_path: Path) -> None:
    oversize = tmp_path / "oversize.json"
    oversize.write_bytes(b"{" + b"a" * 65536 + b"}")
    with pytest.raises(ProviderConfigurationError) as too_big:
        TokenFileResolver(oversize)(REF)
    _static(too_big.value)
    encoded = tmp_path / "bad.json"
    encoded.write_bytes(b"\xff\xfe{}")
    with pytest.raises(ProviderConfigurationError) as bad_encoding:
        TokenFileResolver(encoded)(REF)
    _static(bad_encoding.value)


def test_token_resolver_rejects_deeply_nested_json(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    nested = "[" * 20000 + "]" * 20000
    path.write_text(nested, encoding="utf-8")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        TokenFileResolver(path)(REF)
    _static(exc_info.value, TOKEN_MARKER, nested[:32], "RecursionError")


def test_secret_and_token_paths_reject_nul(tmp_path: Path) -> None:
    marker = "NUL_PATH_SENTINEL"
    nul_path = Path(str(tmp_path / "secret.txt") + "\x00" + marker)
    with pytest.raises(ProviderConfigurationError) as secret:
        read_secret_file(nul_path)
    _static(secret.value, marker, "embedded null byte", "ValueError")
    with pytest.raises(ProviderConfigurationError) as tokens:
        TokenFileResolver(nul_path)(REF)
    _static(tokens.value, marker, TOKEN_MARKER, "embedded null byte", "ValueError")
