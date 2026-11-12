"""Check identity and transient security records with synthetic values."""

from datetime import datetime
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from psycopg.types.json import Json
from sqlalchemy.orm import Session

from app.kroger_models import KrogerCustomerToken
from app.models import User
from app.security_models import KrogerOwner, SecurityIntent
from tests.test_runtime_database_policy import PgConnection

pytest_plugins: list[str] = ["tests.test_runtime_database_policy"]


def test_user_identity_metadata() -> None:
    table = User.__table__
    assert table.c.auth_issuer.nullable is True
    assert table.c.auth_subject.nullable is True
    assert table.c.workspace_id.nullable is False
    assert isinstance(table.c.workspace_id.type, sa.Uuid)
    assert str(table.c.workspace_id.server_default.arg) == "gen_random_uuid()"
    assert table.c.status.nullable is False
    assert str(table.c.status.server_default.arg) == "'active'"
    constraints = {constraint.name: constraint for constraint in table.constraints}
    assert {"ck_users_auth_identity_pair", "ck_users_status"} <= constraints.keys()
    unique = constraints["uq_users_auth_identity"]
    assert isinstance(unique, sa.UniqueConstraint)
    assert list(unique.columns.keys()) == ["auth_issuer", "auth_subject"]


def test_security_metadata_has_named_keys_and_lookup_index() -> None:
    for model in (KrogerOwner, SecurityIntent):
        table = model.__table__
        assert table.primary_key.name == f"pk_{table.name}"
        assert {fk.target_fullname for fk in table.foreign_keys} == {"users.id"}
        assert all(constraint.name is not None for constraint in table.constraints)
        assert table.c.updated_at.type.timezone is True
        assert table.c.updated_at.server_default is not None
    assert list(KrogerOwner.__table__.primary_key.columns.keys()) == ["user_id"]
    assert list(SecurityIntent.__table__.primary_key.columns.keys()) == ["id"]
    table = SecurityIntent.__table__
    assert {index.name: list(index.columns.keys()) for index in table.indexes} == {
        "ix_security_intents_user_kind_expires": ["user_id", "kind", "expires_at"]
    }
    assert table.c.created_at.type.timezone is True
    assert table.c.expires_at.type.timezone is True
    assert table.c.expires_at.nullable is False
    unique = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    )
    assert unique.name == "uq_security_intents_kind_digest"
    assert list(unique.columns.keys()) == ["kind", "digest"]


def test_orm_user_defaults_leave_identity_unclaimed(session: Session) -> None:
    users = [
        User(id=987654321 + index, display_name="Synthetic user") for index in range(2)
    ]
    session.add_all(users)
    session.flush()
    assert all(user.auth_issuer is None and user.auth_subject is None for user in users)
    assert all(user.status == "active" for user in users)
    assert all(isinstance(user.workspace_id, UUID) for user in users)
    assert users[0].workspace_id != users[1].workspace_id


def test_orm_user_preserves_explicit_workspace_and_status(session: Session) -> None:
    workspace_id = uuid4()
    user = User(
        id=987654321,
        display_name="Synthetic disabled user",
        workspace_id=workspace_id,
        status="disabled",
    )
    session.add(user)
    session.flush()
    session.refresh(user)
    assert user.workspace_id == workspace_id
    assert user.status == "disabled"


def test_connection_version_defaults_never_rotate_on_update() -> None:
    for column in (
        KrogerCustomerToken.__table__.c.connection_version,
        KrogerOwner.__table__.c.pairing_generation,
    ):
        assert isinstance(column.type, sa.Uuid)
        assert column.nullable is False
        assert column.default is not None
        assert str(column.server_default.arg) == "gen_random_uuid()"
        assert column.onupdate is None
        assert column.server_onupdate is None


@pytest.mark.parametrize(
    ("issuer", "subject", "status", "constraint"),
    [
        ("https://issuer.example", None, "active", "ck_users_auth_identity_pair"),
        (None, "synthetic-subject", "active", "ck_users_auth_identity_pair"),
        (None, None, "unknown", "ck_users_status"),
    ],
)
def test_postgres_user_constraints(
    admin: PgConnection,
    issuer: str | None,
    subject: str | None,
    status: str,
    constraint: str,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        with admin.transaction():
            admin.execute(
                "INSERT INTO users "
                "(id, display_name, auth_issuer, auth_subject, status) "
                "VALUES (987654321, 'Synthetic user', %s, %s, %s)",
                (issuer, subject, status),
            )
    assert caught.value.diag.constraint_name == constraint


def test_postgres_user_identity_pair_is_unique_and_nullable(
    admin: PgConnection,
) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name, status) VALUES "
        "(987654321, 'Synthetic unclaimed', 'active'), "
        "(987654322, 'Synthetic disabled', 'disabled'), "
        "(987654323, 'Synthetic deleting', 'deleting')"
    )
    row = admin.execute(
        "INSERT INTO users (id, display_name, auth_issuer, auth_subject) VALUES "
        "(987654324, 'Synthetic claimed', 'https://issuer.example', 'subject') "
        "RETURNING workspace_id, status"
    ).fetchone()
    assert row is not None and isinstance(row[0], UUID) and row[1] == "active"
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        with admin.transaction():
            admin.execute(
                "INSERT INTO users (id, display_name, auth_issuer, auth_subject) "
                "VALUES (987654325, 'Synthetic duplicate', "
                "'https://issuer.example', 'subject')"
            )
    assert caught.value.diag.constraint_name == "uq_users_auth_identity"
    admin.execute(
        "INSERT INTO users (id, display_name, auth_issuer, auth_subject) VALUES "
        "(987654326, 'Synthetic other issuer', 'https://other.example', 'subject')"
    )


