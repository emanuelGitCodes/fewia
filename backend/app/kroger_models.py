"""SQLAlchemy model for the encrypted Kroger customer tokens."""

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class KrogerCustomerToken(Base):
    """One row per user. Both tokens are Fernet ciphertext, never plaintext."""

    __tablename__ = "kroger_customer_tokens"

    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), primary_key=True
    )
    connection_version: Mapped[UUID] = mapped_column(
        sa.Uuid, nullable=False, default=uuid4, server_default=sa.func.gen_random_uuid()
    )
    access_token: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    refresh_token: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
