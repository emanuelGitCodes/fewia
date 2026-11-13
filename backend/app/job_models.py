"""SQLAlchemy models for durable jobs and their outbox records."""

from datetime import datetime
from typing import Protocol, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from app import job_effect_models  # noqa: F401
from app.db import Base


class _DefaultParameters(Protocol):
    def get_current_parameters(
        self, isolate_multiinsert_groups: bool = True
    ) -> dict[str, object]: ...


def _request_namespace(context: DefaultExecutionContext) -> str:
    parameters = cast(_DefaultParameters, context).get_current_parameters()
    if parameters.get("kind") == "sync":
        return "sync"
    payload = parameters.get("payload")
    if isinstance(payload, dict) and payload.get("operation") == "chat":
        return "chat"
    return "plan"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        sa.UniqueConstraint("id", "user_id", name="uq_jobs_id_user"),
        sa.CheckConstraint("kind IN ('sync', 'agent')", name="ck_jobs_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts"),
        sa.CheckConstraint(
            "request_namespace IN ('plan', 'chat', 'sync')",
            name="ck_jobs_request_namespace",
        ),
        sa.CheckConstraint(
            sa.column("request_namespace")
            == sa.case(
                (sa.column("kind") == "sync", "sync"),
                (
                    sa.column("payload", sa.JSON)["operation"].as_string() == "chat",
                    "chat",
                ),
                else_="plan",
            ),
            name="ck_jobs_namespace_matches_payload",
        ),
        sa.UniqueConstraint(
            "user_id",
            "kind",
            "request_namespace",
            "request_key",
            name="uq_jobs_user_kind_namespace_request_key",
        ),
        sa.Index("ix_jobs_status_lease", "status", "lease_expires_at"),
        sa.Index("ix_jobs_user_status_lease", "user_id", "status", "lease_expires_at"),
        sa.Index("ix_jobs_user_kind_created", "user_id", "kind", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    request_namespace: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        default=_request_namespace,
        server_default=sa.text("'plan'"),
    )
    request_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=sa.text("'queued'")
    )
    payload: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(sa.JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    lease_token: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class JobOutbox(Base):
    __tablename__ = "job_outbox"
    __table_args__ = (
        sa.UniqueConstraint("job_id", name="uq_job_outbox_job_id"),
        sa.Index("ix_job_outbox_published_at", "published_at"),
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("jobs.id"), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
