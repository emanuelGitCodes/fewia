"""Tests for grocery provider factories and capabilities."""

import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.provider_runtime import (
    build_bedrock,
    build_kroger,
    build_kroger_cipher,
    build_kroger_pairing_cipher,
    build_llm,
    build_plaid,
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
        prompt_cache: bool = False,
        guardrail: tuple[str, str] | None = None,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.profile_name = profile_name
        self.prompt_cache = prompt_cache
        self.guardrail = guardrail


class FakePlaid:
    def __init__(self, client_id: str, secret: str, token_resolver: object) -> None:
        self.client_id = client_id
        self.secret = secret
        self.token_resolver = token_resolver


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", FakeBedrock)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", FakePlaid)


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
    assert build_llm(settings) is None
    assert build_plaid(settings) is None
    assert capabilities(settings) == {
        "chat_configured": False,
        "plaid_configured": False,
        "spending_source": "manual",
        "kroger_mode": "off",
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
            prompt_cache: bool = False,
            guardrail: tuple[str, str] | None = None,
        ) -> None:
            calls.append(model_id)
            super().__init__(
                model_id,
                region=region,
                profile_name=profile_name,
                prompt_cache=prompt_cache,
                guardrail=guardrail,
            )

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
    assert defaulted.prompt_cache is False
    cached = build_bedrock(
        GroceryProviderSettings(
            bedrock_model_id=MODEL_MARKER, bedrock_prompt_cache=True
        )
    )
    assert isinstance(cached, FakeBedrock)
    assert cached.prompt_cache is True
    assert defaulted.guardrail is None
    guarded = build_bedrock(
        GroceryProviderSettings(
            bedrock_model_id=MODEL_MARKER,
            bedrock_guardrail_id="abc123def456",
            bedrock_guardrail_version="3",
        )
    )
    assert isinstance(guarded, FakeBedrock)
    assert guarded.guardrail == ("abc123def456", "3")


def test_build_bedrock_hides_constructor_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(
        model_id: str,
        region: str = "us-east-1",
        profile_name: str | None = None,
        prompt_cache: bool = False,
        guardrail: tuple[str, str] | None = None,
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


def test_capabilities_does_not_construct_or_claim_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("constructor MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", boom)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", boom)
    _forbid_reads(monkeypatch)
    settings = GroceryProviderSettings(
        spending_source="plaid_sandbox",
        bedrock_model_id=MODEL_MARKER,
        aws_profile=PROFILE_MARKER,
        plaid_client_id=CLIENT_MARKER,
        plaid_secret_file=Path("secret"),
        plaid_tokens_file=Path("tokens"),
    )
    caps = capabilities(settings)
    assert caps == {
        "chat_configured": True,
        "plaid_configured": True,
        "spending_source": "plaid_sandbox",
        "kroger_mode": "off",
    }
    blob = repr(caps)
    assert set(caps) == {
        "chat_configured",
        "plaid_configured",
        "spending_source",
        "kroger_mode",
    }
    assert "connected" not in blob
    assert PROFILE_MARKER not in blob
    assert MODEL_MARKER not in blob
    assert CLIENT_MARKER not in blob
    assert "secret" not in blob
    assert "tokens" not in blob
    assert "key" not in blob


@pytest.mark.parametrize("region", ["us", "global"])
def test_build_llm_selects_openai_without_bedrock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, region: str
) -> None:
    captured: list[tuple[Path, str]] = []
    sentinel = object()

    def openai(path: Path, *, region: str) -> object:
        captured.append((path, region))
        return sentinel

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Bedrock MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.OpenAIResponsesProvider", openai)
    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", forbid)
    _forbid_reads(monkeypatch)
    path = tmp_path / "openai-key"
    settings = GroceryProviderSettings.model_validate(
        {"openai_api_key_file": path, "openai_region": region}
    )
    assert build_llm(settings) is sentinel
    assert captured == [(path, region)]
    assert capabilities(settings)["chat_configured"] is True
    assert str(path) not in repr(capabilities(settings))


