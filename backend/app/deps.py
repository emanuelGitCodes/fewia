"""FastAPI dependencies."""

import functools
import threading
from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.provider_runtime import build_kroger
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)
from app.providers.kroger import KrogerClient

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


_kroger_lock = threading.Lock()


@functools.cache
def _build_kroger_client() -> KrogerClient | None:
    try:
        return build_kroger(load_provider_settings())
    except ProviderConfigurationError:
        return None


def get_kroger_client() -> KrogerClient | None:
    """Return one process-wide Kroger client, or None."""
    with _kroger_lock:
        return _build_kroger_client()


get_kroger_client.cache_clear = _build_kroger_client.cache_clear  # type: ignore[attr-defined]
