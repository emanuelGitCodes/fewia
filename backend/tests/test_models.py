"""Tests for the SQLAlchemy metadata. No database connection runs here."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app import models, plaid_models
from app.db import Base

EXPECTED_TABLES = {
    "users",
    "daily_finance",
    "daily_environment",
    "daily_health",
    "model_runs",
    "predictions",
    "jobs",
    "job_outbox",
    plaid_models.PlaidItem.__tablename__,
    plaid_models.PlaidTransaction.__tablename__,
}


def test_metadata_holds_the_application_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_daily_tables_use_a_composite_primary_key() -> None:
    for name in ("daily_finance", "daily_environment", "daily_health"):
        table = Base.metadata.tables[name]
        columns = [column.name for column in table.primary_key.columns]
        assert columns == ["user_id", "observation_date"]


def test_identity_tables_use_a_single_primary_key() -> None:
    for name in ("users", "model_runs", "predictions"):
        table = Base.metadata.tables[name]
        assert [column.name for column in table.primary_key.columns] == ["id"]


def test_daily_health_checks_that_steps_are_not_negative() -> None:
    table = Base.metadata.tables["daily_health"]
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("steps >= 0" in str(check.sqltext) for check in checks)


def test_daily_finance_money_columns_are_not_nullable() -> None:
    table = models.DailyFinance.__table__
    assert table.c.total_spending.nullable is False
    assert table.c.cash_flow.nullable is False


def test_model_runs_holds_training_metadata() -> None:
    table = models.ModelRun.__table__
    columns = set(table.columns.keys())
    assert {
        "model_version",
        "random_seed",
        "sample_size_train",
        "sample_size_test",
        "feature_list",
        "split_method",
        "missing_data_policy",
        "baseline_mae",
    } <= columns


def test_model_runs_model_version_is_unique() -> None:
    table = models.ModelRun.__table__
    constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert any(
        constraint.name == "uq_model_runs_model_version" for constraint in constraints
    )
