"""Tests for grocery provider factories and capabilities."""

import json
import os
from pathlib import Path

import pytest

from app.provider_runtime import (
    build_bedrock,
    build_instacart,
    build_plaid,
    build_spoonacular,
    capabilities,
)
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    TokenFileResolver,
)

CLIENT_MARKER = "TEST_PLAID_CLIENT_MARKER"
SECRET_MARKER = "TEST_SECRET_FILE_MARKER"
TOKEN_MARKER = "TEST_ACCESS_TOKEN_MARKER"
KEY_MARKER = "TEST_INSTACART_KEY_MARKER"
SPOONACULAR_KEY_MARKER = "TEST_SPOONACULAR_KEY_MARKER"
MODEL_MARKER = "anthropic.model"
PROFILE_MARKER = "operator-profile"
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


class FakeBedrock:
    def __init__(
        self,
        model_id: str,
        region: str = "us-east-1",
        profile_name: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.profile_name = profile_name


class FakePlaid:
    def __init__(self, client_id: str, secret: str, token_resolver: object) -> None:
        self.client_id = client_id
        self.secret = secret
        self.token_resolver = token_resolver


class FakeInstacart:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


class FakeSpoonacular:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", FakeBedrock)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", FakePlaid)
    monkeypatch.setattr(
        "app.provider_runtime.InstacartDevelopmentProvider", FakeInstacart
    )
    monkeypatch.setattr(
        "app.provider_runtime.SpoonacularEstimateProvider", FakeSpoonacular
    )


def _forbid_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def tracking_read(path: Path) -> None:
        raise AssertionError(f"read_secret_file MUST NOT run for {path.name}")

    monkeypatch.setattr("app.provider_runtime.read_secret_file", tracking_read)


def test_unconfigured_defaults_have_zero_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    _forbid_reads(monkeypatch)
    settings = GroceryProviderSettings()
    assert build_bedrock(settings) is None
    assert build_plaid(settings) is None
    assert build_instacart(settings) is None
    assert build_spoonacular(settings) is None
    assert capabilities(settings) == {
        "chat_configured": False,
        "plaid_configured": False,
        "instacart_configured": False,
        "spending_source": "fixture",
    }


def test_profile_without_model_does_not_construct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Tracking(FakeBedrock):
        def __init__(
            self,
            model_id: str,
            region: str = "us-east-1",
            profile_name: str | None = None,
        ) -> None:
            calls.append(model_id)
            super().__init__(model_id, region=region, profile_name=profile_name)

    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", Tracking)
    settings = GroceryProviderSettings(aws_profile=PROFILE_MARKER)
    assert build_bedrock(settings) is None
    assert calls == []
    caps = capabilities(settings)
    assert caps["chat_configured"] is False
    assert PROFILE_MARKER not in repr(caps)


def test_build_bedrock_routes_model_region_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    configured = GroceryProviderSettings(
        bedrock_model_id=MODEL_MARKER,
        bedrock_region="us-west-2",
        aws_profile=PROFILE_MARKER,
    )
    provider = build_bedrock(configured)
    assert isinstance(provider, FakeBedrock)
    assert provider.model_id == MODEL_MARKER
    assert provider.region == "us-west-2"
    assert provider.profile_name == PROFILE_MARKER
    defaulted = build_bedrock(GroceryProviderSettings(bedrock_model_id=MODEL_MARKER))
    assert isinstance(defaulted, FakeBedrock)
    assert defaulted.region == "us-east-1"
    assert defaulted.profile_name is None


def test_build_bedrock_hides_constructor_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(
        model_id: str,
        region: str = "us-east-1",
        profile_name: str | None = None,
    ) -> None:
        raise RuntimeError(f"{model_id}:{profile_name}:aws-leak")

    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", boom)
    settings = GroceryProviderSettings(
        bedrock_model_id=MODEL_MARKER, aws_profile=PROFILE_MARKER
    )
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_bedrock(settings)
    _static(exc_info.value, MODEL_MARKER, PROFILE_MARKER, "aws-leak")


def test_partial_plaid_raises_without_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    _forbid_reads(monkeypatch)
    secret = tmp_path / "secret"
    tokens = tmp_path / "tokens.json"
    cases = (
        GroceryProviderSettings(plaid_client_id=CLIENT_MARKER),
        GroceryProviderSettings(plaid_secret_file=secret),
        GroceryProviderSettings(plaid_tokens_file=tokens),
        GroceryProviderSettings(
            plaid_client_id=CLIENT_MARKER, plaid_secret_file=secret
        ),
        GroceryProviderSettings(
            plaid_client_id=CLIENT_MARKER, plaid_tokens_file=tokens
        ),
        GroceryProviderSettings(plaid_secret_file=secret, plaid_tokens_file=tokens),
    )
    for settings in cases:
        with pytest.raises(ProviderConfigurationError) as exc_info:
            build_plaid(settings)
        _static(exc_info.value, CLIENT_MARKER, str(secret), str(tokens))
        assert capabilities(settings)["plaid_configured"] is False


