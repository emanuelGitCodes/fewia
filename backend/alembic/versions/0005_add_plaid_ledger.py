from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plaid_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_item_id", sa.Text(), nullable=False),
        sa.Column("credential_ref", sa.Text(), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_item_id", name="uq_plaid_items_provider_item_id"),
    )
    op.create_table(
        "plaid_transactions",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("pending", sa.Boolean(), nullable=False),
        sa.Column("pending_transaction_id", sa.Text(), nullable=True),
        sa.Column("is_grocery", sa.Boolean(), nullable=False),
        sa.Column("classification_version", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "currency = 'USD'", name="ck_plaid_transactions_currency_usd"
        ),
        sa.ForeignKeyConstraint(["item_id"], ["plaid_items.id"]),
        sa.PrimaryKeyConstraint("item_id", "transaction_id"),
    )
    op.create_index(
        "ix_plaid_transactions_item_date_pending",
        "plaid_transactions",
        ["item_id", "transaction_date", "pending"],
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
