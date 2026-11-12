"""Shared fixtures for deterministic tool tests."""

import ast
import os
from collections.abc import Collection, Iterator, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NoReturn, Protocol

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.agent import ingredient_tool
from app.db import Base
from app.deps import get_session
from app.main import app

_JOB_TEST_DATABASE_URL = "FEWIA_JOB_TEST_DATABASE_URL"
_REQUIRE_DB = "FEWIA_REQUIRE_DB"
_DATABASE_HELPER = "require_test_database_url"
_EVALUATION_DATABASE_URL = "FEWIA_EVALUATION_DATABASE_URL"
_DATABASE_NAMES = (_DATABASE_HELPER, _JOB_TEST_DATABASE_URL, _EVALUATION_DATABASE_URL)
DATABASE_XDIST_GROUP = "database"
# These modules name the database but never connect to it.
NO_DATABASE_MODULES = frozenset(
    {
        "test_openai_compose_launcher",
        "test_evaluation_cli_config",
        "test_cloud_database_config",
        "test_database_gate",
        "test_xdist_groups",
    }
)
_database_skip_count = 0


def _skip_or_fail_test_database(message: str) -> NoReturn:
    """Skip the test, or fail it when FEWIA_REQUIRE_DB equals 1."""
    if os.environ.get(_REQUIRE_DB) == "1":
        pytest.fail(f"{_REQUIRE_DB}=1 requires {_JOB_TEST_DATABASE_URL}. {message}")
    pytest.skip(message)


def require_test_database_url() -> str:
    """Give FEWIA_JOB_TEST_DATABASE_URL, or skip or fail the test."""
    url = os.environ.get(_JOB_TEST_DATABASE_URL)
    if url:
        return url
    _skip_or_fail_test_database(
        "Set FEWIA_JOB_TEST_DATABASE_URL to an isolated migrated PostgreSQL."
    )


def uses_test_database(source: str) -> bool:
    """Tell whether test module source names the shared test database."""
    return any(name in source for name in _DATABASE_NAMES)


def _last_part(dotted_name: str) -> str:
    return dotted_name.rpartition(".")[2]


def _plugin_names(statement: ast.stmt) -> set[str]:
    targets: Sequence[ast.expr]
    if isinstance(statement, ast.Assign):
        targets, value = statement.targets, statement.value
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        targets, value = [statement.target], statement.value
    else:
        return set()
    if not any(
        isinstance(target, ast.Name) and target.id == "pytest_plugins"
        for target in targets
    ):
        return set()
    return {
        _last_part(node.value)
        for node in ast.walk(value)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def module_dependencies(source: str) -> frozenset[str]:
    """Give the last dotted part of every module, name, and plugin source loads."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(_last_part(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(_last_part(node.module))
            names.update(alias.name for alias in node.names)
    for statement in tree.body:
        names.update(_plugin_names(statement))
    return frozenset(names)


def database_modules(sources: Mapping[str, str]) -> frozenset[str]:
    """Give the module stems that reach the shared test database.

    A module reaches it when it names the database or depends, directly or
    through other modules, on one that does. Stems in NO_DATABASE_MODULES stay out.
    """
    dependencies = {
        stem: module_dependencies(source) for stem, source in sources.items()
    }
    members = {
        stem
        for stem, source in sources.items()
        if uses_test_database(source) and stem not in NO_DATABASE_MODULES
    }
    added = True
    while added:
        added = False
        for stem, stem_dependencies in dependencies.items():
            if stem in members or stem in NO_DATABASE_MODULES:
                continue
            if not stem_dependencies.isdisjoint(members):
                members.add(stem)
                added = True
    return frozenset(members)


def _read_test_sources() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in Path(__file__).resolve().parent.glob("test_*.py")
    }


def mark_database_items(
    items: Sequence[pytest.Item], sources: Mapping[str, str]
) -> None:
    """Add the database xdist group to each item from a module that reaches it."""
    members = database_modules(sources)
    for item in items:
        if item.path.stem in members:
            item.add_marker(pytest.mark.xdist_group(DATABASE_XDIST_GROUP))


def _runs_distributed(config: pytest.Config) -> bool:
    """Tell whether this process is an xdist worker or the xdist controller."""
    if hasattr(config, "workerinput"):
        return True
    return bool(config.getoption("numprocesses", None))


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Keep every test that uses the shared PostgreSQL on one xdist worker.

    Runs first so the marker exists when xdist appends the group to node ids.
    One process has no groups to keep, so it reads no test file.
    """
    if not _runs_distributed(config):
        return
    mark_database_items(items, _read_test_sources())


def skip_or_fail_unreachable_test_database(error: BaseException) -> NoReturn:
    """Skip or fail when the test database does not answer."""
    _skip_or_fail_test_database(
        "No database answers at FEWIA_JOB_TEST_DATABASE_URL. Start Postgres with "
        "`docker compose up -d postgres` and run `uv run alembic upgrade head`. "
        f"Driver said: {error.__class__.__name__}."
    )


def _database_skip_reason(report: pytest.TestReport) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) >= 3:
        return str(longrepr[2])
    return str(longrepr)


