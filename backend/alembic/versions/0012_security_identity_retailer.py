from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_issuer", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("auth_subject", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'active'"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_users_auth_identity_pair",
        "users",
        "(auth_issuer IS NULL) = (auth_subject IS NULL)",
    )
    op.create_unique_constraint(
        "uq_users_auth_identity", "users", ["auth_issuer", "auth_subject"]
    )
    op.create_check_constraint(
        "ck_users_status", "users", "status IN ('active', 'disabled', 'deleting')"
    )
    op.add_column(
        "kroger_customer_tokens",
        sa.Column(
            "connection_version",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_table(
        "kroger_owners",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "pairing_generation",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_kroger_owners_user_id"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_kroger_owners"),
    )
    op.create_table(
        "security_intents",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "state", sa.Text(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('pairing_ticket', 'oauth_start', 'oauth_state', "
            "'cart_confirmation')",
            name="ck_security_intents_kind",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_security_intents_digest_sha256"
        ),
        sa.CheckConstraint(
            "json_typeof(details) = 'object'", name="ck_security_intents_details_object"
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'claimed', 'consumed', 'succeeded', "
            "'failed', 'uncertain')",
            name="ck_security_intents_state",
        ),
        sa.UniqueConstraint("kind", "digest", name="uq_security_intents_kind_digest"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_security_intents_user_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_intents"),
    )
    op.create_index(
        "ix_security_intents_user_kind_expires",
        "security_intents",
        ["user_id", "kind", "expires_at"],
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
