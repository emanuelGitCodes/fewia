"""FastAPI dependencies."""

import functools
import threading
from collections.abc import Iterator
from typing import Annotated

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import (
    AlbTokenVerifier,
    AuthConfigurationError,
    AuthenticationError,
    AuthKeyUnavailableError,
    AuthSettings,
    load_auth_settings,
)
from app.db import SessionLocal
from app.models import User
from app.provider_runtime import build_kroger, build_kroger_cipher
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)
from app.providers.kroger import KrogerClient
from app.security_models import KrogerOwner

PROVIDER_UNAVAILABLE_MESSAGE = "Provider configuration is invalid"
AUTH_UNAVAILABLE_MESSAGE = "Authentication service is unavailable."


def get_session() -> Iterator[Session]:
    """Yield a database session and close it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_auth_settings() -> AuthSettings:
    """Load trusted authentication settings or return a static HTTP 503."""
    try:
        return load_auth_settings()
    except AuthConfigurationError:
        raise HTTPException(
            status_code=503, detail="Authentication configuration is invalid."
        ) from None


@functools.lru_cache(maxsize=1)
def get_alb_verifier(settings: AuthSettings) -> AlbTokenVerifier:
    return AlbTokenVerifier(settings)


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    """Resolve one active user from the configured authentication mode."""
    try:
        if settings.auth_mode == "local_demo":
            user = session.scalar(
                select(User)
                .where(User.id == 1)
                .execution_options(populate_existing=True)
            )
            if user is None or user.status != "active":
                raise HTTPException(status_code=503, detail=AUTH_UNAVAILABLE_MESSAGE)
            return user

        identity = get_alb_verifier(settings).verify_headers(request.scope["headers"])
        statement = (
            select(User)
            .where(
                User.auth_issuer == identity.issuer,
                User.auth_subject == identity.subject,
            )
            .execution_options(populate_existing=True)
        )
        user = session.scalars(statement).one_or_none()
        changed = False
        if user is None:
            session.execute(
                text(
                    "INSERT INTO users (display_name, auth_issuer, auth_subject) "
                    "VALUES (:display_name, :auth_issuer, :auth_subject) "
                    "ON CONFLICT (auth_issuer, auth_subject) DO NOTHING"
                ),
                {
                    "display_name": "FEWIA user",
                    "auth_issuer": identity.issuer,
                    "auth_subject": identity.subject,
                },
            )
            user = session.scalars(statement).one_or_none()
            changed = True
        if user is None:
            raise HTTPException(status_code=503, detail=AUTH_UNAVAILABLE_MESSAGE)
        if user.status != "active":
            raise HTTPException(status_code=403, detail="Workspace access is disabled.")
        if session.get(KrogerOwner, user.id) is None:
            session.execute(
                text(
                    "INSERT INTO kroger_owners (user_id) VALUES (:user_id) "
                    "ON CONFLICT (user_id) DO NOTHING"
                ),
                {"user_id": user.id},
            )
            changed = True
        if changed:
            session.commit()
        return user
    except AuthenticationError:
        raise HTTPException(
            status_code=401, detail="Authentication is invalid."
        ) from None
    except AuthConfigurationError:
        raise HTTPException(
            status_code=503, detail="Authentication configuration is invalid."
        ) from None
    except AuthKeyUnavailableError:
        raise HTTPException(status_code=503, detail=AUTH_UNAVAILABLE_MESSAGE) from None
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=503, detail=AUTH_UNAVAILABLE_MESSAGE) from None


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


@functools.cache
def _build_kroger_cipher() -> Fernet | None:
    try:
        return build_kroger_cipher(load_provider_settings())
    except ProviderConfigurationError:
        return None


def get_kroger_cipher() -> Fernet | None:
    """Return the process-wide Kroger token cipher, or None."""
    with _kroger_lock:
        return _build_kroger_cipher()


get_kroger_cipher.cache_clear = _build_kroger_cipher.cache_clear  # type: ignore[attr-defined]