def test_build_plaid_routes_client_secret_and_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    secret = tmp_path / "secret"
    tokens = tmp_path / "tokens.json"
    secret.write_text(f"  {SECRET_MARKER}\n", encoding="utf-8")
    tokens.write_text(json.dumps({REF: TOKEN_MARKER}), encoding="utf-8")
    settings = GroceryProviderSettings(
        plaid_client_id=CLIENT_MARKER,
        plaid_secret_file=secret,
        plaid_tokens_file=tokens,
    )
    provider = build_plaid(settings)
    assert isinstance(provider, FakePlaid)
    assert provider.client_id == CLIENT_MARKER
    assert provider.secret == SECRET_MARKER
    assert isinstance(provider.token_resolver, TokenFileResolver)
    assert provider.token_resolver(REF) == TOKEN_MARKER
    caps = capabilities(settings)
    assert caps["plaid_configured"] is True
    blob = repr(caps)
    assert CLIENT_MARKER not in blob
    assert SECRET_MARKER not in blob
    assert TOKEN_MARKER not in blob
    assert str(secret) not in blob
    assert str(tokens) not in blob


def test_build_plaid_hides_secret_on_constructor_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(client_id: str, secret: str, token_resolver: object) -> None:
        raise ValueError(secret)

    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", boom)
    secret = tmp_path / "secret"
    tokens = tmp_path / "tokens.json"
    secret.write_text(SECRET_MARKER, encoding="utf-8")
    tokens.write_text("{}", encoding="utf-8")
    settings = GroceryProviderSettings(
        plaid_client_id=CLIENT_MARKER,
        plaid_secret_file=secret,
        plaid_tokens_file=tokens,
    )
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_plaid(settings)
    _static(exc_info.value, CLIENT_MARKER, SECRET_MARKER)


def test_build_instacart_routes_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    key_file = tmp_path / "instacart.key"
    key_file.write_text(f"{KEY_MARKER}\n", encoding="utf-8")
    settings = GroceryProviderSettings(instacart_key_file=key_file)
    provider = build_instacart(settings)
    assert isinstance(provider, FakeInstacart)
    assert provider.api_key == KEY_MARKER
    caps = capabilities(settings)
    assert caps["instacart_configured"] is True
    assert KEY_MARKER not in repr(caps)
    assert str(key_file) not in repr(caps)


def test_build_instacart_hides_key_on_constructor_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(api_key: str) -> None:
        raise ValueError(api_key)

    monkeypatch.setattr("app.provider_runtime.InstacartDevelopmentProvider", boom)
    key_file = tmp_path / "instacart.key"
    key_file.write_text(KEY_MARKER, encoding="utf-8")
    settings = GroceryProviderSettings(instacart_key_file=key_file)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_instacart(settings)
    _static(exc_info.value, KEY_MARKER)


def test_build_instacart_missing_file_is_static(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    key_file = tmp_path / "missing.key"
    settings = GroceryProviderSettings(instacart_key_file=key_file)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_instacart(settings)
    _static(exc_info.value, str(key_file))


def test_build_spoonacular_routes_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    key_file = tmp_path / "spoonacular.key"
    key_file.write_text(f"{SPOONACULAR_KEY_MARKER}\n", encoding="utf-8")
    settings = GroceryProviderSettings(spoonacular_key_file=key_file)
    provider = build_spoonacular(settings)
    assert isinstance(provider, FakeSpoonacular)
    assert provider.api_key == SPOONACULAR_KEY_MARKER
    caps = capabilities(settings)
    assert "spoonacular_configured" not in caps
    assert SPOONACULAR_KEY_MARKER not in repr(caps)
    assert str(key_file) not in repr(caps)


def test_build_spoonacular_hides_key_on_constructor_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(api_key: str) -> None:
        raise ValueError(api_key)

    monkeypatch.setattr("app.provider_runtime.SpoonacularEstimateProvider", boom)
    key_file = tmp_path / "spoonacular.key"
    key_file.write_text(SPOONACULAR_KEY_MARKER, encoding="utf-8")
    settings = GroceryProviderSettings(spoonacular_key_file=key_file)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_spoonacular(settings)
    _static(exc_info.value, SPOONACULAR_KEY_MARKER)


def test_build_spoonacular_missing_file_is_static(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fakes(monkeypatch)
    key_file = tmp_path / "missing-spoonacular.key"
    settings = GroceryProviderSettings(spoonacular_key_file=key_file)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_spoonacular(settings)
    _static(exc_info.value, str(key_file))


def test_capabilities_does_not_construct_or_claim_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("constructor MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", boom)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", boom)
    monkeypatch.setattr("app.provider_runtime.InstacartDevelopmentProvider", boom)
    monkeypatch.setattr("app.provider_runtime.SpoonacularEstimateProvider", boom)
    _forbid_reads(monkeypatch)
    settings = GroceryProviderSettings(
        spending_source="plaid_sandbox",
        bedrock_model_id=MODEL_MARKER,
        aws_profile=PROFILE_MARKER,
        plaid_client_id=CLIENT_MARKER,
        plaid_secret_file=Path("secret"),
        plaid_tokens_file=Path("tokens"),
        instacart_key_file=Path("key"),
        spoonacular_key_file=Path("spoonacular"),
    )
    caps = capabilities(settings)
    assert caps == {
        "chat_configured": True,
        "plaid_configured": True,
        "instacart_configured": True,
        "spending_source": "plaid_sandbox",
    }
    blob = repr(caps)
    assert set(caps) == {
        "chat_configured",
        "plaid_configured",
        "instacart_configured",
        "spending_source",
    }
    assert "connected" not in blob
    assert PROFILE_MARKER not in blob
    assert MODEL_MARKER not in blob
    assert CLIENT_MARKER not in blob
    assert "secret" not in blob
    assert "tokens" not in blob
    assert "key" not in blob
    assert "spoonacular" not in blob
    assert "spoonacular_configured" not in caps