@pytest.mark.parametrize(
    ("kind", "digest", "details", "state", "constraint"),
    [
        ("unknown", "a" * 64, {}, "pending", "ck_security_intents_kind"),
        ("oauth_start", "A" * 64, {}, "pending", "ck_security_intents_digest_sha256"),
        ("oauth_start", "a" * 63, {}, "pending", "ck_security_intents_digest_sha256"),
        ("oauth_start", "g" * 64, {}, "pending", "ck_security_intents_digest_sha256"),
        ("oauth_start", "a" * 65, {}, "pending", "ck_security_intents_digest_sha256"),
        (
            "oauth_start",
            "a" * 64 + "\n",
            {},
            "pending",
            "ck_security_intents_digest_sha256",
        ),
        ("oauth_start", "a" * 64, [], "pending", "ck_security_intents_details_object"),
        (
            "oauth_start",
            "a" * 64,
            None,
            "pending",
            "ck_security_intents_details_object",
        ),
        (
            "oauth_start",
            "a" * 64,
            "value",
            "pending",
            "ck_security_intents_details_object",
        ),
        ("oauth_start", "a" * 64, {}, "unknown", "ck_security_intents_state"),
    ],
)
def test_postgres_security_intent_constraints(
    admin: PgConnection,
    kind: str,
    digest: str,
    details: object,
    state: str,
    constraint: str,
) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES (987654321, 'Synthetic owner')"
    )
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        with admin.transaction():
            admin.execute(
                "INSERT INTO security_intents "
                "(user_id, kind, digest, details, state, expires_at) "
                "VALUES (987654321, %s, %s, %s, %s, now() + interval '1 minute')",
                (kind, digest, Json(details), state),
            )
    assert caught.value.diag.constraint_name == constraint


def test_postgres_security_intent_uniqueness_and_defaults(admin: PgConnection) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES "
        "(987654321, 'Synthetic owner'), (987654322, 'Synthetic other owner')"
    )
    statement = (
        "INSERT INTO security_intents (user_id, kind, digest, expires_at) "
        "VALUES (%s, %s, %s, now() + interval '1 minute') "
        "RETURNING id, details, state, created_at, updated_at"
    )
    first = admin.execute(statement, (987654321, "oauth_start", "b" * 64)).fetchone()
    assert first is not None
    assert isinstance(first[0], UUID)
    assert first[1:3] == ({}, "pending")
    assert all(isinstance(value, datetime) and value.tzinfo for value in first[3:])
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        with admin.transaction():
            admin.execute(statement, (987654322, "oauth_start", "b" * 64))
    assert caught.value.diag.constraint_name == "uq_security_intents_kind_digest"
    for kind in ("oauth_state", "pairing_ticket", "cart_confirmation"):
        other = admin.execute(statement, (987654321, kind, "b" * 64)).fetchone()
        assert other is not None and other[0] != first[0]


@pytest.mark.parametrize("table", ["kroger_owners", "security_intents"])
def test_postgres_security_records_require_existing_user(
    admin: PgConnection, table: str
) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as caught:
        with admin.transaction():
            if table == "kroger_owners":
                admin.execute("INSERT INTO kroger_owners (user_id) VALUES (987654321)")
            else:
                admin.execute(
                    "INSERT INTO security_intents "
                    "(id, user_id, kind, digest, expires_at) "
                    "VALUES (%s, 987654321, 'oauth_state', %s, now())",
                    (uuid4(), "c" * 64),
                )
    assert caught.value.diag.constraint_name == f"fk_{table}_user_id"


def test_postgres_token_refresh_preserves_connection_version(
    admin: PgConnection,
) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES "
        "(987654321, 'Synthetic connection'), (987654322, 'Synthetic other connection')"
    )
    versions = admin.execute(
        "INSERT INTO kroger_customer_tokens "
        "(user_id, access_token, refresh_token, access_expires_at) VALUES "
        "(987654321, %s, %s, now()), (987654322, %s, %s, now()) "
        "RETURNING user_id, connection_version",
        (b"synthetic-ciphertext",) * 4,
    ).fetchall()
    assert all(isinstance(row[1], UUID) for row in versions)
    assert versions[0][1] != versions[1][1]
    original = dict(versions)[987654321]
    assert admin.execute(
        "UPDATE kroger_customer_tokens SET access_token = %s, refresh_token = %s, "
        "access_expires_at = now() + interval '1 hour', updated_at = now() "
        "WHERE user_id = 987654321 RETURNING connection_version",
        (b"synthetic-refreshed-ciphertext",) * 2,
    ).fetchone() == (original,)
    replacement = uuid4()
    assert admin.execute(
        "UPDATE kroger_customer_tokens SET connection_version = %s "
        "WHERE user_id = 987654321 RETURNING connection_version",
        (replacement,),
    ).fetchone() == (replacement,)
    assert replacement != original
