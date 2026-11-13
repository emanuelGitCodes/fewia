from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.provider import LLMProvider, LLMUnavailable
from app.job_models import Job
from app.model_cost_models import ModelCallReservation
from app.services.model_cost_rates import (
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    RuntimeRates,
)

ADMISSION_LOCK = 7_046_231_908_117
SLOT_SECONDS = 60
USER_DAILY_MICRODOLLARS = 1_000_000
GLOBAL_DAILY_MICRODOLLARS = 10_000_000
MAX_LIVE_CALLS = 4
Fence = Callable[[Session], int]
SessionFactory = Callable[[], Session]


class ModelCostError(LLMUnavailable):
    code = "model_cost_unavailable"
    retry_guidance = "Do not retry this model call."

    def __init__(self) -> None:
        super().__init__(f"{self.code}. {self.retry_guidance}")


class ModelBudgetExhausted(ModelCostError):
    code = "model_budget_exhausted"
    retry_guidance = "Try a new job after the next UTC day begins."


class ModelCapacityUnavailable(ModelCostError):
    code = "model_capacity_unavailable"
    retry_guidance = "Try a new job after 60 seconds."


class ModelReservationConflict(ModelCostError):
    code = "model_reservation_conflict"


class ModelFenceRejected(ModelCostError):
    code = "model_fence_rejected"


@dataclass(frozen=True)
class Reservation:
    id: str
    job_id: str
    user_id: int
    attempt: int
    turn: int
    model_id: str
    region: str
    rate_version: str
    reserved_microdollars: int


def _lock(session: Session) -> None:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql" or (
        isinstance(bind, sa.Connection) and bind.in_transaction()
    ):
        raise ModelCostError()
    connection = session.connection()
    driver = connection.connection.dbapi_connection
    if (
        connection.get_isolation_level() != "READ COMMITTED"
        or getattr(driver, "autocommit", True) is not False
    ):
        raise ModelCostError()
    session.execute(sa.select(sa.func.pg_advisory_xact_lock(ADMISSION_LOCK)))


def _clock(session: Session) -> datetime:
    value = session.scalar(sa.select(sa.func.clock_timestamp()))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ModelCostError()
    return value.astimezone(UTC)


