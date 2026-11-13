"""Bind Kroger actions to owner generations without storing raw credentials.

Callers MUST commit before provider calls to release all database locks.
"""

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kroger_models import KrogerCustomerToken
from app.security_models import KrogerOwner, SecurityIntent
from app.services.security_admission import OwnerUnavailableError, lock_active_owner

PAIRING_TTL_SECONDS = 300
PROOF_TTL_SECONDS = 8 * 60 * 60
OAUTH_START_TTL_SECONDS = 300
OAUTH_STATE_TTL_SECONDS = 300
CART_TTL_SECONDS = 300
MAX_CART_TOKEN_LENGTH = 32768
TerminalState = Literal["succeeded", "failed", "uncertain"]
IntentKind = Literal[
    "pairing_ticket", "oauth_start", "oauth_state", "cart_confirmation"
]
_NONCE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


class SecurityIntentError(Exception):
    """Report invalid security input without its contents."""

    def __init__(self) -> None:
        super().__init__("Kroger action is invalid or expired.")


class CartOutcomeUnknown(SecurityIntentError):
    """Refuse another upstream call when an action has no terminal result."""

    def __init__(self) -> None:
        Exception.__init__(self, "Kroger cart outcome is unknown.")


class CartLine(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )
    upc: str = Field(min_length=8, max_length=14, pattern=r"^[0-9]{8,14}$")
    quantity: int = Field(ge=1, le=10)


class CartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    owner_id: int = Field(gt=0, le=9223372036854775807)
    pairing_generation: UUID
    connection_version: UUID
    plan_revision: UUID
    action_id: UUID
    items: list[CartLine] = Field(min_length=1, max_length=30)
    expires_at: int = Field(ge=0)


@dataclass(frozen=True)
class CartClaim:
    intent_id: UUID
    action_id: UUID
    plan_revision: UUID
    items: tuple[CartLine, ...]
    connection_version: UUID
    pairing_generation: UUID


@dataclass(frozen=True)
class CartOutcome:
    action_id: UUID
    state: TerminalState


def _seconds(now_seconds: int | None) -> int:
    value = int(time.time()) if now_seconds is None else now_seconds
    if type(value) is not int or not 0 <= value <= 253402271999:
        raise SecurityIntentError()
    return value


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def _expired(row: SecurityIntent, now_seconds: int) -> bool:
    expiry = row.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return expiry <= _at(now_seconds)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _nonce_digest(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 43
        or _NONCE.fullmatch(value) is None
    ):
        raise SecurityIntentError()
    return _digest(value)


def _token_digest(token: str) -> str:
    if (
        not isinstance(token, str)
        or not 1 <= len(token) <= MAX_CART_TOKEN_LENGTH
        or not token.isascii()
    ):
        raise SecurityIntentError()
    return _digest(token)


