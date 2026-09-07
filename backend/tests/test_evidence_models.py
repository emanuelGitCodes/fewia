"""Tests for grocery evidence metadata and migration SQL compile."""

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import Base
from app.evidence_models import SHA256_HEX_ID, GroceryEvidence
from app.models import User

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND_ROOT / "alembic" / "versions" / "0007_add_grocery_evidence.py"
ENV_PATH = BACKEND_ROOT / "alembic" / "env.py"

FORBIDDEN_COLUMNS = {
    "access_token",
    "user_token",
    "raw_response",
    "provider_payload",
    "checkout_url",
    "order_id",
    "payment_token",
    "latest",
    "is_latest",
    "current_id",
}


def load_revision_0007() -> ModuleType:
    spec = importlib.util.spec_from_file_location("alembic_rev_0007", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grocery_evidence_columns_nullability_and_defaults() -> None:
    table = GroceryEvidence.__table__
    assert table.name == "grocery_evidence"
    assert set(table.columns.keys()) == {"id", "user_id", "snapshot", "created_at"}
    assert isinstance(table.c.id.type, Text)
    assert table.c.id.nullable is False
    assert table.c.id.default is None
    assert table.c.id.server_default is None
    assert isinstance(table.c.user_id.type, BigInteger)
    assert table.c.user_id.nullable is False
    assert isinstance(table.c.snapshot.type, JSON)
    assert table.c.snapshot.nullable is False
    assert isinstance(table.c.created_at.type, DateTime)
    assert table.c.created_at.type.timezone is True
    assert table.c.created_at.nullable is False
    assert table.c.created_at.server_default is not None
    assert FORBIDDEN_COLUMNS.isdisjoint(table.columns.keys())


def test_grocery_evidence_pk_fk_and_id_check() -> None:
    table = GroceryEvidence.__table__
    assert [column.name for column in table.primary_key.columns] == ["id"]
    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for foreign_key in constraint.elements
    }
    assert ("user_id", "users.id") in foreign_keys
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any(
        constraint.name == "ck_grocery_evidence_id_sha256"
        and str(constraint.sqltext) == SHA256_HEX_ID
        for constraint in checks
    )


def test_grocery_evidence_is_registered_on_base_metadata() -> None:
    assert GroceryEvidence.__tablename__ in Base.metadata.tables


def test_alembic_env_imports_evidence_models() -> None:
    source = ENV_PATH.read_text(encoding="utf-8")
    assert "evidence_models" in source


def test_create_table_sql_compiles_for_postgresql() -> None:
    compiled = str(
        CreateTable(GroceryEvidence.__table__).compile(dialect=postgresql.dialect())
    )
    assert "grocery_evidence" in compiled
    assert SHA256_HEX_ID in compiled
    assert "ck_grocery_evidence_id_sha256" in compiled


def test_sqlite_create_all_and_drop_all_with_user() -> None:
    # SQLite does not enforce the hex id CHECK.
    test_engine = create_engine("sqlite://")
    tables = [User.__table__, GroceryEvidence.__table__]
    try:
        Base.metadata.create_all(test_engine, tables=tables)
        table_names = set(inspect(test_engine).get_table_names())
        assert "users" in table_names
        assert "grocery_evidence" in table_names
        Base.metadata.drop_all(test_engine, tables=tables)
        table_names = set(inspect(test_engine).get_table_names())
        assert "users" not in table_names
        assert "grocery_evidence" not in table_names
    finally:
        test_engine.dispose()


def test_migration_0007_upgrade_sql_compiles_for_postgresql() -> None:
    module = load_revision_0007()
    assert module.revision == "0007"
    assert module.down_revision == "0006"
    buffer = StringIO()
    context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
    )
    with Operations.context(context):
        module.upgrade()
    sql = buffer.getvalue()
    assert "grocery_evidence" in sql
    assert SHA256_HEX_ID in sql
    assert "ck_grocery_evidence_id_sha256" in sql
    assert "fewia_grocery_evidence_immutable" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "RAISE EXCEPTION" in sql
    assert SHA256_HEX_ID in MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_0007_rejects_downgrade() -> None:
    module = load_revision_0007()
    with pytest.raises(RuntimeError, match="Forward-only"):
        module.downgrade()