def pytest_sessionstart(session: pytest.Session) -> None:
    global _database_skip_count
    _database_skip_count = 0
    _ = session


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global _database_skip_count
    if report.when != "setup" or not report.skipped:
        return
    if _JOB_TEST_DATABASE_URL in _database_skip_reason(report):
        _database_skip_count += 1


def pytest_terminal_summary(
    terminalreporter: object, exitstatus: int, config: pytest.Config
) -> None:
    if _database_skip_count <= 0:
        return
    write_line = getattr(terminalreporter, "write_line", print)
    write_line(
        "FEWIA: "
        f"{_database_skip_count} database tests skipped; "
        "set FEWIA_JOB_TEST_DATABASE_URL to run them"
    )


class UserSeeder(Protocol):
    """Seed one user and return its ID."""

    def __call__(self, user_id: int = 1, display_name: str = "Test user") -> int: ...


class RowSeeder(Protocol):
    """Seed a range of daily rows and return the inserted dates."""

    def __call__(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]: ...


DailyRowType = (
    type[models.DailyHealth] | type[models.DailyFinance] | type[models.DailyEnvironment]
)


def _days(start_date: date, end_date: date) -> Iterator[date]:
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def _seed_rows(
    session: Session,
    row_type: DailyRowType,
    defaults: Mapping[str, object],
    user_id: int,
    start_date: date,
    end_date: date,
    *,
    skip_days: Collection[date] = (),
    null_fields: Collection[str] = (),
    source: str = "synthetic-v1",
    overrides: Mapping[str, object] | None = None,
) -> list[date]:
    inserted_dates: list[date] = []
    for observation_date in _days(start_date, end_date):
        if observation_date in skip_days:
            continue
        values: dict[str, object] = {
            "user_id": user_id,
            "observation_date": observation_date,
            "source": source,
            **defaults,
        }
        for field_name in null_fields:
            values[field_name] = None
        if overrides is not None:
            values.update(overrides)
        session.add(row_type(**values))
        inserted_dates.append(observation_date)
    session.flush()
    return inserted_dates


@pytest.fixture(autouse=True)
def _no_live_usda(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test off the network, even with FEWIA_USDA_FDC_KEY_FILE set."""
    monkeypatch.setattr(ingredient_tool, "_live_client", lambda: None)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Give the suite one in-memory SQLite engine."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Give each test a session that rolls back its rows."""
    connection: Connection = engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    """Give each test a client that uses its database session."""

    def get_test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app, base_url="http://localhost") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def seed_user(session: Session) -> UserSeeder:
    """Give tests a user factory."""

    def seed(user_id: int = 1, display_name: str = "Test user") -> int:
        session.add(models.User(id=user_id, display_name=display_name))
        session.flush()
        return user_id

    return seed


@pytest.fixture()
def seed_health(session: Session) -> RowSeeder:
    """Give tests a daily health row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "steps": 8000,
            "resting_heart_rate": Decimal("60.00"),
            "sleep_minutes": 420,
            "intensity_minutes": 30,
            "stress_score": Decimal("25.00"),
        }
        return _seed_rows(
            session,
            models.DailyHealth,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed


@pytest.fixture()
def seed_finance(session: Session) -> RowSeeder:
    """Give tests a daily finance row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "total_spending": Decimal("100.00"),
            "grocery_spending": Decimal("40.00"),
            "restaurant_spending": Decimal("20.00"),
            "transportation_spending": Decimal("15.00"),
            "fitness_spending": Decimal("10.00"),
            "discretionary_spending": Decimal("15.00"),
            "cash_flow": Decimal("50.00"),
        }
        return _seed_rows(
            session,
            models.DailyFinance,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed


@pytest.fixture()
def seed_environment(session: Session) -> RowSeeder:
    """Give tests a daily environment row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "park_count": 2,
            "gym_count": 1,
            "grocery_store_count": 3,
            "restaurant_count": 5,
            "location_type": "urban",
        }
        return _seed_rows(
            session,
            models.DailyEnvironment,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed
