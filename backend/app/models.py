"""SQLAlchemy models for the FEWIA schema."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MONEY = Numeric(12, 2)
SMALL = Numeric(5, 2)


class User(Base):
    """A person who owns daily observations."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyFinance(Base):
    """Daily financial context for one user."""

    __tablename__ = "daily_finance"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    grocery_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    restaurant_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    transportation_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fitness_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discretionary_spending: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_flow: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class DailyEnvironment(Base):
    """Daily environmental context for one user."""

    __tablename__ = "daily_environment"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    park_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gym_count: Mapped[int] = mapped_column(Integer, nullable=False)
    grocery_store_count: Mapped[int] = mapped_column(Integer, nullable=False)
    restaurant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    location_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class DailyHealth(Base):
    """Daily activity and health observations for one user."""

    __tablename__ = "daily_health"
    __table_args__ = (CheckConstraint("steps >= 0", name="ck_daily_health_steps"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    resting_heart_rate: Mapped[Decimal | None] = mapped_column(SMALL, nullable=True)
    sleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intensity_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stress_score: Mapped[Decimal | None] = mapped_column(SMALL, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class ModelRun(Base):
    """One trained model and its measured metrics."""

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    feature_set: Mapped[str] = mapped_column(Text, nullable=False)
    data_version: Mapped[str] = mapped_column(Text, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    mae: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    rmse: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    r_squared: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prediction(Base):
    """One predicted step count from one model run."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("model_runs.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_steps: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    actual_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
