"""Build seeded synthetic daily data."""

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.synth.records import (
    DATA_VERSION,
    PROFILES,
    Dataset,
    EnvironmentRow,
    FinanceRow,
    HealthRow,
)


def _quantize(value: float) -> Decimal:
    """Fit a value in the money column range."""

    return Decimal(str(min(9_999_999_999.99, max(-9_999_999_999.99, value)))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _nonnegative_decimal(rng: random.Random, value: float, deviation: float) -> Decimal:
    """Build a nonnegative two-decimal measurement."""

    return _quantize(min(999.99, max(0.0, rng.gauss(value, deviation))))


def _count(rng: random.Random, base: int, deviation: float = 1.0) -> int:
    """Build a nonnegative count."""

    return max(0, round(rng.gauss(base, deviation)))


def generate(*, seed: int, days: int, end_date: date) -> Dataset:
    """Generate daily synthetic data through end_date."""

    if days < 1:
        raise ValueError("days must be positive")
    rng = random.Random(seed)
    finance: list[FinanceRow] = []
    environment: list[EnvironmentRow] = []
    health: list[HealthRow] = []
    for offset in range(days):
        observation_date = end_date - timedelta(days=days - offset - 1)
        weekend = observation_date.weekday() >= 5
        for profile in PROFILES:
            urban = profile.user_id in (1, 3)
            discretionary = _nonnegative_decimal(
                rng, 42.0 if profile.discretionary_level == "high" else 16.0, 5.0
            )
            if rng.random() < 0.03:
                discretionary = _nonnegative_decimal(
                    rng, float(discretionary) + 125.0, 2.0
                )
            grocery = _nonnegative_decimal(rng, 20.0, 3.0)
            restaurant = _nonnegative_decimal(rng, 24.0 if weekend else 9.0, 4.0)
            transportation = _nonnegative_decimal(rng, 8.0 if urban else 4.0, 1.5)
            fitness = _nonnegative_decimal(
                rng, 4.0 if profile.activity_level == "high" else 1.5, 0.8
            )
            total = sum(
                (grocery, restaurant, transportation, fitness, discretionary), Decimal()
            )
            finance.append(
                FinanceRow(
                    user_id=profile.user_id,
                    observation_date=observation_date,
                    total_spending=total,
                    grocery_spending=grocery,
                    restaurant_spending=restaurant,
                    transportation_spending=transportation,
                    fitness_spending=fitness,
                    discretionary_spending=discretionary,
                    cash_flow=_quantize(rng.gauss(120.0 - float(total), 30.0)),
                )
            )
            park_count = _count(rng, 9 if urban else 4)
            gym_count = _count(rng, 5 if urban else 3)
            grocery_store_count = _count(rng, 8 if urban else 5)
            restaurant_count = _count(rng, 24 if urban else 11)
            environment.append(
                EnvironmentRow(
                    user_id=profile.user_id,
                    observation_date=observation_date,
                    park_count=park_count,
                    gym_count=gym_count,
                    grocery_store_count=grocery_store_count,
                    restaurant_count=restaurant_count,
                    location_type="urban" if urban else "suburban",
                )
            )
            if rng.random() < 0.05:
                continue
            base_steps = 8_000 if profile.activity_level == "high" else 4_000
            base_steps += (300 if urban else -200) - 900 * weekend
            steps = max(0, round(rng.gauss(base_steps, 850.0)))
            steps += rng.randint(4_000, 7_000) if rng.random() < 0.02 else 0
            health.append(
                HealthRow(
                    user_id=profile.user_id,
                    observation_date=observation_date,
                    steps=steps,
                    resting_heart_rate=(
                        None
                        if rng.random() < 0.1
                        else _nonnegative_decimal(rng, 62.0, 3.0)
                    ),
                    sleep_minutes=(
                        None if rng.random() < 0.1 else _count(rng, 430, 35.0)
                    ),
                    intensity_minutes=(
                        None if rng.random() < 0.1 else _count(rng, 45, 12.0)
                    ),
                    stress_score=(
                        None
                        if rng.random() < 0.1
                        else _nonnegative_decimal(rng, 45.0, 12.0)
                    ),
                )
            )
    return Dataset(
        seed, days, DATA_VERSION, tuple(finance), tuple(environment), tuple(health)
    )
