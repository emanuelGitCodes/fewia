"""FastAPI dependencies."""

import functools
from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.provider_runtime import build_spoonacular
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)
from app.services.supermarket_overlay import IngredientCostEstimator

PROVIDER_UNAVAILABLE_MESSAGE = "Provider configuration is invalid"


def get_session() -> Iterator[Session]:
    """Yield a database session and close it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_provider_settings() -> GroceryProviderSettings:
    """Return grocery provider settings or a static HTTP 503."""
    settings: GroceryProviderSettings | None = None
    try:
        settings = load_provider_settings()
    except ProviderConfigurationError:
        pass
    if settings is None:
        raise HTTPException(status_code=503, detail=PROVIDER_UNAVAILABLE_MESSAGE)
    return settings


@functools.cache
def get_supermarket_estimator() -> IngredientCostEstimator | None:
    """Return one process-wide Spoonacular estimator, or None."""
    try:
        settings = load_provider_settings()
    except ProviderConfigurationError:
        return None
    if settings.spoonacular_key_file is None:
        return None
    try:
        return build_spoonacular(settings)
    except ProviderConfigurationError:
        return None
