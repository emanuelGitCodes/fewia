"""Build configured grocery providers from settings."""

import os
import re
import stat
from pathlib import Path
from typing import Literal, TypedDict

from cryptography.fernet import Fernet

from app.agent.provider import LLMProvider
from app.domain.budget import SpendingSource
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    TokenFileResolver,
    load_kroger_credentials,
    read_secret_file,
)
from app.providers.bedrock import BedrockConverseProvider
from app.providers.kroger import KrogerClient, kroger_base_url
from app.providers.kroger_fixture import build_fixture_cipher, build_fixture_client
from app.providers.openai_responses import OpenAIResponsesProvider
from app.providers.plaid import PlaidSandboxProvider

_MAX_PAIRING_KEY_BYTES = 4096


class ProviderCapabilities(TypedDict):
    chat_configured: bool
    plaid_configured: bool
    spending_source: SpendingSource
    kroger_mode: Literal["off", "live", "fixture"]


def build_llm(settings: GroceryProviderSettings) -> LLMProvider | None:
    key_file = settings.openai_api_key_file
    if key_file is None:
        return build_bedrock(settings)
    if settings.bedrock_model_id is not None:
        raise ProviderConfigurationError()
    provider: LLMProvider | None = None
    try:
        provider = OpenAIResponsesProvider(key_file, region=settings.openai_region)
    except Exception:  # noqa: BLE001
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def build_bedrock(settings: GroceryProviderSettings) -> LLMProvider | None:
    model_id = settings.bedrock_model_id
    if model_id is None:
        return None
    guardrail_id = settings.bedrock_guardrail_id
    guardrail_version = settings.bedrock_guardrail_version
    guardrail = (
        (guardrail_id, guardrail_version)
        if guardrail_id is not None and guardrail_version is not None
        else None
    )
    provider: LLMProvider | None = None
    try:
        provider = BedrockConverseProvider(
            model_id,
            region=settings.bedrock_region,
            profile_name=settings.aws_profile,
            prompt_cache=settings.bedrock_prompt_cache,
            guardrail=guardrail,
        )
    except Exception:  # noqa: BLE001
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def build_plaid(settings: GroceryProviderSettings) -> PlaidSandboxProvider | None:
    client_id = settings.plaid_client_id
    secret_file = settings.plaid_secret_file
    tokens_file = settings.plaid_tokens_file
    if client_id is None and secret_file is None and tokens_file is None:
        return None
    if client_id is None or secret_file is None or tokens_file is None:
        raise ProviderConfigurationError()
    secret = read_secret_file(secret_file)
    provider: PlaidSandboxProvider | None = None
    try:
        provider = PlaidSandboxProvider(
            client_id.get_secret_value(),
            secret.get_secret_value(),
            TokenFileResolver(tokens_file),
        )
    except Exception:  # noqa: BLE001
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def _fixture_mode(settings: GroceryProviderSettings) -> bool:
    """Return True for fixture mode; fail closed when a Kroger file is also set."""
    if settings.kroger_mode != "fixture":
        return False
    if (
        settings.kroger_client_id_file is not None
        or settings.kroger_secret_file is not None
        or settings.kroger_token_key_file is not None
    ):
        raise ProviderConfigurationError()
    return True


def build_kroger(settings: GroceryProviderSettings) -> KrogerClient | None:
    if _fixture_mode(settings):
        return build_fixture_client(settings.kroger_redirect_uri)
    if settings.kroger_client_id_file is None or settings.kroger_secret_file is None:
        return None
    client_id, secret = load_kroger_credentials(settings)
    client: KrogerClient | None = None
    try:
        client = KrogerClient(
            client_id.get_secret_value(),
            secret.get_secret_value(),
            base_url=kroger_base_url(settings.kroger_environment),
        )
    except ValueError:
        pass
    if client is None:
        raise ProviderConfigurationError()
    return client


def build_kroger_cipher(settings: GroceryProviderSettings) -> Fernet | None:
    if _fixture_mode(settings):
        return build_fixture_cipher()
    key_file = settings.kroger_token_key_file
    if key_file is None:
        return None
    key = read_secret_file(key_file)
    cipher: Fernet | None = None
    try:
        cipher = Fernet(key.get_secret_value())
    except ValueError:
        pass
    if cipher is None:
        raise ProviderConfigurationError()
    return cipher


def _read_private_pairing_cipher(path: Path) -> Fernet:
    cipher: Fernet | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode & 0o077
                or metadata.st_size > _MAX_PAIRING_KEY_BYTES
            ):
                raise ValueError
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read(_MAX_PAIRING_KEY_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(payload) > _MAX_PAIRING_KEY_BYTES:
            raise ValueError
        key = payload.decode("ascii").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{43}=", key) is None:
            raise ValueError
        cipher = Fernet(key)
    except (OSError, ValueError):
        pass
    if cipher is None:
        raise ProviderConfigurationError()
    return cipher


def build_kroger_pairing_cipher(settings: GroceryProviderSettings) -> Fernet | None:
    if _kroger_mode(settings) != "live":
        return None
    key_file = settings.kroger_pairing_key_file
    if key_file is None:
        raise ProviderConfigurationError()
    return _read_private_pairing_cipher(key_file)


def _kroger_mode(
    settings: GroceryProviderSettings,
) -> Literal["off", "live", "fixture"]:
    if settings.kroger_mode == "fixture":
        return "fixture"
    if (
        settings.kroger_client_id_file is not None
        and settings.kroger_secret_file is not None
    ):
        return "live"
    return "off"


def capabilities(settings: GroceryProviderSettings) -> ProviderCapabilities:
    plaid_configured = (
        settings.plaid_client_id is not None
        and settings.plaid_secret_file is not None
        and settings.plaid_tokens_file is not None
    )
    return {
        "chat_configured": (
            settings.bedrock_model_id is not None
            or settings.openai_api_key_file is not None
        ),
        "plaid_configured": plaid_configured,
        "spending_source": settings.spending_source,
        "kroger_mode": _kroger_mode(settings),
    }
