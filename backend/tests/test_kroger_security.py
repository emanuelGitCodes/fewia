"""Exercise security intents with synthetic inputs and an in-memory database."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import ORMExecuteState, Session

from app.kroger_customer import store_tokens
from app.models import User
from app.providers.kroger import CustomerTokens
from app.security_models import KrogerOwner, SecurityIntent
from app.services import kroger_security
from app.services.kroger_security import (
    CART_TTL_SECONDS,
    OAUTH_START_TTL_SECONDS,
    OAUTH_STATE_TTL_SECONDS,
    PAIRING_TTL_SECONDS,
    PROOF_TTL_SECONDS,
    CartClaim,
    CartLine,
    CartOutcome,
    CartOutcomeUnknown,
    SecurityIntentError,
    TerminalState,
    claim_cart_confirmation,
    consume_oauth_start_ticket,
    consume_oauth_state,
    get_cart_outcome,
    issue_cart_confirmation,
    issue_oauth_start_ticket,
    issue_oauth_state,
    issue_pairing_ticket,
    record_cart_outcome,
    redeem_pairing_ticket,
    revoke_pairing,
    validate_tab_proof,
)
from app.services.security_admission import OwnerUnavailableError

NOW_SECONDS = 1800000000
OWNER_ID = 101
OTHER_OWNER_ID = 102


@pytest.fixture(autouse=True)
def owners(seed_user: UserSeeder) -> None:
    seed_user(OWNER_ID)
    seed_user(OTHER_OWNER_ID)


def _ticket(session: Session) -> str:
    return issue_pairing_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)


def _proof(session: Session) -> str:
    return redeem_pairing_ticket(
        session, OWNER_ID, _ticket(session), now_seconds=NOW_SECONDS
    )


def _cart(session: Session, cipher: Fernet) -> str:
    store_tokens(
        session, OWNER_ID, cipher, CustomerTokens("synthetic-a", "synthetic-r", 1800)
    )
    return issue_cart_confirmation(
        session,
        OWNER_ID,
        cipher,
        uuid4(),
        [CartLine(upc="000000000001", quantity=2)],
        now_seconds=NOW_SECONDS,
    )


def test_ticket_is_one_use_and_stores_only_digests(session: Session) -> None:
    ticket = _ticket(session)
    proof = redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    assert ticket != proof
    generation = validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    owner = session.get(KrogerOwner, OWNER_ID)
    assert owner is not None
    assert generation == owner.pairing_generation
    rows = list(session.scalars(select(SecurityIntent)))
    assert {row.kind for row in rows} == {"pairing_ticket"}
    assert {row.details["purpose"] for row in rows} == {"pairing_ticket", "tab_proof"}
    assert {row.digest for row in rows} == {
        hashlib.sha256(value.encode()).hexdigest() for value in (ticket, proof)
    }
    for row in rows:
        purpose = "pairing_ticket" if row.state == "consumed" else "tab_proof"
        assert row.details == {
            "pairing_generation": str(generation),
            "purpose": purpose,
        }
        assert ticket not in json.dumps(row.details)
        assert proof not in json.dumps(row.details)
    with pytest.raises(SecurityIntentError):
        redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)


def test_pairing_tickets_and_proofs_have_separate_purposes(session: Session) -> None:
    ticket = _ticket(session)
    with pytest.raises(SecurityIntentError):
        validate_tab_proof(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    proof = redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        redeem_pairing_ticket(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    assert validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)


@pytest.mark.parametrize("proof", [False, True])
@pytest.mark.parametrize("purpose", [None, "unexpected"])
def test_pairing_rejects_missing_or_wrong_purpose(
    session: Session, proof: bool, purpose: str | None
) -> None:
    nonce = _proof(session) if proof else _ticket(session)
    row = session.scalar(
        select(SecurityIntent).where(
            SecurityIntent.digest == hashlib.sha256(nonce.encode()).hexdigest()
        )
    )
    assert row is not None
    details = dict(row.details)
    details.pop("purpose")
    if purpose is not None:
        details["purpose"] = purpose
    row.details = details
    session.flush()
    helper = validate_tab_proof if proof else redeem_pairing_ticket
    with pytest.raises(SecurityIntentError):
        helper(session, OWNER_ID, nonce, now_seconds=NOW_SECONDS)
    assert row.state == "pending"


def test_ticket_foreign_owner_does_not_consume_ticket(session: Session) -> None:
    ticket = _ticket(session)
    with pytest.raises(SecurityIntentError):
        redeem_pairing_ticket(session, OTHER_OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    assert redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)


@pytest.mark.parametrize("offset_seconds", [PAIRING_TTL_SECONDS, 301])
def test_ticket_expires(session: Session, offset_seconds: int) -> None:
    ticket = _ticket(session)
    with pytest.raises(SecurityIntentError):
        redeem_pairing_ticket(
            session, OWNER_ID, ticket, now_seconds=NOW_SECONDS + offset_seconds
        )


def test_revocation_invalidates_tickets_and_proofs(session: Session) -> None:
    ticket, proof = _ticket(session), _proof(session)
    original = validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    assert revoke_pairing(session, OWNER_ID) != original
    with pytest.raises(SecurityIntentError):
        redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)


def test_proof_owner_scope_expiry_and_reuse(session: Session) -> None:
    proof = _proof(session)
    first = validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    again = validate_tab_proof(
        session, OWNER_ID, proof, now_seconds=NOW_SECONDS + PROOF_TTL_SECONDS - 1
    )
    assert again == first
    with pytest.raises(SecurityIntentError):
        validate_tab_proof(session, OTHER_OWNER_ID, proof, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        validate_tab_proof(
            session, OWNER_ID, proof, now_seconds=NOW_SECONDS + PROOF_TTL_SECONDS
        )


@pytest.mark.parametrize("value", ["", "x", "é" * 43, "!" * 43, "A" * 100000])
def test_nonce_helpers_reject_malformed_values(session: Session, value: str) -> None:
    for helper in (
        redeem_pairing_ticket,
        validate_tab_proof,
        consume_oauth_start_ticket,
        consume_oauth_state,
    ):
        with pytest.raises(SecurityIntentError, match="invalid or expired"):
            helper(session, OWNER_ID, value, now_seconds=NOW_SECONDS)


def test_oauth_start_ticket_is_owner_bound_and_one_use(session: Session) -> None:
    ticket = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        consume_oauth_start_ticket(
            session, OTHER_OWNER_ID, ticket, now_seconds=NOW_SECONDS
        )
    generation = consume_oauth_start_ticket(
        session,
        OWNER_ID,
        ticket,
        now_seconds=NOW_SECONDS + OAUTH_START_TTL_SECONDS - 1,
    )
    owner = session.get(KrogerOwner, OWNER_ID)
    assert owner is not None
    assert generation == owner.pairing_generation
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    assert row.kind == "oauth_start"
    assert row.state == "consumed"
    assert row.digest == hashlib.sha256(ticket.encode()).hexdigest()
    assert row.details == {"pairing_generation": str(generation)}
    with pytest.raises(SecurityIntentError):
        consume_oauth_start_ticket(
            session,
            OWNER_ID,
            ticket,
            now_seconds=NOW_SECONDS + OAUTH_START_TTL_SECONDS - 1,
        )


@pytest.mark.parametrize("offset_seconds", [OAUTH_START_TTL_SECONDS, 301])
def test_oauth_start_ticket_expires(session: Session, offset_seconds: int) -> None:
    ticket = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        consume_oauth_start_ticket(
            session, OWNER_ID, ticket, now_seconds=NOW_SECONDS + offset_seconds
        )
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    assert row.state == "pending"


def test_oauth_start_ticket_rejects_revoked_generation(session: Session) -> None:
    ticket = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    revoke_pairing(session, OWNER_ID)
    with pytest.raises(SecurityIntentError):
        consume_oauth_start_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    fresh = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    generation = consume_oauth_start_ticket(
        session, OWNER_ID, fresh, now_seconds=NOW_SECONDS
    )
    owner = session.get(KrogerOwner, OWNER_ID)
    assert owner is not None
    assert generation == owner.pairing_generation


def test_oauth_start_is_separate_from_pairing_and_state(session: Session) -> None:
    ticket, proof = _ticket(session), _proof(session)
    state = issue_oauth_state(session, OWNER_ID, now_seconds=NOW_SECONDS)
    start = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    for nonce in (ticket, proof, state):
        with pytest.raises(SecurityIntentError):
            consume_oauth_start_ticket(
                session, OWNER_ID, nonce, now_seconds=NOW_SECONDS
            )
    for nonce in (ticket, proof, start):
        with pytest.raises(SecurityIntentError):
            consume_oauth_state(session, OWNER_ID, nonce, now_seconds=NOW_SECONDS)
    for helper in (redeem_pairing_ticket, validate_tab_proof):
        with pytest.raises(SecurityIntentError):
            helper(session, OWNER_ID, start, now_seconds=NOW_SECONDS)
    assert redeem_pairing_ticket(session, OWNER_ID, ticket, now_seconds=NOW_SECONDS)
    assert validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    consume_oauth_start_ticket(session, OWNER_ID, start, now_seconds=NOW_SECONDS)
    consume_oauth_state(session, OWNER_ID, state, now_seconds=NOW_SECONDS)


def test_oauth_state_is_owner_bound_and_one_use(session: Session) -> None:
    state = issue_oauth_state(session, OWNER_ID, now_seconds=NOW_SECONDS)
    with pytest.raises(SecurityIntentError):
        consume_oauth_state(session, OTHER_OWNER_ID, state, now_seconds=NOW_SECONDS)
    generation = consume_oauth_state(session, OWNER_ID, state, now_seconds=NOW_SECONDS)
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    assert row.kind == "oauth_state"
    assert row.state == "consumed"
    assert row.digest == hashlib.sha256(state.encode()).hexdigest()
    assert row.details == {"pairing_generation": str(generation)}
    with pytest.raises(SecurityIntentError):
        consume_oauth_state(session, OWNER_ID, state, now_seconds=NOW_SECONDS)


@pytest.mark.parametrize("revoke", [False, True])
def test_oauth_state_rejects_expiry_or_revocation(
    session: Session, revoke: bool
) -> None:
    state = issue_oauth_state(session, OWNER_ID, now_seconds=NOW_SECONDS)
    if revoke:
        revoke_pairing(session, OWNER_ID)
    now = NOW_SECONDS if revoke else NOW_SECONDS + OAUTH_STATE_TTL_SECONDS
    with pytest.raises(SecurityIntentError):
        consume_oauth_state(session, OWNER_ID, state, now_seconds=now)


def test_cart_token_contains_only_bounded_claims(session: Session) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    payload = json.loads(cipher.decrypt_at_time(token.encode(), 300, NOW_SECONDS))
    assert set(payload) == {
        "owner_id",
        "pairing_generation",
        "connection_version",
        "plan_revision",
        "action_id",
        "items",
        "expires_at",
    }
    assert payload["items"] == [{"upc": "000000000001", "quantity": 2}]
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    assert set(row.details) == {
        "action_id",
        "input_sha256",
        "pairing_generation",
        "connection_version",
    }
    assert row.digest == hashlib.sha256(token.encode()).hexdigest()
    persisted = json.dumps(row.details)
    assert "000000000001" not in persisted
    assert token not in persisted
    assert len(str(row.details["input_sha256"])) == 64


@pytest.mark.parametrize(
    "change", ["signature", "expiry", "owner", "generation", "connection"]
)
def test_cart_rejects_invalid_claims(session: Session, change: str) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    now, owner_id = NOW_SECONDS, OWNER_ID
    if change == "signature":
        cipher = Fernet(Fernet.generate_key())
    elif change == "expiry":
        now += CART_TTL_SECONDS
    elif change == "owner":
        owner_id = OTHER_OWNER_ID
    elif change == "generation":
        revoke_pairing(session, OWNER_ID)
    else:
        store_tokens(
            session,
            OWNER_ID,
            cipher,
            CustomerTokens("replacement", "replacement-r", 1800),
        )
    with pytest.raises(SecurityIntentError):
        claim_cart_confirmation(session, owner_id, cipher, token, now_seconds=now)


@pytest.mark.parametrize("value", ["", "é", "not-signed", "A" * 40000])
def test_cart_rejects_malformed_tokens(session: Session, value: str) -> None:
    with pytest.raises(SecurityIntentError):
        claim_cart_confirmation(
            session,
            OWNER_ID,
            Fernet(Fernet.generate_key()),
            value,
            now_seconds=NOW_SECONDS,
        )


def test_cart_token_tampering_is_rejected(session: Session) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    replacement = "A" if token[50] != "A" else "B"
    tampered = token[:50] + replacement + token[51:]
    with pytest.raises(SecurityIntentError):
        claim_cart_confirmation(
            session, OWNER_ID, cipher, tampered, now_seconds=NOW_SECONDS
        )


def test_cart_signature_expiry_applies_even_with_a_later_database_expiry(
    session: Session,
) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    row.expires_at += timedelta(seconds=CART_TTL_SECONDS)
    session.flush()
    with pytest.raises(SecurityIntentError):
        claim_cart_confirmation(
            session,
            OWNER_ID,
            cipher,
            token,
            now_seconds=NOW_SECONDS + CART_TTL_SECONDS + 1,
        )


@pytest.mark.parametrize("state", ["succeeded", "failed", "uncertain"])
def test_terminal_cart_replay_never_calls_provider_twice(
    session: Session, state: TerminalState
) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    calls = 0

    def submit(now_seconds: int) -> CartOutcome:
        nonlocal calls
        result = claim_cart_confirmation(
            session, OWNER_ID, cipher, token, now_seconds=now_seconds
        )
        if isinstance(result, CartOutcome):
            return result
        calls += 1
        assert result.items == (CartLine(upc="000000000001", quantity=2),)
        return record_cart_outcome(session, OWNER_ID, result.intent_id, state)

    first = submit(NOW_SECONDS)
    assert first.state == state
    assert submit(NOW_SECONDS) == first
    assert submit(NOW_SECONDS + CART_TTL_SECONDS + 1) == first
    assert get_cart_outcome(session, OWNER_ID, token) == first
    revoke_pairing(session, OWNER_ID)
    store_tokens(
        session, OWNER_ID, cipher, CustomerTokens("replacement", "replacement-r", 1800)
    )
    assert submit(NOW_SECONDS) == first
    assert get_cart_outcome(session, OWNER_ID, token) == first
    assert calls == 1
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    assert record_cart_outcome(session, OWNER_ID, row.id, "succeeded") == first


def test_claimed_cart_replay_stays_unknown(session: Session) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    with pytest.raises(CartOutcomeUnknown):
        get_cart_outcome(session, OWNER_ID, token)
    result = claim_cart_confirmation(
        session, OWNER_ID, cipher, token, now_seconds=NOW_SECONDS
    )
    assert isinstance(result, CartClaim)
    payload = json.loads(cipher.decrypt_at_time(token.encode(), 300, NOW_SECONDS))
    assert str(result.connection_version) == payload["connection_version"]
    assert str(result.pairing_generation) == payload["pairing_generation"]
    for now in (NOW_SECONDS, NOW_SECONDS + CART_TTL_SECONDS + 1):
        with pytest.raises(CartOutcomeUnknown):
            claim_cart_confirmation(session, OWNER_ID, cipher, token, now_seconds=now)
    with pytest.raises(CartOutcomeUnknown):
        get_cart_outcome(session, OWNER_ID, token)


def test_cart_outcomes_reject_foreign_owners_and_unclaimed_actions(
    session: Session,
) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    row = session.scalar(select(SecurityIntent))
    assert row is not None
    with pytest.raises(CartOutcomeUnknown):
        record_cart_outcome(session, OWNER_ID, row.id, "succeeded")
    claim = claim_cart_confirmation(
        session, OWNER_ID, cipher, token, now_seconds=NOW_SECONDS
    )
    assert isinstance(claim, CartClaim)
    with pytest.raises(SecurityIntentError):
        record_cart_outcome(session, OTHER_OWNER_ID, claim.intent_id, "succeeded")
    record_cart_outcome(session, OWNER_ID, claim.intent_id, "uncertain")
    with pytest.raises(SecurityIntentError):
        get_cart_outcome(session, OTHER_OWNER_ID, token)


@pytest.mark.parametrize("quantity", [-1, 0, 11, 99, 100, True, 1.0, "1"])
def test_cart_quantity_is_a_bounded_integer(quantity: object) -> None:
    with pytest.raises(ValidationError):
        CartLine(upc="000000000001", quantity=quantity)


@pytest.mark.parametrize(
    "upc",
    [
        "",
        "1",
        "1" * 7,
        "1" * 15,
        "synthetic product name",
        "１２３４５６７８",
        "12345678\n",
    ],
)
def test_cart_upc_is_bounded(upc: str) -> None:
    with pytest.raises(ValidationError):
        CartLine(upc=upc, quantity=1)


@pytest.mark.parametrize("count", [0, 31, 100, 101])
def test_cart_item_count_is_bounded(session: Session, count: int) -> None:
    cipher = Fernet(Fernet.generate_key())
    store_tokens(
        session, OWNER_ID, cipher, CustomerTokens("synthetic-a", "synthetic-r", 1800)
    )
    with pytest.raises(SecurityIntentError, match="invalid or expired"):
        issue_cart_confirmation(
            session,
            OWNER_ID,
            cipher,
            uuid4(),
            [CartLine(upc="000000000001", quantity=1)] * count,
            now_seconds=NOW_SECONDS,
        )
    assert list(session.scalars(select(SecurityIntent))) == []


@pytest.mark.parametrize("upc_length", list(range(8, 15)))
@pytest.mark.parametrize("quantity", [1, 10])
@pytest.mark.parametrize("count", [1, 30])
def test_cart_accepts_exact_api_bounds(
    session: Session, upc_length: int, quantity: int, count: int
) -> None:
    cipher = Fernet(Fernet.generate_key())
    store_tokens(
        session, OWNER_ID, cipher, CustomerTokens("synthetic-a", "synthetic-r", 1800)
    )
    items = [CartLine(upc="1" * upc_length, quantity=quantity)] * count
    token = issue_cart_confirmation(
        session, OWNER_ID, cipher, uuid4(), items, now_seconds=NOW_SECONDS
    )
    claim = claim_cart_confirmation(
        session, OWNER_ID, cipher, token, now_seconds=NOW_SECONDS
    )
    assert isinstance(claim, CartClaim)
    assert claim.items == tuple(items)


@pytest.mark.parametrize(
    ("upc", "quantity"),
    [
        ("1" * 7, 1),
        ("1" * 15, 1),
        ("1234567x", 1),
        ("12345678", 11),
        ("12345678", True),
    ],
)
def test_cart_revalidates_lines_before_persisting_intents(
    session: Session, upc: str, quantity: int
) -> None:
    cipher = Fernet(Fernet.generate_key())
    store_tokens(
        session, OWNER_ID, cipher, CustomerTokens("synthetic-a", "synthetic-r", 1800)
    )
    items = [CartLine.model_construct(upc=upc, quantity=quantity)]
    with pytest.raises(SecurityIntentError, match="invalid or expired"):
        issue_cart_confirmation(
            session, OWNER_ID, cipher, uuid4(), items, now_seconds=NOW_SECONDS
        )
    assert list(session.scalars(select(SecurityIntent))) == []


def test_state_consumption_and_cart_claim_use_row_locks(session: Session) -> None:
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    state = issue_oauth_state(session, OWNER_ID, now_seconds=NOW_SECONDS)
    start = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    statements: list[str] = []

    def capture(execute: ORMExecuteState) -> None:
        if execute.is_select:
            statements.append(
                str(execute.statement.compile(dialect=postgresql.dialect()))
            )

    event.listen(session, "do_orm_execute", capture)
    consume_oauth_start_ticket(session, OWNER_ID, start, now_seconds=NOW_SECONDS)
    consume_oauth_state(session, OWNER_ID, state, now_seconds=NOW_SECONDS)
    claim_cart_confirmation(session, OWNER_ID, cipher, token, now_seconds=NOW_SECONDS)
    intents = [query for query in statements if "FROM security_intents" in query]
    assert len(intents) == 3
    assert all(query.rstrip().endswith("FOR UPDATE") for query in intents)
    users = [query for query in statements if f"FROM {User.__tablename__}" in query]
    assert users
    assert all("FOR UPDATE" not in query for query in users)
    owners = [
        query for query in statements if f"FROM {KrogerOwner.__tablename__}" in query
    ]
    assert len(owners) == 3
    assert all(query.rstrip().endswith("FOR UPDATE") for query in owners)


def test_owner_uses_shared_lock_before_kroger_row_lock(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = kroger_security.lock_active_owner
    calls: list[int] = []

    def lock_owner(owner_session: Session, user_id: int) -> User:
        assert owner_session is session
        calls.append(user_id)
        return original(owner_session, user_id)

    def capture(execute: ORMExecuteState) -> None:
        if execute.is_select:
            query = str(execute.statement.compile(dialect=postgresql.dialect()))
            if f"FROM {KrogerOwner.__tablename__}" in query:
                assert calls == [OWNER_ID]

    monkeypatch.setattr(kroger_security, "lock_active_owner", lock_owner)
    event.listen(session, "do_orm_execute", capture)
    assert _ticket(session)
    assert calls == [OWNER_ID]


def test_unavailable_owner_keeps_the_security_error(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(owner_session: Session, user_id: int) -> User:
        assert owner_session is session
        assert user_id == OWNER_ID
        raise OwnerUnavailableError()

    monkeypatch.setattr(kroger_security, "lock_active_owner", unavailable)
    with pytest.raises(SecurityIntentError, match="invalid or expired"):
        _ticket(session)
    assert session.get(KrogerOwner, OWNER_ID) is None
    assert list(session.scalars(select(SecurityIntent))) == []


def test_security_helpers_leave_commit_to_caller(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_commit() -> None:
        pytest.fail("Security helpers MUST NOT commit.")

    monkeypatch.setattr(session, "commit", forbidden_commit)
    proof = _proof(session)
    validate_tab_proof(session, OWNER_ID, proof, now_seconds=NOW_SECONDS)
    start = issue_oauth_start_ticket(session, OWNER_ID, now_seconds=NOW_SECONDS)
    consume_oauth_start_ticket(session, OWNER_ID, start, now_seconds=NOW_SECONDS)
    state = issue_oauth_state(session, OWNER_ID, now_seconds=NOW_SECONDS)
    consume_oauth_state(session, OWNER_ID, state, now_seconds=NOW_SECONDS)
    cipher = Fernet(Fernet.generate_key())
    token = _cart(session, cipher)
    claim = claim_cart_confirmation(
        session, OWNER_ID, cipher, token, now_seconds=NOW_SECONDS
    )
    assert isinstance(claim, CartClaim)
    record_cart_outcome(session, OWNER_ID, claim.intent_id, "uncertain")
    revoke_pairing(session, OWNER_ID)
