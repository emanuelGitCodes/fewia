from __future__ import annotations

import json
import runpy
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import pytest
import sqlalchemy as sa
from conftest import require_test_database_url
from sqlalchemy.orm import Session, sessionmaker

from app.job_models import Job
from app.model_cost_models import ModelCallReservation
from app.models import User
from app.services.model_cost import (
    ADMISSION_LOCK,
    CostControlledProvider,
    ModelBudgetExhausted,
    ModelCapacityUnavailable,
    ModelCostError,
    ModelCostLedger,
    ModelFenceRejected,
    ModelReservationConflict,
    Reservation,
    verified_cost,
)
from app.services.model_cost_rates import (
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    ModelRatesUnavailable,
    RuntimeRates,
    load_runtime_rates,
)


def rate_record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_id": "gpt-6-luna",
        "region": "us",
        "currency": "USD",
        "input_usd_per_1000": "0.001",
        "output_usd_per_1000": "0.002",
        "cached_input_usd_per_1000": "0.0005",
        "source_url": "https://openai.com/api/pricing/",
        "source_version": "fixture-1",
        "date_as_of": "2026-11-12",
        "retrieved_at": "2026-11-12",
    }
    if changes.get("model_id", record["model_id"]) == "gpt-6-luna":
        record.update(
            cache_write_30m_usd_per_1000="0.001",
            cache_write_12h_usd_per_1000="0.001",
        )
    else:
        record["cache_write_usd_per_1000"] = "0"
    return {**record, **changes}


def load_fixture_rates(tmp_path: Path, **changes: object) -> RuntimeRates:
    record = rate_record(**changes)
    path = tmp_path / f"rates-{uuid4().hex}.json"
    path.write_text(json.dumps({"rates": [record]}), encoding="utf-8")
    return load_runtime_rates(
        model_id=str(record["model_id"]),
        region=str(record["region"]),
        test_rates_path=path,
    )


@pytest.fixture()
def rates(tmp_path: Path) -> RuntimeRates:
    return load_fixture_rates(tmp_path)


def known_response() -> dict[str, object]:
    return {
        "serviceTier": "default",
        "usage": {
            "inputTokens": 10,
            "outputTokens": 2,
            "cacheReadInputTokens": 4,
        },
        "output": {"message": {"content": [{"text": "fixture"}]}},
    }


