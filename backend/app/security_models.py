"""Ownership generations, hashed security intents, and quota counters."""

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class KrogerOwner(Base):
    """The current pairing generation for one user."""

    __tablename__ = "kroger_owners"
    __table_args__ = (
        sa.PrimaryKeyConstraint("user_id", name="pk_kroger_owners"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_kroger_owners_user_id"
        ),
    )

    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    pairing_generation: Mapped[UUID] = mapped_column(
        sa.Uuid, nullable=False, default=uuid4, server_default=sa.func.gen_random_uuid()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SecurityIntent(Base):
    """A nonce digest and bounded security metadata.

    Details MUST contain only nonce hashes, generations, versions, hashes,
    and bounded outcome codes. Details MUST NOT contain raw credentials,
    tickets, OAuth values, or provider product payloads.
    """

    __tablename__ = "security_intents"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="pk_security_intents"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_security_intents_user_id"
        ),
        sa.CheckConstraint(
            "kind IN ('pairing_ticket', 'oauth_start', 'oauth_state', "
            "'cart_confirmation')",
            name="ck_security_intents_kind",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_security_intents_digest_sha256"
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "json_typeof(details) = 'object'", name="ck_security_intents_details_object"
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "state IN ('pending', 'claimed', 'consumed', 'succeeded', "
            "'failed', 'uncertain')",
            name="ck_security_intents_state",
        ),
        sa.UniqueConstraint("kind", "digest", name="uq_security_intents_kind_digest"),
        sa.Index(
            "ix_security_intents_user_kind_expires", "user_id", "kind", "expires_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        sa.Uuid, nullable=False, default=uuid4, server_default=sa.func.gen_random_uuid()
    )
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    digest: Mapped[str] = mapped_column(sa.Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        sa.JSON, nullable=False, default=dict, server_default=sa.text("'{}'")
    )
    state: Mapped[str] = mapped_column(
        sa.Text, nullable=False, default="pending", server_default=sa.text("'pending'")
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class QuotaCounter(Base):
    """Count admitted actions within one UTC minute."""

    __tablename__ = "quota_counters"
    __table_args__ = (
        sa.PrimaryKeyConstraint(
            "action", "scope", "scope_key", "minute_start", name="pk_quota_counters"
        ),
        sa.CheckConstraint(
            "(action = 'mutation' AND scope = 'user' AND scope_key > 0) OR "
            "(action = 'retailer' AND ((scope = 'global' AND scope_key = 0) OR "
            "(scope = 'user' AND scope_key > 0)))",
            name="ck_quota_counters_action_scope_key",
        ),
        sa.CheckConstraint("count > 0", name="ck_quota_counters_count_positive"),
        sa.CheckConstraint(
            "expires_at > minute_start", name="ck_quota_counters_expiry"
        ),
        sa.Index("ix_quota_counters_expires_at", "expires_at"),
    )

    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scope: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scope_key: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    minute_start: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
