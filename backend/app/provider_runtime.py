"""Build configured grocery providers from settings."""

from typing import TypedDict

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
from app.providers.plaid import PlaidSandboxProvider


class ProviderCapabilities(TypedDict):
    chat_configured: bool
    plaid_configured: bool
    spending_source: SpendingSource


def build_bedrock(settings: GroceryProviderSettings) -> LLMProvider | None:
    model_id = settings.bedrock_model_id
    if model_id is None:
        return None
    provider: LLMProvider | None = None
    try:
        provider = BedrockConverseProvider(
            model_id,
            region=settings.bedrock_region,
            profile_name=settings.aws_profile,
            prompt_cache=settings.bedrock_prompt_cache,
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


def build_kroger(settings: GroceryProviderSettings) -> KrogerClient | None:
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


def capabilities(settings: GroceryProviderSettings) -> ProviderCapabilities:
    plaid_configured = (
        settings.plaid_client_id is not None
        and settings.plaid_secret_file is not None
        and settings.plaid_tokens_file is not None
    )
    return {
        "chat_configured": settings.bedrock_model_id is not None,
        "plaid_configured": plaid_configured,
        "spending_source": settings.spending_source,
    }