class FakeProvider:
    def __init__(
        self,
        response: dict[str, object] | None = None,
        *,
        hook: Callable[[], None] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response if response is not None else known_response()
        self.hook = hook
        self.error = error
        self.calls = 0

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        if self.hook is not None:
            self.hook()
        if self.error is not None:
            raise self.error
        return self.response


@dataclass
class Database:
    sessions: sessionmaker[Session]
    jobs: dict[int, str]

    def fence(self, owner: int = 1) -> Callable[[Session], int]:
        def check(session: Session) -> int:
            job = session.scalar(
                sa.select(Job)
                .where(Job.id == self.jobs[owner], Job.user_id == owner)
                .with_for_update()
            )
            if job is None:
                raise ModelFenceRejected()
            return job.attempts

        return check

    def reserve(
        self, rates: RuntimeRates, owner: int = 1, turn: int = 1
    ) -> Reservation:
        return ModelCostLedger(self.sessions).reserve(
            job_id=self.jobs[owner],
            user_id=owner,
            turn=turn,
            fence=self.fence(owner),
            rates=rates,
        )

    def provider(
        self, rates: RuntimeRates, fake: FakeProvider, owner: int = 1
    ) -> CostControlledProvider:
        return CostControlledProvider(
            session_factory=self.sessions,
            job_id=self.jobs[owner],
            user_id=owner,
            fence=self.fence(owner),
            provider=fake,
            rates=rates,
        )


@pytest.fixture()
def database() -> Iterator[Database]:
    url = require_test_database_url()
    admin = sa.create_engine(url)
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("Model cost tests require disposable PostgreSQL.")
    schema = "model_cost_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(
        url,
        isolation_level="READ COMMITTED",
        connect_args={
            "options": (
                f"-csearch_path={schema} -ctimezone=Etc/GMT+12 "
                "-cstatement_timeout=10000 -clock_timeout=5000"
            )
        },
        pool_size=10,
    )
    try:
        with engine.begin() as connection:
            User.__table__.create(connection)
            Job.__table__.create(connection)
            connection.execute(sa.text("ALTER TABLE jobs ADD UNIQUE (id, user_id)"))
            ModelCallReservation.__table__.create(connection)
            migration = runpy.run_path(
                str(
                    Path(__file__).resolve().parents[1]
                    / "alembic/versions/0017_model_cost.py"
                )
            )
            connection.execute(sa.text(migration["GUARD_FUNCTION_SQL"]))
            connection.execute(sa.text(migration["GUARD_TRIGGER_SQL"]))
        sessions = sessionmaker(engine, expire_on_commit=False)
        jobs = {owner: str(uuid4()) for owner in range(1, 17)}
        with sessions.begin() as session:
            now = session.scalar(sa.select(sa.func.clock_timestamp()))
            assert isinstance(now, datetime)
            session.add_all(
                User(id=owner, display_name="model-cost-fixture") for owner in jobs
            )
            session.flush()
            session.add_all(
                Job(
                    id=job_id,
                    user_id=owner,
                    kind="agent",
                    request_key=f"cost-fixture-{owner}",
                    status="running",
                    payload={},
                    attempts=1,
                    lease_token="fixture-lease",
                    lease_expires_at=now + timedelta(hours=1),
                )
                for owner, job_id in jobs.items()
            )
        yield Database(sessions, jobs)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def seed_exposure(
    database: Database,
    rates: RuntimeRates,
    *,
    owner: int = 1,
    amount: int = 990_000,
    status: str = "unknown",
    yesterday: bool = False,
    live: bool = False,
) -> str:
    with database.sessions.begin() as session:
        now = session.scalar(sa.select(sa.func.clock_timestamp()))
        assert isinstance(now, datetime)
        utc_now = now.astimezone(UTC)
        started = utc_now - (
            timedelta(days=1) if yesterday else timedelta(seconds=0 if live else 120)
        )
        if not yesterday:
            midnight = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
            started = max(started, midnight)
        row = ModelCallReservation(
            id=str(uuid4()),
            job_id=database.jobs[owner],
            user_id=owner,
            attempt=1,
            turn=100,
            model_id=rates.record.model_id,
            region=rates.record.region,
            rate_version=rates.version,
            utc_day=started.date(),
            reserved_microdollars=amount,
            status="in_flight",
            started_at=started,
            slot_deadline=started + timedelta(seconds=60),
        )
        session.add(row)
        session.flush()
        if status != "in_flight":
            row.status = status
            row.finished_at = now
            row.charged_microdollars = amount if status == "settled" else None
        return row.id


def test_four_global_slots_with_parallel_sessions(
    database: Database, rates: RuntimeRates
) -> None:
    start = Barrier(6)
    rejected = Barrier(3)
    entered = Barrier(5)
    release = Event()

    def wait_for_release() -> None:
        entered.wait(timeout=10)
        assert release.wait(timeout=15)

    providers = [FakeProvider(hook=wait_for_release) for _ in range(6)]

    def converse(owner: int) -> str:
        start.wait(timeout=10)
        try:
            wrapper = database.provider(rates, providers[owner - 1], owner)
            wrapper.converse("fixture", [], [])
        except ModelCapacityUnavailable:
            rejected.wait(timeout=10)
            return "capacity"
        return "settled"

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(converse, owner) for owner in range(1, 7)]
        try:
            rejected.wait(timeout=10)
            entered.wait(timeout=10)
            assert sum(provider.calls for provider in providers) == 4
        finally:
            release.set()
        results = [future.result(timeout=20) for future in futures]
    assert results.count("settled") == 4
    assert results.count("capacity") == 2


@pytest.mark.parametrize("status", ["in_flight", "unknown", "settled"])
def test_owner_budget_counts_all_exposure(
    database: Database, rates: RuntimeRates, status: str
) -> None:
    seed_exposure(database, rates, status=status)
    fake = FakeProvider()
    with pytest.raises(ModelBudgetExhausted, match="model_budget_exhausted"):
        database.provider(rates, fake).converse("fixture", [], [])
    assert fake.calls == 0


