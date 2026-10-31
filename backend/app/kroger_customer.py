"""Encrypt and store the Kroger customer tokens; sign the OAuth state."""

import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.kroger_models import KrogerCustomerToken
from app.providers.kroger import (
    TOKEN_MARGIN_SECONDS,
    CustomerTokens,
    KrogerAuthRejected,
    KrogerClient,
)

STATE_COOKIE = "fewia_kroger_state"
COOKIE_PATH = "/grocery/kroger"
CALLBACK_PATH = f"{COOKIE_PATH}/callback"
STATE_TTL_SECONDS = 600
_now = time.time


def new_nonce() -> str:
    return secrets.token_urlsafe(32)


def make_state(cipher: Fernet, nonce: str) -> str:
    return cipher.encrypt(nonce.encode()).decode()


def state_matches(cipher: Fernet, state: str, cookie: str | None) -> bool:
    """Return True when the state decrypts, is fresh, and equals the cookie nonce."""
    if cookie is None:
        return False
    matched = False
    try:
        nonce = cipher.decrypt_at_time(state.encode(), STATE_TTL_SECONDS, int(_now()))
        matched = secrets.compare_digest(nonce, cookie.encode())
    except (InvalidToken, UnicodeError):
        pass
    return matched


def store_tokens(
    session: Session, user_id: int, cipher: Fernet, tokens: CustomerTokens
) -> None:
    """Replace the user's token row with freshly encrypted tokens."""
    now = datetime.now(UTC)
    access = cipher.encrypt(tokens.access_token.encode())
    refresh = cipher.encrypt(tokens.refresh_token.encode())
    expires_at = now + timedelta(seconds=tokens.expires_in)
    row = session.get(KrogerCustomerToken, user_id)
    if row is None:
        session.add(
            KrogerCustomerToken(
                user_id=user_id,
                access_token=access,
                refresh_token=refresh,
                access_expires_at=expires_at,
            )
        )
    else:
        row.access_token = access
        row.refresh_token = refresh
        row.access_expires_at = expires_at
        row.updated_at = now
    session.commit()


def is_connected(session: Session, user_id: int) -> bool:
    return session.get(KrogerCustomerToken, user_id) is not None


def delete_tokens(session: Session, user_id: int) -> None:
    """Forget the user's Kroger tokens. No error when there are none."""
    session.execute(
        delete(KrogerCustomerToken).where(KrogerCustomerToken.user_id == user_id)
    )
    session.commit()


def customer_access_token(
    session: Session, user_id: int, client: KrogerClient, cipher: Fernet
) -> str | None:
    """Return a usable access token, refreshing and storing a rotated pair first.

    The row stays locked until the commit. KrogerUnavailable propagates and
    leaves the stored tokens as they were. A rejected refresh token deletes the
    tokens and counts as not connected. A stored token that no longer decrypts
    (for example after a key change) is deleted and counts as not connected.
    """
    row = session.scalars(
        select(KrogerCustomerToken)
        .where(KrogerCustomerToken.user_id == user_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        return None
    expires_at = row.access_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    fresh = expires_at - timedelta(seconds=TOKEN_MARGIN_SECONDS) > datetime.now(UTC)
    try:
        secret = cipher.decrypt(
            row.access_token if fresh else row.refresh_token
        ).decode()
    except (InvalidToken, UnicodeError):
        delete_tokens(session, user_id)
        return None
    if fresh:
        session.commit()
        return secret
    try:
        tokens = client.refresh_customer(secret)
    except KrogerAuthRejected:
        delete_tokens(session, user_id)
        return None
    store_tokens(session, user_id, cipher, tokens)
    return tokens.access_token


class _RedactCallbackQuery(logging.Filter):
    """Keep the OAuth code and state out of the server access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (
            isinstance(args, tuple)
            and len(args) > 2
            and isinstance(args[2], str)
            and args[2].startswith(CALLBACK_PATH)
        ):
            record.args = (*args[:2], CALLBACK_PATH, *args[3:])
        return True


def redact_access_log() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _RedactCallbackQuery) for f in logger.filters):
        logger.addFilter(_RedactCallbackQuery())
