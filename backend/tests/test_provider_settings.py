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
    load_kroger_credentials,
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
    assert settings.spending_source == "manual"
    assert settings.bedrock_model_id is None
    assert settings.bedrock_region == "us-east-1"
    assert settings.aws_profile is None
    assert settings.bedrock_prompt_cache is False
    assert settings.bedrock_guardrail_id is None
    assert settings.bedrock_guardrail_version is None
    assert settings.plaid_client_id is None
    assert settings.plaid_secret_file is None
    assert settings.plaid_tokens_file is None
    assert settings.usda_fdc_key_file is None
    assert settings.kroger_client_id_file is None
    assert settings.kroger_secret_file is None
    assert settings.kroger_environment == "certification"
    assert settings.kroger_token_key_file is None
    assert (
        settings.kroger_redirect_uri == "http://localhost:8010/grocery/kroger/callback"
    )
    assert settings.kroger_return_url == "http://127.0.0.1:5173/prototype"


def test_kroger_token_key_file_and_urls_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "token-key"
    key.write_text(f"  {SECRET_MARKER}\n", encoding="utf-8")
    monkeypatch.setenv("FEWIA_KROGER_TOKEN_KEY_FILE", f" {key} ")
    monkeypatch.setenv("FEWIA_KROGER_REDIRECT_URI", "https://app.test/cb")
    monkeypatch.setenv("FEWIA_KROGER_RETURN_URL", "http://app.test:5173/done")
    settings = load_provider_settings()
    assert settings.kroger_token_key_file == key
    assert settings.kroger_redirect_uri == "https://app.test/cb"
    assert settings.kroger_return_url == "http://app.test:5173/done"
    assert read_secret_file(key).get_secret_value() == SECRET_MARKER


@pytest.mark.parametrize(
    "value",
    [
        "http://app.test:5173/done?x=1",
        "http://app.test:5173/done?",
        "http://app.test:5173?kroger=connected",
    ],
)
def test_kroger_return_url_rejects_a_query_string(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("FEWIA_KROGER_RETURN_URL", value)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value, value)


def test_load_rejects_blank_kroger_token_key_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_KROGER_TOKEN_KEY_FILE", "   ")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value)


@pytest.mark.parametrize("name", ["REDIRECT_URI", "RETURN_URL"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "/relative/path",
        "localhost:8010/cb",
        "ftp://app.test/cb",
        "javascript:alert(1)",
        "http:///nohost",
        "http://app.test/cb#frag",
        "http://app.test/cb\n",
        " http://app.test/cb",
    ],
)
def test_kroger_urls_reject_unsafe_values(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(f"FEWIA_KROGER_{name}", value)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value, value or "unused-marker")


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False)])
def test_bedrock_prompt_cache_parses_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_PROMPT_CACHE", raw)
    assert load_provider_settings().bedrock_prompt_cache is expected


_GUARDRAIL_ARN = "arn:aws:bedrock:us-east-1:123456789012:guardrail/abc123def456"


@pytest.mark.parametrize(
    ("guardrail_id", "version"),
    [
        ("abc123def456", "1"),
        (_GUARDRAIL_ARN, "12"),
    ],
)
def test_guardrail_settings_parse_env(
    monkeypatch: pytest.MonkeyPatch, guardrail_id: str, version: str
) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_ID", guardrail_id)
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_VERSION", version)
    settings = load_provider_settings()
    assert settings.bedrock_guardrail_id == guardrail_id
    assert settings.bedrock_guardrail_version == version


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_guardrail_settings_mean_off(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_ID", blank)
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_VERSION", blank)
    settings = load_provider_settings()
    assert settings.bedrock_guardrail_id is None
    assert settings.bedrock_guardrail_version is None


def test_guardrail_settings_strip_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_ID", " abc123def456 ")
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_VERSION", " 3 ")
    settings = load_provider_settings()
    assert settings.bedrock_guardrail_id == "abc123def456"
    assert settings.bedrock_guardrail_version == "3"


@pytest.mark.parametrize(("guardrail_id", "version"), [("abc123def456", ""), ("", "1")])
def test_one_blank_guardrail_setting_fails_both_or_neither(
    monkeypatch: pytest.MonkeyPatch, guardrail_id: str, version: str
) -> None:
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_ID", guardrail_id)
    monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_VERSION", version)
    with pytest.raises(ProviderConfigurationError):
        load_provider_settings()


@pytest.mark.parametrize(
    ("guardrail_id", "version"),
    [
        ("abc123def456", None),
        (None, "1"),
        ("short", "1"),
        ("ABC123DEF456", "1"),
        ("abc123def4567", "1"),
        ("arn:aws:bedrock:us-east-1:123:guardrail/abc123def456", "1"),
        ("arn:aws:bedrock:us-east-1:123456789012:guardrail/abc", "1"),
        ("abc123def456", ""),
        ("abc123def456", "0"),
        ("abc123def456", "-1"),
        ("abc123def456", "01"),
        ("abc123def456", "draft"),
        ("abc123def456", "DRAFT"),
        ("abc123def456", "1.0"),
    ],
)
def test_guardrail_settings_reject_partial_or_malformed(
    monkeypatch: pytest.MonkeyPatch, guardrail_id: str | None, version: str | None
) -> None:
    if guardrail_id is not None:
        monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_ID", guardrail_id)
    if version is not None:
        monkeypatch.setenv("FEWIA_BEDROCK_GUARDRAIL_VERSION", version)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value, guardrail_id or "unused-marker")