def test_build_llm_preserves_bedrock_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("OpenAI MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.OpenAIResponsesProvider", forbid)
    configured = GroceryProviderSettings(
        bedrock_model_id=MODEL_MARKER, bedrock_prompt_cache=True
    )
    provider = build_llm(configured)
    assert isinstance(provider, FakeBedrock)
    assert provider.model_id == MODEL_MARKER
    assert provider.prompt_cache is True


def test_openai_constructor_failure_is_generic_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError(SECRET_MARKER)

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Bedrock MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.OpenAIResponsesProvider", fail)
    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", forbid)
    path = tmp_path / "key"
    with pytest.raises(ProviderConfigurationError) as raised:
        build_llm(GroceryProviderSettings(openai_api_key_file=path))
    _static(raised.value, SECRET_MARKER, str(path))


def test_conflicting_constructed_settings_fail_before_provider_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Provider MUST NOT run")

    monkeypatch.setattr("app.provider_runtime.OpenAIResponsesProvider", forbid)
    monkeypatch.setattr("app.provider_runtime.BedrockConverseProvider", forbid)
    settings = GroceryProviderSettings.model_construct(
        bedrock_model_id=MODEL_MARKER, openai_api_key_file=Path("key")
    )
    with pytest.raises(ProviderConfigurationError):
        build_llm(settings)


def _live_pairing_settings(
    tmp_path: Path, key_file: Path | None
) -> GroceryProviderSettings:
    return GroceryProviderSettings(
        kroger_client_id_file=tmp_path / "unread-client-id",
        kroger_secret_file=tmp_path / "unread-client-secret",
        kroger_token_key_file=tmp_path / "unread-token-key",
        kroger_pairing_key_file=key_file,
    )


@pytest.mark.parametrize("permissions", [0o400, 0o600])
def test_build_kroger_pairing_cipher_loads_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permissions: int
) -> None:
    key = Fernet.generate_key()
    path = tmp_path / "pairing-key"
    path.write_bytes(key + b"\n")
    path.chmod(permissions)
    _forbid_reads(monkeypatch)
    settings = _live_pairing_settings(tmp_path, path)
    cipher = build_kroger_pairing_cipher(settings)
    assert isinstance(cipher, Fernet)
    payload = b"synthetic-pairing-payload"
    assert Fernet(key).decrypt(cipher.encrypt(payload)) == payload
    assert capabilities(settings)["kroger_mode"] == "live"
    assert str(path) not in repr(capabilities(settings))


@pytest.mark.parametrize(
    "mode",
    ["fixture", "fixture-with-credentials", "off", "client-only", "secret-only"],
)
@pytest.mark.parametrize("configured_key", [False, True])
def test_pairing_cipher_inactive_modes_do_not_access_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    configured_key: bool,
) -> None:
    values: dict[str, object] = {
        "kroger_mode": "fixture" if mode.startswith("fixture") else "live",
        "kroger_pairing_key_file": tmp_path / "unread-key" if configured_key else None,
    }
    if mode in ("fixture-with-credentials", "client-only"):
        values["kroger_client_id_file"] = tmp_path / "unread-client"
    if mode in ("fixture-with-credentials", "secret-only"):
        values["kroger_secret_file"] = tmp_path / "unread-secret"
    settings = GroceryProviderSettings.model_validate(values)

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Inactive pairing cipher MUST NOT access files")

    _forbid_reads(monkeypatch)
    with monkeypatch.context() as guard:
        guard.setattr("app.provider_runtime.os.open", forbid)
        guard.setattr(Path, "open", forbid)
        guard.setattr(Path, "stat", forbid)
        guard.setattr(Path, "lstat", forbid)
        cipher = build_kroger_pairing_cipher(settings)
    assert cipher is None


def test_fixture_factories_work_without_pairing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_reads(monkeypatch)
    settings = GroceryProviderSettings(kroger_mode="fixture")
    assert build_kroger(settings) is not None
    assert isinstance(build_kroger_cipher(settings), Fernet)
    assert build_kroger_pairing_cipher(settings) is None