class ModelCostLedger:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def reserve(
        self,
        *,
        job_id: str,
        user_id: int,
        turn: int,
        fence: Fence,
        rates: RuntimeRates,
    ) -> Reservation:
        """The fence MUST check the bound job, owner, and lease without commit."""
        if (
            type(turn) is not int
            or turn <= 0
            or type(user_id) is not int
            or not isinstance(job_id, str)
            or not 1 <= len(job_id) <= 36
        ):
            raise ModelReservationConflict()
        amount = rates.reservation_microdollars
        try:
            with self._session_factory() as session, session.begin():
                _lock(session)
                transaction = session.get_transaction()
                attempt = fence(session)
                if (
                    type(attempt) is not int
                    or attempt <= 0
                    or transaction is None
                    or not transaction.is_active
                    or session.get_transaction() is not transaction
                ):
                    raise ModelFenceRejected()
                job = session.scalar(
                    sa.select(Job)
                    .where(
                        Job.id == job_id,
                        Job.user_id == user_id,
                        Job.attempts == attempt,
                        Job.status == "running",
                    )
                    .with_for_update()
                )
                now = _clock(session)
                if (
                    job is None
                    or job.lease_expires_at is None
                    or job.lease_expires_at <= now
                ):
                    raise ModelFenceRejected()
                duplicate = session.scalar(
                    sa.select(ModelCallReservation.id).where(
                        ModelCallReservation.job_id == job_id,
                        ModelCallReservation.attempt == attempt,
                        ModelCallReservation.turn == turn,
                    )
                )
                if duplicate is not None:
                    raise ModelReservationConflict()
                exposure = sa.case(
                    (
                        ModelCallReservation.status == "settled",
                        ModelCallReservation.charged_microdollars,
                    ),
                    else_=ModelCallReservation.reserved_microdollars,
                )
                global_total, owner_total = session.execute(
                    sa.select(
                        sa.func.coalesce(sa.func.sum(exposure), 0),
                        sa.func.coalesce(
                            sa.func.sum(
                                sa.case(
                                    (ModelCallReservation.user_id == user_id, exposure),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                    ).where(ModelCallReservation.utc_day == now.date())
                ).one()
                if (
                    amount <= 0
                    or owner_total + amount > USER_DAILY_MICRODOLLARS
                    or global_total + amount > GLOBAL_DAILY_MICRODOLLARS
                ):
                    raise ModelBudgetExhausted()
                live = session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ModelCallReservation)
                    .where(
                        ModelCallReservation.status.in_(("in_flight", "unknown")),
                        ModelCallReservation.slot_deadline > now,
                    )
                )
                if live is None or live >= MAX_LIVE_CALLS:
                    raise ModelCapacityUnavailable()
                started = _clock(session)
                if started.date() != now.date() or job.lease_expires_at <= started:
                    raise ModelFenceRejected()
                reservation = Reservation(
                    id=str(uuid4()),
                    job_id=job_id,
                    user_id=user_id,
                    attempt=attempt,
                    turn=turn,
                    model_id=rates.record.model_id,
                    region=rates.record.region,
                    rate_version=rates.version,
                    reserved_microdollars=amount,
                )
                session.add(
                    ModelCallReservation(
                        **vars(reservation),
                        utc_day=now.date(),
                        status="in_flight",
                        started_at=started,
                        slot_deadline=started + timedelta(seconds=SLOT_SECONDS),
                    )
                )
                session.flush()
            return reservation
        except SQLAlchemyError:
            raise ModelCostError() from None

    def settle(self, reservation: Reservation, cost: int | None) -> None:
        if cost is not None and (
            type(cost) is not int or not 0 <= cost <= reservation.reserved_microdollars
        ):
            cost = None
        try:
            with self._session_factory() as session, session.begin():
                _lock(session)
                row = session.scalar(
                    sa.select(ModelCallReservation)
                    .where(ModelCallReservation.id == reservation.id)
                    .with_for_update()
                )
                if (
                    row is None
                    or row.status != "in_flight"
                    or any(
                        getattr(row, name) != value
                        for name, value in vars(reservation).items()
                    )
                ):
                    raise ModelReservationConflict()
                row.status = "unknown" if cost is None else "settled"
                row.charged_microdollars = cost
                row.finished_at = _clock(session)
                session.flush()
        except SQLAlchemyError:
            raise ModelCostError() from None


def verified_cost(response: object, rates: RuntimeRates) -> int | None:
    if not isinstance(response, dict):
        return None
    if rates.provider == "openai":
        if response.get("serviceTier") != "default":
            return None
    else:
        tier = response.get("serviceTier")
        performance = response.get("performanceConfig")
        if (
            not isinstance(tier, dict)
            or tier.get("type") != "default"
            or not isinstance(performance, dict)
            or performance.get("latency") != "standard"
        ):
            return None
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    incoming, outgoing = usage.get("inputTokens"), usage.get("outputTokens")
    read = usage.get("cacheReadInputTokens", 0)
    write = usage.get("cacheWriteInputTokens", 0)
    if any(
        type(value) is not int or value < 0
        for value in (incoming, outgoing, read, write)
    ):
        return None
    if not (
        isinstance(incoming, int)
        and isinstance(outgoing, int)
        and isinstance(read, int)
        and isinstance(write, int)
    ):
        return None
    total_input = incoming if rates.provider == "openai" else incoming + read + write
    if total_input > MAX_INPUT_TOKENS or outgoing > MAX_OUTPUT_TOKENS:
        return None
    if rates.provider == "openai" and read > incoming:
        return None
    if (
        (rates.provider == "openai" and write)
        or (read and rates.record.cached_input_usd_per_1000 is None)
        or (write and rates.record.cache_write_usd_per_1000 is None)
    ):
        return None
    if "totalTokens" in usage:
        total = usage["totalTokens"]
        # Bedrock cache totals MUST satisfy both reported input conventions.
        if (
            type(total) is not int
            or total != total_input + outgoing
            or (rates.provider == "bedrock" and total != incoming + outgoing)
        ):
            return None
    cost = rates.cost(
        incoming - read if rates.provider == "openai" else incoming,
        outgoing,
        read,
        write,
    )
    return cost if cost <= rates.reservation_microdollars else None


class CostControlledProvider:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        job_id: str,
        user_id: int,
        fence: Fence,
        provider: LLMProvider,
        rates: RuntimeRates,
    ) -> None:
        self._ledger = ModelCostLedger(session_factory)
        self._job_id = job_id
        self._user_id = user_id
        self._fence = fence
        self._provider = provider
        self._rates = rates
        self._turn = 0
        self._turn_lock = Lock()

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        admission_started = monotonic()
        with self._turn_lock:
            self._turn += 1
            turn = self._turn
        reservation = self._ledger.reserve(
            job_id=self._job_id,
            user_id=self._user_id,
            turn=turn,
            fence=self._fence,
            rates=self._rates,
        )
        if monotonic() - admission_started >= SLOT_SECONDS - 45:
            self._ledger.settle(reservation, None)
            raise ModelCostError()
        try:
            response = self._provider.converse(system_prompt, messages, tools)
        except BaseException:
            try:
                self._ledger.settle(reservation, None)
            except Exception:  # noqa: BLE001
                pass
            raise
        self._ledger.settle(reservation, verified_cost(response, self._rates))
        return response