def test_global_daily_budget(database: Database, rates: RuntimeRates) -> None:
    for owner in range(1, 11):
        seed_exposure(database, rates, owner=owner, amount=999_000)
    with pytest.raises(ModelBudgetExhausted):
        database.reserve(rates, owner=11)


@pytest.mark.parametrize("global_limit", [False, True])
def test_parallel_reservations_cannot_overspend(
    database: Database, rates: RuntimeRates, global_limit: bool
) -> None:
    if global_limit:
        for owner in range(1, 11):
            seed_exposure(
                database, rates, owner=owner, amount=990_000, status="settled"
            )
    else:
        seed_exposure(database, rates, amount=900_000, status="settled")
    start = Barrier(6)

    def reserve(index: int) -> str:
        start.wait(timeout=10)
        try:
            database.reserve(
                rates, owner=index + 11 if global_limit else 1, turn=index + 1
            )
        except ModelBudgetExhausted:
            return "budget"
        return "reserved"

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(reserve, range(6)))
    assert results.count("reserved") == 1
    assert results.count("budget") == 5


def test_duplicate_turn_has_no_second_egress(
    database: Database, rates: RuntimeRates
) -> None:
    fake = FakeProvider()
    database.provider(rates, fake).converse("fixture", [], [])
    with pytest.raises(ModelReservationConflict):
        database.provider(rates, fake).converse("fixture", [], [])
    assert fake.calls == 1


def test_provider_holds_no_database_locks(
    database: Database, rates: RuntimeRates
) -> None:
    def probe() -> None:
        with database.sessions.begin() as session:
            assert session.scalar(
                sa.select(sa.func.pg_try_advisory_xact_lock(ADMISSION_LOCK))
            )
            assert session.scalar(
                sa.select(Job)
                .where(Job.id == database.jobs[1])
                .with_for_update(nowait=True)
            )

    fake = FakeProvider(hook=probe)
    response = database.provider(rates, fake).converse("fixture", [], [])
    assert response is fake.response
    with database.sessions() as session:
        row = session.scalar(sa.select(ModelCallReservation))
        assert row is not None
        assert row.status == "settled"
        assert row.charged_microdollars == 12


def test_turns_increment(database: Database, rates: RuntimeRates) -> None:
    wrapper = database.provider(rates, FakeProvider())
    wrapper.converse("fixture", [], [])
    wrapper.converse("fixture", [], [])
    with database.sessions() as session:
        assert list(
            session.scalars(sa.select(ModelCallReservation.turn).order_by("turn"))
        ) == [1, 2]


def test_utc_rollover_ignores_prior_day_budget(
    database: Database, rates: RuntimeRates
) -> None:
    seed_exposure(database, rates, yesterday=True, amount=1_000_000)
    reservation = database.reserve(rates)
    with database.sessions() as session:
        row = session.get(ModelCallReservation, reservation.id)
        now = session.scalar(sa.select(sa.func.clock_timestamp()))
        assert row is not None and isinstance(now, datetime)
        assert row.utc_day == now.astimezone(UTC).date()


@pytest.mark.parametrize("status", ["unknown", "in_flight"])
def test_expired_slots_keep_their_cost(
    database: Database, rates: RuntimeRates, status: str
) -> None:
    with database.sessions() as session:
        now = session.scalar(sa.select(sa.func.clock_timestamp()))
        assert isinstance(now, datetime)
        if now.astimezone(UTC).hour == 0 and now.minute == 0:
            pytest.skip("A current-day slot cannot expire in the first UTC minute.")
    for owner in range(1, 5):
        seed_exposure(database, rates, owner=owner, amount=990_000, status=status)
    database.reserve(rates, owner=5)
    with pytest.raises(ModelBudgetExhausted):
        database.reserve(rates, owner=1)


def test_unknown_call_keeps_its_live_slot(
    database: Database, rates: RuntimeRates
) -> None:
    for owner in range(1, 5):
        seed_exposure(database, rates, owner=owner, amount=1, live=True)
    with pytest.raises(ModelCapacityUnavailable):
        database.reserve(rates, owner=5)


