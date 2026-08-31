"""Synthetic dataset record types."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

DATA_VERSION: str = "synthetic-v1"


@dataclass(frozen=True)
class Profile:
    """A synthetic user profile."""

    user_id: int
    display_name: str
    discretionary_level: str
    activity_level: str


@dataclass(frozen=True)
class FinanceRow:
    """A daily financial record."""

    user_id: int
    observation_date: date
    total_spending: Decimal
    grocery_spending: Decimal
    restaurant_spending: Decimal
    transportation_spending: Decimal
    fitness_spending: Decimal
    discretionary_spending: Decimal
    cash_flow: Decimal


@dataclass(frozen=True)
class EnvironmentRow:
    """A daily environment record."""

    user_id: int
    observation_date: date
    park_count: int
    gym_count: int
    grocery_store_count: int
    restaurant_count: int
    location_type: str


@dataclass(frozen=True)
class HealthRow:
    """A daily health record."""

    user_id: int
    observation_date: date
    steps: int
    resting_heart_rate: Decimal | None
    sleep_minutes: int | None
    intensity_minutes: int | None
    stress_score: Decimal | None


@dataclass(frozen=True)
class Dataset:
    """A generated synthetic dataset."""

    seed: int
    days: int
    data_version: str
    finance: tuple[FinanceRow, ...]
    environment: tuple[EnvironmentRow, ...]
    health: tuple[HealthRow, ...]


PROFILES: tuple[Profile, ...] = (
    Profile(1, "Avery", "low", "high"),
    Profile(2, "Blair", "high", "high"),
    Profile(3, "Casey", "high", "low"),
    Profile(4, "Devon", "low", "low"),
)
