"""Build configured grocery providers from settings."""

from typing import TypedDict

from app.agent.provider import LLMProvider
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    TokenFileResolver,
    read_secret_file,
)
from app.providers.bedrock import BedrockConverseProvider
from app.providers.instacart import InstacartDevelopmentProvider
from app.providers.plaid import PlaidSandboxProvider
from app.providers.spoonacular import SpoonacularEstimateProvider
from app.services.grocery_context import SpendingSource


class ProviderCapabilities(TypedDict):
    chat_configured: bool
    plaid_configured: bool
    instacart_configured: bool
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
        )
    except Exception:
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
    except Exception:
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def build_instacart(
    settings: GroceryProviderSettings,
) -> InstacartDevelopmentProvider | None:
    key_file = settings.instacart_key_file
    if key_file is None:
        return None
    secret = read_secret_file(key_file)
    provider: InstacartDevelopmentProvider | None = None
    try:
        provider = InstacartDevelopmentProvider(secret.get_secret_value())
    except Exception:
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def build_spoonacular(
    settings: GroceryProviderSettings,
) -> SpoonacularEstimateProvider | None:
    key_file = settings.spoonacular_key_file
    if key_file is None:
        return None
    secret = read_secret_file(key_file)
    provider: SpoonacularEstimateProvider | None = None
    try:
        provider = SpoonacularEstimateProvider(secret.get_secret_value())
    except Exception:
        pass
    if provider is None:
        raise ProviderConfigurationError()
    return provider


def capabilities(settings: GroceryProviderSettings) -> ProviderCapabilities:
    plaid_configured = (
        settings.plaid_client_id is not None
        and settings.plaid_secret_file is not None
        and settings.plaid_tokens_file is not None
    )
    return {
        "chat_configured": settings.bedrock_model_id is not None,
        "plaid_configured": plaid_configured,
        "instacart_configured": settings.instacart_key_file is not None,
        "spending_source": settings.spending_source,
    }