def test_unknown_usage_retains_maximum(database: Database, rates: RuntimeRates) -> None:
    fake = FakeProvider({"serviceTier": "priority", "usage": {}})
    database.provider(rates, fake).converse("fixture", [], [])
    with database.sessions() as session:
        row = session.scalar(sa.select(ModelCallReservation))
        assert row is not None
        assert row.status == "unknown" and row.charged_microdollars is None
        assert row.reserved_microdollars == rates.reservation_microdollars


def test_provider_error_survives_unknown_settlement(
    database: Database, rates: RuntimeRates
) -> None:
    error = TimeoutError("fixture timeout")
    fake = FakeProvider(error=error)
    with pytest.raises(TimeoutError) as raised:
        database.provider(rates, fake).converse("fixture", [], [])
    assert raised.value is error
    with database.sessions() as session:
        row = session.scalar(sa.select(ModelCallReservation))
        assert row is not None and row.status == "unknown"
        assert row.charged_microdollars is None


def test_settlement_failure_is_static_and_keeps_maximum(
    database: Database, rates: RuntimeRates, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ModelCostLedger.settle

    def fail(self: ModelCostLedger, reservation: Reservation, cost: int | None) -> None:
        raise ModelCostError()

    monkeypatch.setattr(ModelCostLedger, "settle", fail)
    fake = FakeProvider()
    with pytest.raises(ModelCostError, match="model_cost_unavailable"):
        database.provider(rates, fake).converse("fixture", [], [])
    monkeypatch.setattr(ModelCostLedger, "settle", original)
    assert fake.calls == 1
    with database.sessions() as session:
        row = session.scalar(sa.select(ModelCallReservation))
        assert row is not None and row.status == "in_flight"
        assert row.charged_microdollars is None


def test_sql_failure_before_admission_has_zero_egress(
    database: Database, rates: RuntimeRates
) -> None:
    with database.sessions() as session:
        engine = session.get_bind()

    def fail_insert(
        connection: sa.Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO model_call_reservations"):
            raise sa.exc.OperationalError("fixture", {}, RuntimeError("fixture"))

    sa.event.listen(engine, "before_cursor_execute", fail_insert)
    fake = FakeProvider()
    try:
        with pytest.raises(ModelCostError, match="model_cost_unavailable"):
            database.provider(rates, fake).converse("fixture", [], [])
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_insert)
    assert fake.calls == 0
    with database.sessions() as session:
        assert session.scalar(sa.select(sa.func.count(ModelCallReservation.id))) == 0


def test_slow_admission_has_zero_egress(
    database: Database, rates: RuntimeRates, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter((0.0, 16.0))
    monkeypatch.setattr("app.services.model_cost.monotonic", lambda: next(ticks))
    fake = FakeProvider()
    with pytest.raises(ModelCostError):
        database.provider(rates, fake).converse("fixture", [], [])
    assert fake.calls == 0
    with database.sessions() as session:
        row = session.scalar(sa.select(ModelCallReservation))
        assert row is not None and row.status == "unknown"
        assert row.reserved_microdollars == rates.reservation_microdollars


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "AUTOCOMMIT"])
def test_unsafe_transaction_mode_fails_closed(
    database: Database, rates: RuntimeRates, isolation: str
) -> None:
    with database.sessions() as session:
        engine = session.get_bind()
    factory = sessionmaker(engine.execution_options(isolation_level=isolation))
    fake = FakeProvider()
    wrapper = CostControlledProvider(
        session_factory=factory,
        job_id=database.jobs[1],
        user_id=1,
        fence=database.fence(),
        provider=fake,
        rates=rates,
    )
    with pytest.raises(ModelCostError):
        wrapper.converse("fixture", [], [])
    assert fake.calls == 0


def test_joined_outer_transaction_has_zero_egress(
    database: Database, rates: RuntimeRates
) -> None:
    with database.sessions() as session:
        engine = session.get_bind()
    with engine.connect() as connection, connection.begin():
        fake = FakeProvider()
        wrapper = CostControlledProvider(
            session_factory=sessionmaker(connection),
            job_id=database.jobs[1],
            user_id=1,
            fence=database.fence(),
            provider=fake,
            rates=rates,
        )
        with pytest.raises(ModelCostError):
            wrapper.converse("fixture", [], [])
        assert fake.calls == 0