def _owner(session: Session, owner_id: int) -> KrogerOwner:
    if type(owner_id) is not int or not 0 < owner_id <= 9223372036854775807:
        raise SecurityIntentError()
    try:
        lock_active_owner(session, owner_id)
    except OwnerUnavailableError:
        raise SecurityIntentError() from None
    row = session.scalar(
        select(KrogerOwner)
        .where(KrogerOwner.user_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        row = KrogerOwner(user_id=owner_id, pairing_generation=uuid4())
        session.add(row)
        session.flush()
    return row


def _intent(
    session: Session, owner_id: int, kind: IntentKind, digest: str
) -> SecurityIntent:
    row = session.scalar(
        select(SecurityIntent)
        .where(
            SecurityIntent.user_id == owner_id,
            SecurityIntent.kind == kind,
            SecurityIntent.digest == digest,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or not secrets.compare_digest(row.digest, digest):
        raise SecurityIntentError()
    return row


def _bound(row: SecurityIntent, owner: KrogerOwner) -> bool:
    generation = row.details.get("pairing_generation")
    return isinstance(generation, str) and secrets.compare_digest(
        generation, str(owner.pairing_generation)
    )


def _issue_nonce(
    session: Session,
    owner: KrogerOwner,
    kind: IntentKind,
    ttl_seconds: int,
    now_seconds: int,
    *,
    purpose: Literal["pairing_ticket", "tab_proof"] | None = None,
) -> str:
    raw = secrets.token_urlsafe(32)
    details = {"pairing_generation": str(owner.pairing_generation)}
    if purpose is not None:
        details["purpose"] = purpose
    session.add(
        SecurityIntent(
            user_id=owner.user_id,
            kind=kind,
            digest=_digest(raw),
            details=details,
            state="pending",
            expires_at=_at(now_seconds + ttl_seconds),
        )
    )
    session.flush()
    return raw


def issue_pairing_ticket(
    session: Session, owner_id: int, *, now_seconds: int | None = None
) -> str:
    now = _seconds(now_seconds)
    return _issue_nonce(
        session,
        _owner(session, owner_id),
        "pairing_ticket",
        PAIRING_TTL_SECONDS,
        now,
        purpose="pairing_ticket",
    )


def redeem_pairing_ticket(
    session: Session, owner_id: int, ticket: str, *, now_seconds: int | None = None
) -> str:
    now, digest = _seconds(now_seconds), _nonce_digest(ticket)
    owner = _owner(session, owner_id)
    row = _intent(session, owner_id, "pairing_ticket", digest)
    if (
        row.details.get("purpose") != "pairing_ticket"
        or row.state != "pending"
        or _expired(row, now)
        or not _bound(row, owner)
    ):
        raise SecurityIntentError()
    row.state = "consumed"
    row.updated_at = _at(now)
    return _issue_nonce(
        session, owner, "pairing_ticket", PROOF_TTL_SECONDS, now, purpose="tab_proof"
    )


def validate_tab_proof(
    session: Session, owner_id: int, proof: str, *, now_seconds: int | None = None
) -> UUID:
    now, digest = _seconds(now_seconds), _nonce_digest(proof)
    owner = _owner(session, owner_id)
    row = _intent(session, owner_id, "pairing_ticket", digest)
    if (
        row.details.get("purpose") != "tab_proof"
        or row.state != "pending"
        or _expired(row, now)
        or not _bound(row, owner)
    ):
        raise SecurityIntentError()
    return owner.pairing_generation


def revoke_pairing(session: Session, owner_id: int) -> UUID:
    owner = _owner(session, owner_id)
    owner.pairing_generation = uuid4()
    owner.updated_at = _at(_seconds(None))
    session.flush()
    return owner.pairing_generation


def issue_oauth_start_ticket(
    session: Session, owner_id: int, *, now_seconds: int | None = None
) -> str:
    now = _seconds(now_seconds)
    return _issue_nonce(
        session, _owner(session, owner_id), "oauth_start", OAUTH_START_TTL_SECONDS, now
    )


def consume_oauth_start_ticket(
    session: Session, owner_id: int, ticket: str, *, now_seconds: int | None = None
) -> UUID:
    """Consume the start ticket once before the caller creates OAuth state."""
    now, digest = _seconds(now_seconds), _nonce_digest(ticket)
    owner = _owner(session, owner_id)
    row = _intent(session, owner_id, "oauth_start", digest)
    if row.state != "pending" or _expired(row, now) or not _bound(row, owner):
        raise SecurityIntentError()
    row.state = "consumed"
    row.updated_at = _at(now)
    session.flush()
    return owner.pairing_generation


def issue_oauth_state(
    session: Session, owner_id: int, *, now_seconds: int | None = None
) -> str:
    now = _seconds(now_seconds)
    return _issue_nonce(
        session, _owner(session, owner_id), "oauth_state", OAUTH_STATE_TTL_SECONDS, now
    )


def consume_oauth_state(
    session: Session, owner_id: int, state: str, *, now_seconds: int | None = None
) -> UUID:
    """Consume state once. Callers MUST commit before exchanging the OAuth code."""
    now, digest = _seconds(now_seconds), _nonce_digest(state)
    owner = _owner(session, owner_id)
    row = _intent(session, owner_id, "oauth_state", digest)
    if row.state != "pending" or _expired(row, now) or not _bound(row, owner):
        raise SecurityIntentError()
    row.state = "consumed"
    row.updated_at = _at(now)
    session.flush()
    return owner.pairing_generation


def _connection(session: Session, owner_id: int) -> UUID:
    row = session.scalar(
        select(KrogerCustomerToken)
        .where(KrogerCustomerToken.user_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise SecurityIntentError()
    return row.connection_version


def _canonical_hash(payload: CartPayload) -> str:
    canonical = json.dumps(
        {
            "plan_revision": str(payload.plan_revision),
            "items": sorted((line.upc, line.quantity) for line in payload.items),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def issue_cart_confirmation(
    session: Session,
    owner_id: int,
    cipher: Fernet,
    plan_revision: UUID,
    items: list[CartLine],
    *,
    now_seconds: int | None = None,
) -> str:
    now = _seconds(now_seconds)
    owner = _owner(session, owner_id)
    try:
        payload = CartPayload(
            owner_id=owner_id,
            pairing_generation=owner.pairing_generation,
            connection_version=_connection(session, owner_id),
            plan_revision=plan_revision,
            action_id=uuid4(),
            items=items,
            expires_at=now + CART_TTL_SECONDS,
        )
    except ValidationError:
        raise SecurityIntentError() from None
    token = cipher.encrypt_at_time(payload.model_dump_json().encode(), now).decode()
    session.add(
        SecurityIntent(
            user_id=owner_id,
            kind="cart_confirmation",
            digest=_token_digest(token),
            details={
                "action_id": str(payload.action_id),
                "input_sha256": _canonical_hash(payload),
                "pairing_generation": str(payload.pairing_generation),
                "connection_version": str(payload.connection_version),
            },
            state="pending",
            expires_at=_at(payload.expires_at),
        )
    )
    session.flush()
    return token


def _outcome(row: SecurityIntent) -> CartOutcome | None:
    if row.state not in ("succeeded", "failed", "uncertain"):
        return None
    action = row.details.get("action_id")
    if not isinstance(action, str) or len(action) != 36:
        raise SecurityIntentError()
    try:
        action_id = UUID(action)
    except ValueError:
        raise SecurityIntentError() from None
    if row.state == "succeeded":
        return CartOutcome(action_id, "succeeded")
    if row.state == "failed":
        return CartOutcome(action_id, "failed")
    return CartOutcome(action_id, "uncertain")


def _cart_intent(
    session: Session, owner_id: int, token: str
) -> tuple[KrogerOwner, SecurityIntent]:
    digest = _token_digest(token)
    owner = _owner(session, owner_id)
    row = _intent(session, owner_id, "cart_confirmation", digest)
    return owner, row


def get_cart_outcome(session: Session, owner_id: int, token: str) -> CartOutcome:
    _, row = _cart_intent(session, owner_id, token)
    outcome = _outcome(row)
    if outcome is None:
        raise CartOutcomeUnknown()
    return outcome


def claim_cart_confirmation(
    session: Session,
    owner_id: int,
    cipher: Fernet,
    token: str,
    *,
    now_seconds: int | None = None,
) -> CartClaim | CartOutcome:
    """Claim once. Callers MUST commit the claim before an upstream request."""
    now = _seconds(now_seconds)
    owner, row = _cart_intent(session, owner_id, token)
    outcome = _outcome(row)
    if outcome is not None:
        return outcome
    if row.state != "pending":
        raise CartOutcomeUnknown()
    if (
        not _bound(row, owner)
        or row.details.get("connection_version") != str(_connection(session, owner_id))
        or _expired(row, now)
    ):
        raise SecurityIntentError()
    try:
        raw = cipher.decrypt_at_time(token.encode("ascii"), CART_TTL_SECONDS, now)
        payload = CartPayload.model_validate_json(raw)
    except (InvalidToken, ValidationError, UnicodeError):
        raise SecurityIntentError() from None
    if (
        payload.owner_id != owner_id
        or payload.pairing_generation != owner.pairing_generation
        or str(payload.connection_version) != row.details.get("connection_version")
        or str(payload.action_id) != row.details.get("action_id")
        or payload.expires_at <= now
        or not secrets.compare_digest(
            _canonical_hash(payload), str(row.details.get("input_sha256", ""))
        )
    ):
        raise SecurityIntentError()
    row.state = "claimed"
    row.updated_at = _at(now)
    session.flush()
    return CartClaim(
        row.id,
        payload.action_id,
        payload.plan_revision,
        tuple(payload.items),
        payload.connection_version,
        payload.pairing_generation,
    )


def record_cart_outcome(
    session: Session,
    owner_id: int,
    intent_id: UUID,
    state: TerminalState,
) -> CartOutcome:
    if state not in ("succeeded", "failed", "uncertain"):
        raise SecurityIntentError()
    _owner(session, owner_id)
    row = session.scalar(
        select(SecurityIntent)
        .where(
            SecurityIntent.id == intent_id,
            SecurityIntent.user_id == owner_id,
            SecurityIntent.kind == "cart_confirmation",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise SecurityIntentError()
    outcome = _outcome(row)
    if outcome is not None:
        return outcome
    if row.state != "claimed":
        raise CartOutcomeUnknown()
    row.state = state
    row.updated_at = _at(_seconds(None))
    session.flush()
    outcome = _outcome(row)
    assert outcome is not None
    return outcome