def test_kroger_credentials_load_and_strip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = tmp_path / "kroger-id"
    secret = tmp_path / "kroger-secret"
    client_id.write_text(f"  {CLIENT_MARKER}\n", encoding="utf-8")
    secret.write_text(f"{SECRET_MARKER}  \n", encoding="utf-8")
    monkeypatch.setenv("FEWIA_KROGER_CLIENT_ID_FILE", f" {client_id} ")
    monkeypatch.setenv("FEWIA_KROGER_SECRET_FILE", str(secret))
    monkeypatch.setenv("FEWIA_KROGER_ENVIRONMENT", "production")
    settings = load_provider_settings()
    assert settings.kroger_client_id_file == client_id
    assert settings.kroger_environment == "production"
    loaded_id, loaded_secret = load_kroger_credentials(settings)
    assert loaded_id.get_secret_value() == CLIENT_MARKER
    assert loaded_secret.get_secret_value() == SECRET_MARKER


@pytest.mark.parametrize(
    "content",
    [b"  \n", b"bad\x01id", b"a" * 65537],
    ids=["empty", "control", "oversize"],
)
def test_kroger_credentials_reject_invalid_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    good.write_text("ok", encoding="utf-8")
    bad.write_bytes(content)
    monkeypatch.setenv("FEWIA_KROGER_CLIENT_ID_FILE", str(bad))
    monkeypatch.setenv("FEWIA_KROGER_SECRET_FILE", str(good))
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_kroger_credentials(load_provider_settings())
    _static(exc_info.value, str(bad))


def test_kroger_credentials_require_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = tmp_path / "good"
    good.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("FEWIA_KROGER_CLIENT_ID_FILE", str(good))
    with pytest.raises(ProviderConfigurationError):
        load_kroger_credentials(load_provider_settings())


def test_kroger_environment_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEWIA_KROGER_ENVIRONMENT", "staging")
    with pytest.raises(ProviderConfigurationError):
        load_provider_settings()


def test_reads_prefixed_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "plaid.secret"
    tokens = tmp_path / "plaid.tokens.json"
    usda_key = tmp_path / "usda.key"
    monkeypatch.setenv("FEWIA_SPENDING_SOURCE", "plaid_sandbox")
    monkeypatch.setenv("FEWIA_BEDROCK_MODEL_ID", "anthropic.model")
    monkeypatch.setenv("FEWIA_BEDROCK_REGION", "us-west-2")
    monkeypatch.setenv("FEWIA_AWS_PROFILE", "operator")
    monkeypatch.setenv("FEWIA_PLAID_CLIENT_ID", CLIENT_MARKER)
    monkeypatch.setenv("FEWIA_PLAID_SECRET_FILE", str(secret))
    monkeypatch.setenv("FEWIA_PLAID_TOKENS_FILE", str(tokens))
    monkeypatch.setenv("FEWIA_USDA_FDC_KEY_FILE", str(usda_key))
    settings = load_provider_settings()
    assert settings.spending_source == "plaid_sandbox"
    assert settings.bedrock_model_id == "anthropic.model"
    assert settings.bedrock_region == "us-west-2"
    assert settings.aws_profile == "operator"
    assert settings.plaid_client_id is not None
    assert settings.plaid_client_id.get_secret_value() == CLIENT_MARKER
    assert settings.plaid_secret_file == secret
    assert settings.plaid_tokens_file == tokens
    assert settings.usda_fdc_key_file == usda_key
    assert CLIENT_MARKER not in repr(settings)
    assert CLIENT_MARKER not in str(settings)


def test_unknown_file_variable_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FEWIA_RETIRED_KEY_FILE", str(tmp_path / "retired.key"))
    settings = load_provider_settings()
    assert settings.spending_source == "manual"
    assert not hasattr(settings, "retired_key_file")


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
    assert settings.spending_source == "manual"
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


def test_load_rejects_blank_usda_key_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEWIA_USDA_FDC_KEY_FILE", "   ")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings()
    _static(exc_info.value)


def test_settings_are_frozen() -> None:
    settings = GroceryProviderSettings()
    with pytest.raises(ValidationError):
        settings.spending_source = "plaid_sandbox"


def test_spending_source_default_is_manual_and_rejects_invalid() -> None:
    settings = GroceryProviderSettings()
    assert settings.spending_source == "manual"
    with pytest.raises(ValidationError):
        GroceryProviderSettings.model_validate({"spending_source": "live"})


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