def test_provider_error_is_not_masked_by_database_failure(
    database: Database, rates: RuntimeRates, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: ModelCostLedger, reservation: Reservation, cost: int | None) -> None:
        raise ModelCostError()

    monkeypatch.setattr(ModelCostLedger, "settle", fail)
    error = TimeoutError("fixture timeout")
    with pytest.raises(TimeoutError) as raised:
        database.provider(rates, FakeProvider(error=error)).converse("fixture", [], [])
    assert raised.value is error


def test_parallel_settlement_cannot_double_credit(
    database: Database, rates: RuntimeRates
) -> None:
    reservation = database.reserve(rates)
    start = Barrier(2)

    def settle() -> str:
        start.wait(timeout=10)
        try:
            ModelCostLedger(database.sessions).settle(reservation, 1)
        except ModelReservationConflict:
            return "conflict"
        return "settled"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: settle(), range(2)))
    assert sorted(results) == ["conflict", "settled"]
    with database.sessions() as session:
        row = session.get(ModelCallReservation, reservation.id)
        assert row is not None and row.charged_microdollars == 1


def test_settlement_requires_same_identity(
    database: Database, rates: RuntimeRates
) -> None:
    reservation = database.reserve(rates)
    with pytest.raises(ModelReservationConflict):
        ModelCostLedger(database.sessions).settle(replace(reservation, user_id=2), 0)
    ModelCostLedger(database.sessions).settle(reservation, None)
    with pytest.raises(ModelReservationConflict):
        ModelCostLedger(database.sessions).settle(reservation, 0)


@pytest.mark.parametrize("cost", [-1, True, 10_000_000])
def test_unverified_settlement_keeps_maximum(
    database: Database, rates: RuntimeRates, cost: int
) -> None:
    reservation = database.reserve(rates)
    ModelCostLedger(database.sessions).settle(reservation, cost)
    with database.sessions() as session:
        row = session.get(ModelCallReservation, reservation.id)
        assert row is not None and row.status == "unknown"
        assert row.charged_microdollars is None


@pytest.mark.parametrize("field", ["user_id", "attempts", "status", "lease_expires_at"])
def test_job_fence_rejects_mismatches_without_egress(
    database: Database, rates: RuntimeRates, field: str
) -> None:
    with database.sessions.begin() as session:
        job = session.get(Job, database.jobs[1])
        assert job is not None
        if field == "user_id":
            job.request_key = "owner-mismatch"
            job.user_id = 2
        elif field == "attempts":
            job.attempts = 2
        elif field == "status":
            job.status = "failed"
        else:
            now = session.scalar(sa.select(sa.func.clock_timestamp()))
            assert isinstance(now, datetime)
            job.lease_expires_at = now - timedelta(seconds=1)
    fake = FakeProvider()
    wrapper = CostControlledProvider(
        session_factory=database.sessions,
        job_id=database.jobs[1],
        user_id=1,
        fence=lambda session: 1,
        provider=fake,
        rates=rates,
    )
    with pytest.raises(ModelFenceRejected):
        wrapper.converse("fixture", [], [])
    assert fake.calls == 0


def test_fence_exception_has_zero_provider_calls(
    database: Database, rates: RuntimeRates
) -> None:
    def reject(session: Session) -> int:
        raise ModelFenceRejected()

    fake = FakeProvider()
    wrapper = CostControlledProvider(
        session_factory=database.sessions,
        job_id=database.jobs[1],
        user_id=1,
        fence=reject,
        provider=fake,
        rates=rates,
    )
    with pytest.raises(ModelFenceRejected):
        wrapper.converse("fixture", [], [])
    assert fake.calls == 0


@pytest.mark.parametrize("turn", [0, -1, True])
def test_nonpositive_or_boolean_turn_rejected(
    database: Database, rates: RuntimeRates, turn: int
) -> None:
    with pytest.raises(ModelReservationConflict):
        database.reserve(rates, turn=turn)


def test_database_enforces_immutable_identity(
    database: Database, rates: RuntimeRates
) -> None:
    reservation = database.reserve(rates)
    with pytest.raises(sa.exc.IntegrityError):
        with database.sessions.begin() as session:
            session.execute(
                sa.update(ModelCallReservation)
                .where(ModelCallReservation.id == reservation.id)
                .values(
                    status="settled",
                    charged_microdollars=0,
                    user_id=2,
                    finished_at=sa.func.clock_timestamp(),
                )
            )


