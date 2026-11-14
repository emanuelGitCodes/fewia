"""Check quote admission with synthetic requests and a PostgreSQL observer."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_kroger_client, get_session
from app.job_models import Job
from app.main import app
from app.models import User
from app.providers.kroger import KrogerClient
from app.security_models import KrogerOwner, QuotaCounter, SecurityIntent
from app.services import kroger_security, security_admission
from tests.conftest import (
    require_test_database_url,
    skip_or_fail_unreachable_test_database,
)

LOCATION = "01234567"
STORED_RESULT: dict[str, object] = {
    "answer": "Stored synthetic answer.",
    "tool_trace": [
        {
            "tool": "what_if_substitute",
            "outcome": "success",
            "inputs": {"status": "swapped", "with_ingredient_id": "ground_beef_80"},
        }
    ],
}


@dataclass
class QuoteRead:
    engine: Engine
    session: Session
    user_id: int
    job_id: str
    minute: datetime
    proof: str = field(repr=False)
    foreign_proof: str = field(repr=False)
    now_seconds: int
    admission_calls: int = 0
    proof_calls: int = 0
    requests: list[str] = field(default_factory=list)
    provider_mode: Literal["ok", "unavailable", "malformed", "empty"] = "ok"

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as observer:
            rows = observer.execute(
                select(QuotaCounter.scope, QuotaCounter.count).where(
                    QuotaCounter.action == "retailer",
                    QuotaCounter.minute_start == self.minute,
                )
            )
            return {scope: count for scope, count in rows}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        assert not self.session.in_transaction()
        assert self.counts() == {"global": 1, "user": 1}
        assert self.proof_calls == 1
        assert "x-fewia-kroger-owner" not in request.headers
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200, json={"access_token": "synthetic-token", "expires_in": 1800}
            )
        if self.provider_mode == "unavailable":
            return httpx.Response(503)
        if self.provider_mode == "malformed":
            return httpx.Response(200, content="invalid json")
        products = (
            []
            if self.provider_mode == "empty"
            else [
                {
                    "productId": "synthetic-product",
                    "description": "Invented ground beef",
                    "items": [{"price": {"regular": 2.49}}],
                }
            ]
        )
        return httpx.Response(200, json={"data": products})


@pytest.fixture
def quote_read(monkeypatch: pytest.MonkeyPatch) -> Iterator[QuoteRead]:
    engine = create_engine(require_test_database_url())
    assert engine.dialect.name == "postgresql"
    try:
        with engine.connect():
            pass
    except SQLAlchemyError as error:
        engine.dispose()
        skip_or_fail_unreachable_test_database(error)
    user_id = 1_000_000_000 + uuid4().int % 1_000_000_000
    foreign_user_id = user_id - 999_999_999
    job_id = str(uuid4())
    minute = datetime(2040, 1, 1, tzinfo=UTC)
    minute += timedelta(minutes=uuid4().int % 20_000_000)
    now_seconds = int((minute + timedelta(seconds=15)).timestamp())
    with Session(engine) as session:
        session.add_all(
            [
                User(id=user_id, display_name="Synthetic quote owner"),
                User(id=foreign_user_id, display_name="Synthetic foreign owner"),
            ]
        )
        session.flush()
        ticket = kroger_security.issue_pairing_ticket(
            session, user_id, now_seconds=now_seconds
        )
        proof = kroger_security.redeem_pairing_ticket(
            session, user_id, ticket, now_seconds=now_seconds
        )
        foreign_ticket = kroger_security.issue_pairing_ticket(
            session, foreign_user_id, now_seconds=now_seconds
        )
        foreign_proof = kroger_security.redeem_pairing_ticket(
            session, foreign_user_id, foreign_ticket, now_seconds=now_seconds
        )
        session.add(
            Job(
                id=job_id,
                user_id=user_id,
                kind="agent",
                request_key=f"chat:{job_id}",
                payload={"operation": "chat"},
                status="succeeded",
                result=STORED_RESULT,
            )
        )
        session.commit()
        context = QuoteRead(
            engine, session, user_id, job_id, minute, proof, foreign_proof, now_seconds
        )
        real_reserve = security_admission.reserve_action
        real_validate = kroger_security.validate_tab_proof

        def reserve(
            db: Session,
            owner_id: int,
            action: security_admission.Action,
            *,
            now: datetime | None = None,
        ) -> None:
            assert db is session
            assert owner_id == user_id
            assert action == "retailer"
            assert now is None
            context.admission_calls += 1
            real_reserve(db, owner_id, action, now=minute + timedelta(seconds=15))

        def validate(
            db: Session,
            owner_id: int,
            tab_proof: str,
            *,
            now_seconds: int | None = None,
        ) -> UUID:
            assert db is session
            assert owner_id == user_id
            assert now_seconds is None
            assert context.admission_calls == 1
            assert context.requests == []
            assert context.counts() == {}
            context.proof_calls += 1
            return real_validate(
                db, owner_id, tab_proof, now_seconds=context.now_seconds
            )

        def current_user() -> User:
            owner = session.get(User, user_id)
            assert owner is not None
            return owner

        monkeypatch.setattr(security_admission, "reserve_action", reserve)
        monkeypatch.setattr(kroger_security, "validate_tab_proof", validate)
        monkeypatch.setitem(app.dependency_overrides, get_session, lambda: session)
        monkeypatch.setitem(app.dependency_overrides, get_current_user, current_user)
        with httpx.Client(transport=httpx.MockTransport(context.handle)) as http:
            kroger = KrogerClient(
                "synthetic-id",
                "synthetic-secret",
                base_url="https://kroger.test",
                client=http,
            )
            monkeypatch.setitem(
                app.dependency_overrides, get_kroger_client, lambda: kroger
            )
            try:
                yield context
            finally:
                session.rollback()
                with Session(engine) as cleanup:
                    cleanup.execute(delete(Job).where(Job.id == job_id))
                    cleanup.execute(
                        delete(QuotaCounter).where(
                            QuotaCounter.action == "retailer",
                            QuotaCounter.minute_start == minute,
                        )
                    )
                    owners = [user_id, foreign_user_id]
                    cleanup.execute(
                        delete(SecurityIntent).where(SecurityIntent.user_id.in_(owners))
                    )
                    cleanup.execute(
                        delete(KrogerOwner).where(KrogerOwner.user_id.in_(owners))
                    )
                    cleanup.execute(delete(User).where(User.id.in_(owners)))
                    cleanup.commit()
                engine.dispose()


def read_quote(
    context: QuoteRead, *, headers: list[tuple[str, str]] | None = None
) -> httpx.Response:
    if headers is None:
        headers = [("X-FEWIA-Kroger-Owner", context.proof)]
    with TestClient(app, base_url="http://localhost") as client:
        return client.get(
            f"/grocery/chat/jobs/{context.job_id}",
            params={"location_id": LOCATION},
            headers=headers,
        )


def assert_stored_answer(context: QuoteRead) -> None:
    context.session.expire_all()
    stored = context.session.get(Job, context.job_id)
    assert stored is not None
    assert stored.result == STORED_RESULT


def test_live_quote_commits_quota_before_any_provider_request(
    quote_read: QuoteRead,
) -> None:
    response = read_quote(quote_read)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["result"]["kroger_quote"]["regular_cents"] == 249
    assert response.json()["result"]["answer"] == STORED_RESULT["answer"]
    assert quote_read.admission_calls == 1
    assert quote_read.requests == ["/v1/connect/oauth2/token", "/v1/products"]
    assert not quote_read.session.in_transaction()
    assert quote_read.counts() == {"global": 1, "user": 1}
    assert_stored_answer(quote_read)


@pytest.mark.parametrize(
    "proof_case",
    [
        "missing",
        "duplicate",
        "duplicate_case",
        "comma",
        "short",
        "long",
        "malformed",
        "unknown",
        "revoked",
        "foreign",
        "expired",
        "ticket",
    ],
)
def test_denied_proof_rolls_back_quota_without_provider_requests(
    quote_read: QuoteRead, proof_case: str
) -> None:
    proof = quote_read.proof
    headers = [("X-FEWIA-Kroger-Owner", proof)]
    shape_denied = proof_case in {
        "missing",
        "duplicate",
        "duplicate_case",
        "comma",
        "short",
        "long",
    }
    if proof_case == "missing":
        headers = []
    elif proof_case in {"duplicate", "duplicate_case"}:
        name = (
            "x-fewia-kroger-owner"
            if proof_case == "duplicate_case"
            else "X-FEWIA-Kroger-Owner"
        )
        headers.append((name, proof))
    elif proof_case in {"comma", "short", "long", "malformed", "unknown"}:
        invalid_proof = {
            "comma": "a" * 21 + "," + "a" * 21,
            "short": "a" * 42,
            "long": "a" * 44,
            "malformed": "." + "a" * 42,
            "unknown": "a" * 43,
        }[proof_case]
        headers = [("X-FEWIA-Kroger-Owner", invalid_proof)]
    elif proof_case == "revoked":
        kroger_security.revoke_pairing(quote_read.session, quote_read.user_id)
        quote_read.session.commit()
    elif proof_case == "foreign":
        headers = [("X-FEWIA-Kroger-Owner", quote_read.foreign_proof)]
    elif proof_case == "expired":
        quote_read.now_seconds += kroger_security.PROOF_TTL_SECONDS
    elif proof_case == "ticket":
        ticket = kroger_security.issue_pairing_ticket(
            quote_read.session,
            quote_read.user_id,
            now_seconds=quote_read.now_seconds,
        )
        quote_read.session.commit()
        headers = [("X-FEWIA-Kroger-Owner", ticket)]
    response = read_quote(quote_read, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "id": quote_read.job_id,
        "status": "succeeded",
        "result": {**STORED_RESULT, "kroger_degraded": True},
        "error_code": None,
    }
    assert quote_read.admission_calls == (0 if shape_denied else 1)
    assert quote_read.proof_calls == (0 if shape_denied else 1)
    assert quote_read.requests == []
    assert not quote_read.session.in_transaction()
    assert quote_read.counts() == {}
    assert_stored_answer(quote_read)


@pytest.mark.parametrize("scope", ["user", "global"])
def test_denied_quote_keeps_stored_answer_without_provider_requests(
    quote_read: QuoteRead, scope: str
) -> None:
    limit = (
        security_admission.RETAILER_USER_LIMIT
        if scope == "user"
        else security_admission.RETAILER_GLOBAL_LIMIT
    )
    quote_read.session.add(
        QuotaCounter(
            action="retailer",
            scope=scope,
            scope_key=quote_read.user_id if scope == "user" else 0,
            minute_start=quote_read.minute,
            expires_at=quote_read.minute + timedelta(minutes=1),
            count=limit,
        )
    )
    quote_read.session.commit()
    response = read_quote(quote_read)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "id": quote_read.job_id,
        "status": "succeeded",
        "result": {**STORED_RESULT, "kroger_degraded": True},
        "error_code": None,
    }
    assert quote_read.admission_calls == 1
    assert quote_read.proof_calls == 0
    assert quote_read.requests == []
    assert not quote_read.session.in_transaction()
    assert quote_read.counts() == {scope: limit}
    assert_stored_answer(quote_read)


@pytest.mark.parametrize("failure", ["owner", "reserve", "proof", "commit"])
def test_quote_admission_errors_roll_back_before_returning_stored_answer(
    quote_read: QuoteRead, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    real_reserve = security_admission.reserve_action

    def fail_reserve(
        session: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        real_reserve(session, user_id, action, now=now)
        if failure == "owner":
            raise security_admission.OwnerUnavailableError()
        raise SQLAlchemyError("Synthetic admission failure")

    def fail_commit() -> None:
        raise SQLAlchemyError("Synthetic commit failure")

    def fail_proof(
        session: Session,
        user_id: int,
        proof: str,
        *,
        now_seconds: int | None = None,
    ) -> UUID:
        raise SQLAlchemyError("Synthetic proof failure")

    if failure == "commit":
        monkeypatch.setattr(quote_read.session, "commit", fail_commit)
    elif failure == "proof":
        monkeypatch.setattr(kroger_security, "validate_tab_proof", fail_proof)
    else:
        monkeypatch.setattr(security_admission, "reserve_action", fail_reserve)
    response = read_quote(quote_read)
    assert response.status_code == 200
    assert response.json()["id"] == quote_read.job_id
    assert response.json()["status"] == "succeeded"
    assert response.json()["result"] == {**STORED_RESULT, "kroger_degraded": True}
    assert quote_read.admission_calls == 1
    assert quote_read.requests == []
    assert not quote_read.session.in_transaction()
    assert quote_read.counts() == {}
    assert_stored_answer(quote_read)


@pytest.mark.parametrize("mode", ["unavailable", "malformed", "empty"])
def test_provider_failure_does_not_undo_committed_quote_admission(
    quote_read: QuoteRead, mode: Literal["unavailable", "malformed", "empty"]
) -> None:
    quote_read.provider_mode = mode
    response = read_quote(quote_read)
    assert response.status_code == 200
    expected = (
        {**STORED_RESULT, "kroger_quote": None}
        if mode == "empty"
        else {**STORED_RESULT, "kroger_degraded": True}
    )
    assert response.json()["result"] == expected
    assert quote_read.admission_calls == 1
    assert quote_read.requests == ["/v1/connect/oauth2/token", "/v1/products"]
    assert not quote_read.session.in_transaction()
    assert quote_read.counts() == {"global": 1, "user": 1}
    assert_stored_answer(quote_read)