@pytest.mark.parametrize("configured_key", [False, True])
def test_pairing_cipher_live_requires_existing_key(
    tmp_path: Path, configured_key: bool
) -> None:
    path = tmp_path / "missing-pairing-key"
    settings = _live_pairing_settings(tmp_path, path if configured_key else None)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(settings)
    _static(raised.value, str(path))


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b" \n",
        b"TEST_INVALID_FERNET_KEY",
        b"A" * 40,
        b"A" * 44,
        b"A" * 43 + b"!",
        b"\xff\xfe",
        b"\xc2\xa0" + b"A" * 43 + b"=",
        b"\x00" + b"A" * 43 + b"=",
        b"A" * 20 + b"\n" + b"A" * 23 + b"=",
        b"A" * 43 + b"=!",
    ],
    ids=[
        "empty",
        "blank",
        "invalid-key",
        "wrong-decoded-length",
        "missing-padding",
        "invalid-base64",
        "invalid-encoding",
        "non-ascii-whitespace",
        "nul",
        "embedded-newline",
        "trailing-junk",
    ],
)
def test_pairing_cipher_rejects_malformed_keys(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "pairing-key"
    path.write_bytes(payload)
    path.chmod(0o600)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path), "TEST_INVALID_FERNET_KEY", repr(payload))


@pytest.mark.parametrize("dangling", [False, True])
def test_pairing_cipher_rejects_symlinks(tmp_path: Path, dangling: bool) -> None:
    target = tmp_path / "target-key"
    if not dangling:
        target.write_bytes(Fernet.generate_key())
        target.chmod(0o600)
    path = tmp_path / "pairing-link"
    path.symlink_to(target)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path), str(target))


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_pairing_cipher_rejects_nonregular_files(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "nonregular-key"
    if kind == "directory":
        path.mkdir(mode=0o700)
    else:
        os.mkfifo(path, 0o600)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path))


@pytest.mark.parametrize("permissions", [0o640, 0o620, 0o604, 0o602, 0o644, 0o666])
def test_pairing_cipher_rejects_unsafe_modes_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permissions: int
) -> None:
    path = tmp_path / "unsafe-key"
    key = Fernet.generate_key()
    path.write_bytes(key)
    path.chmod(permissions)

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Unsafe pairing key MUST NOT be read")

    monkeypatch.setattr("app.provider_runtime.os.fdopen", forbid)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path), key.decode("ascii"))


@pytest.mark.parametrize("stale_size", [False, True])
def test_pairing_cipher_rejects_oversized_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stale_size: bool
) -> None:
    path = tmp_path / "oversized-key"
    key = Fernet.generate_key()
    path.write_bytes(b" " * 4096 + key)
    path.chmod(0o600)
    if stale_size:
        original_fstat = os.fstat

        def stale_fstat(descriptor: int) -> os.stat_result:
            fields = list(original_fstat(descriptor))
            fields[6] = len(key)
            return os.stat_result(fields)

        monkeypatch.setattr("app.provider_runtime.os.fstat", stale_fstat)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path), key.decode("ascii"))


def test_pairing_cipher_does_not_require_process_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mapped-uid-key"
    key = Fernet.generate_key()
    path.write_bytes(key)
    path.chmod(0o600)
    mapped_uid = path.stat().st_uid + 1

    def process_uid() -> int:
        return mapped_uid

    monkeypatch.setattr(os, "getuid", process_uid)
    monkeypatch.setattr(os, "geteuid", process_uid)
    cipher = build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    assert isinstance(cipher, Fernet)
    payload = b"synthetic-pairing-payload"
    assert Fernet(key).decrypt(cipher.encrypt(payload)) == payload


def test_pairing_cipher_file_access_errors_are_generic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "unreadable-key"

    def deny(*args: object, **kwargs: object) -> None:
        raise PermissionError(SECRET_MARKER)

    monkeypatch.setattr("app.provider_runtime.os.open", deny)
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, str(path), SECRET_MARKER)


def test_pairing_cipher_rejects_nul_path(tmp_path: Path) -> None:
    path = Path(str(tmp_path / "key") + "\x00NUL_PATH_SENTINEL")
    with pytest.raises(ProviderConfigurationError) as raised:
        build_kroger_pairing_cipher(_live_pairing_settings(tmp_path, path))
    _static(raised.value, "NUL_PATH_SENTINEL", "embedded null byte")