def test_known_usage_and_upward_rounding(tmp_path: Path, rates: RuntimeRates) -> None:
    assert verified_cost(known_response(), rates) == 12
    tiny = load_fixture_rates(
        tmp_path,
        input_usd_per_1000="0.0000001",
        output_usd_per_1000="0.0000001",
        cache_write_30m_usd_per_1000="0.0000001",
        cache_write_12h_usd_per_1000="0.0000001",
    )
    assert (
        verified_cost(
            {"serviceTier": "default", "usage": {"inputTokens": 1, "outputTokens": 0}},
            tiny,
        )
        == 1
    )
    premium_cache = load_fixture_rates(tmp_path, cached_input_usd_per_1000="0.005")
    assert premium_cache.reservation_microdollars == 335_872


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"inputTokens": True, "outputTokens": 1},
        {"inputTokens": -1, "outputTokens": 1},
        {"inputTokens": 1, "outputTokens": False},
        {"inputTokens": MAX_INPUT_TOKENS + 1, "outputTokens": 1},
        {"inputTokens": 1, "outputTokens": MAX_OUTPUT_TOKENS + 1},
        {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": 2},
        {"inputTokens": 1, "outputTokens": 1, "cacheWriteInputTokens": 1},
        {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": True},
        {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": -1},
        {"inputTokens": 1, "outputTokens": 1, "totalTokens": 1},
    ],
)
def test_invalid_usage_is_unknown(usage: object, rates: RuntimeRates) -> None:
    assert verified_cost({"serviceTier": "default", "usage": usage}, rates) is None


@pytest.mark.parametrize("tier", [None, "priority", "flex", {"type": "default"}])
def test_unverified_openai_tier_is_unknown(tier: object, rates: RuntimeRates) -> None:
    assert verified_cost({**known_response(), "serviceTier": tier}, rates) is None


def test_missing_cache_price_is_unknown(tmp_path: Path) -> None:
    rates = load_fixture_rates(tmp_path, cached_input_usd_per_1000=None)
    assert verified_cost(known_response(), rates) is None


@pytest.mark.parametrize("response", [None, {}, {"serviceTier": "default"}])
def test_missing_response_usage_is_unknown(
    response: object, rates: RuntimeRates
) -> None:
    assert verified_cost(response, rates) is None


def test_bedrock_tiers_and_exclusive_cache_input(tmp_path: Path) -> None:
    rates = load_fixture_rates(
        tmp_path, model_id="us.amazon.nova-2-lite-v1:0", region="us-east-1"
    )
    response = {
        **known_response(),
        "serviceTier": {"type": "default"},
        "performanceConfig": {"latency": "standard"},
    }
    assert verified_cost(response, rates) == 16
    assert verified_cost({**response, "performanceConfig": {}}, rates) is None
    assert verified_cost({**response, "serviceTier": "default"}, rates) is None
    assert (
        verified_cost(
            {
                **response,
                "usage": {
                    "inputTokens": MAX_INPUT_TOKENS,
                    "outputTokens": 0,
                    "cacheReadInputTokens": 1,
                },
            },
            rates,
        )
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"input_usd_per_1000": "0"},
        {"output_usd_per_1000": "0"},
        {"cached_input_usd_per_1000": "0"},
        {"cache_write_30m_usd_per_1000": "0"},
        {"cache_write_12h_usd_per_1000": "0"},
        {"cache_write_30m_usd_per_1000": "-1"},
        {"cache_write_12h_usd_per_1000": "NaN"},
        {"cache_write_12h_usd_per_1000": True},
        {"cache_write_12h_usd_per_1000": "1e31"},
        {"input_usd_per_1000": 0.1},
        {"input_usd_per_1000": "NaN"},
        {"source_url": "http://openai.com/pricing"},
        {"source_version": ""},
        {"currency": "EUR"},
        {"date_as_of": "invalid"},
    ],
)
def test_invalid_rates_fail_closed(tmp_path: Path, change: dict[str, object]) -> None:
    with pytest.raises(ModelRatesUnavailable):
        load_fixture_rates(tmp_path, **change)


def test_missing_duplicate_and_mismatched_rates_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    with pytest.raises(ModelRatesUnavailable):
        load_runtime_rates(model_id="gpt-6-luna", region="us", test_rates_path=path)
    for records in ([], [rate_record(), rate_record()], [rate_record(region="global")]):
        path.write_text(json.dumps({"rates": records}), encoding="utf-8")
        with pytest.raises(ModelRatesUnavailable):
            load_runtime_rates(model_id="gpt-6-luna", region="us", test_rates_path=path)
    record = rate_record()
    del record["output_usd_per_1000"]
    path.write_text(json.dumps({"rates": [record]}), encoding="utf-8")
    with pytest.raises(ModelRatesUnavailable):
        load_runtime_rates(model_id="gpt-6-luna", region="us", test_rates_path=path)


def test_rate_version_changes_with_price_and_source(tmp_path: Path) -> None:
    original = load_fixture_rates(tmp_path)
    price = load_fixture_rates(tmp_path, input_usd_per_1000="0.002")
    source = load_fixture_rates(tmp_path, source_version="fixture-2")
    write = load_fixture_rates(tmp_path, cache_write_12h_usd_per_1000="0.003")
    assert len({original.version, price.version, source.version, write.version}) == 4


def test_only_canonical_approved_arn_in_configured_region(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    path.write_text(
        json.dumps(
            {
                "rates": [
                    rate_record(
                        model_id="us.amazon.nova-2-pro-v1:0", region="us-east-1"
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    profile = "us.amazon.nova-2-pro-v1:0"
    arn = f"arn:aws:bedrock:us-east-1:000000000000:inference-profile/{profile}"
    rates = load_runtime_rates(model_id=arn, region="us-east-1", test_rates_path=path)
    assert rates.record.model_id == profile
    for model, region in (
        (arn, "us-west-2"),
        (arn.replace("us-east-1", "us-west-2"), "us-east-1"),
        ("amazon.nova-2-pro-v1:0", "us-east-1"),
        ("us.openai.gpt-6-luna", "us-east-1"),
        ("gpt-6-luna", "us-east-1"),
    ):
        with pytest.raises(ModelRatesUnavailable):
            load_runtime_rates(model_id=model, region=region, test_rates_path=path)


@pytest.mark.parametrize(
    ("region", "regular", "read", "write_30m", "write_12h", "reserved", "mixed"),
    [
        ("global", "0.00010", "0.00001", "0.000125", "0.00025", 24576, 154),
        ("us", "0.00011", "0.000011", "0.0001375", "0.000275", 26215, 170),
    ],
)
def test_openai_reserves_12h_write_and_prices_unclassified_input(
    tmp_path: Path,
    region: str,
    regular: str,
    read: str,
    write_30m: str,
    write_12h: str,
    reserved: int,
    mixed: int,
) -> None:
    rates = load_fixture_rates(
        tmp_path,
        region=region,
        input_usd_per_1000=regular,
        cached_input_usd_per_1000=read,
        cache_write_30m_usd_per_1000=write_30m,
        cache_write_12h_usd_per_1000=write_12h,
    )
    assert rates.reservation_microdollars == reserved
    response = {
        "serviceTier": "default",
        "usage": {"inputTokens": MAX_INPUT_TOKENS, "outputTokens": MAX_OUTPUT_TOKENS},
    }
    assert verified_cost(response, rates) == reserved
    assert verified_cost({**response, "serviceTier": "priority"}, rates) is None
    assert verified_cost({**response, "usage": {}}, rates) is None
    unclassified = rates.cost(1000, 0)
    assert unclassified == (250 if region == "global" else 275)
    assert unclassified > (100 if region == "global" else 110)
    assert (
        verified_cost(
            {
                "serviceTier": "default",
                "usage": {
                    "inputTokens": 1000,
                    "outputTokens": 0,
                    "cacheReadInputTokens": 400,
                    "totalTokens": 1000,
                },
            },
            rates,
        )
        == mixed
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"cache_write_30m_usd_per_1000": None},
        {"cache_write_12h_usd_per_1000": None},
        {"cache_write_usd_per_1000": "0"},
        {"cache_write_usd_per_1000": "0.001"},
        {
            "model_id": "us.amazon.nova-2-lite-v1:0",
            "region": "us-east-1",
            "cache_write_30m_usd_per_1000": "0",
        },
        {
            "model_id": "us.amazon.nova-2-lite-v1:0",
            "region": "us-east-1",
            "cache_write_12h_usd_per_1000": "0.001",
        },
    ],
)
def test_missing_or_conflicting_write_metadata_fails_closed(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    with pytest.raises(ModelRatesUnavailable):
        load_fixture_rates(tmp_path, **changes)


@pytest.mark.parametrize(
    "missing", ["cache_write_30m_usd_per_1000", "cache_write_12h_usd_per_1000"]
)
def test_openai_missing_write_fields_fail_before_admission(
    tmp_path: Path, missing: str
) -> None:
    record = rate_record()
    del record[missing]
    path = tmp_path / "missing-write.json"
    path.write_text(json.dumps({"rates": [record]}), encoding="utf-8")
    with pytest.raises(ModelRatesUnavailable):
        load_runtime_rates(model_id="gpt-6-luna", region="us", test_rates_path=path)


def bedrock_response(**usage_changes: object) -> dict[str, object]:
    return {
        "serviceTier": {"type": "default"},
        "performanceConfig": {"latency": "standard"},
        "usage": {
            "inputTokens": 100,
            "outputTokens": 10,
            "cacheReadInputTokens": 200,
            "cacheWriteInputTokens": 300,
            **usage_changes,
        },
    }


@pytest.mark.parametrize(("write_price", "expected"), [("0", 77), ("0.00066", 275)])
def test_bedrock_settles_verified_cache_reads_and_writes(
    tmp_path: Path, write_price: str, expected: int
) -> None:
    rates = load_fixture_rates(
        tmp_path,
        model_id="us.amazon.nova-2-lite-v1:0",
        region="us-east-1",
        input_usd_per_1000="0.00033",
        output_usd_per_1000="0.00275",
        cached_input_usd_per_1000="0.0000825",
        cache_write_usd_per_1000=write_price,
        source_version="20261111013037",
    )
    assert verified_cost(bedrock_response(), rates) == expected
    if write_price != "0":
        assert rates.reservation_microdollars == 54_518


@pytest.mark.parametrize(
    "missing", ["cached_input_usd_per_1000", "cache_write_usd_per_1000"]
)
def test_bedrock_unpriced_used_cache_retains_maximum(
    tmp_path: Path, missing: str
) -> None:
    rates = load_fixture_rates(
        tmp_path,
        model_id="us.amazon.nova-2-lite-v1:0",
        region="us-east-1",
        **{missing: None},
    )
    assert verified_cost(bedrock_response(), rates) is None
    assert (
        verified_cost(
            bedrock_response(cacheReadInputTokens=0, cacheWriteInputTokens=0), rates
        )
        == 120
    )


@pytest.mark.parametrize("total", [110, 610, 109, True, -1, "610"])
def test_bedrock_conflicting_cache_totals_remain_unknown(
    tmp_path: Path, total: object
) -> None:
    rates = load_fixture_rates(
        tmp_path, model_id="us.amazon.nova-2-lite-v1:0", region="us-east-1"
    )
    assert verified_cost(bedrock_response(totalTokens=total), rates) is None
    assert (
        verified_cost(
            bedrock_response(
                cacheReadInputTokens=0, cacheWriteInputTokens=0, totalTokens=110
            ),
            rates,
        )
        == 120
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"cacheWriteInputTokens": True},
        {"cacheWriteInputTokens": -1},
        {"cacheWriteInputTokens": "300"},
        {"cacheWriteInputTokens": MAX_INPUT_TOKENS},
        {"cacheReadInputTokens": MAX_INPUT_TOKENS},
        {"inputTokens": MAX_INPUT_TOKENS},
    ],
)
def test_bedrock_invalid_cache_counts_remain_unknown(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    rates = load_fixture_rates(
        tmp_path, model_id="us.amazon.nova-2-lite-v1:0", region="us-east-1"
    )
    assert verified_cost(bedrock_response(**changes), rates) is None
