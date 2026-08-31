from datetime import date, timedelta
from decimal import Decimal

from app.synth import DATA_VERSION, PROFILES, Dataset, HealthRow, generate

END_DATE = date(2026, 6, 30)
DAYS = 90


def _dataset(seed: int) -> Dataset:
    return generate(seed=seed, days=DAYS, end_date=END_DATE)


def _health_mean(rows: tuple[HealthRow, ...], user_id: int) -> float:
    steps = [row.steps for row in rows if row.user_id == user_id]
    return sum(steps) / len(steps)


def _discretionary_mean(dataset: Dataset, user_id: int) -> float:
    spending = [
        float(row.discretionary_spending)
        for row in dataset.finance
        if row.user_id == user_id
    ]
    return sum(spending) / len(spending)


def test_generate_is_reproducible() -> None:
    assert _dataset(42) == _dataset(42)


def test_different_seeds_produce_different_datasets() -> None:
    assert _dataset(42) != _dataset(43)


def test_row_counts_and_missing_health_share() -> None:
    dataset = _dataset(42)
    expected_rows = DAYS * len(PROFILES)
    missing_share = (expected_rows - len(dataset.health)) / expected_rows

    assert len(dataset.finance) == expected_rows
    assert len(dataset.environment) == expected_rows
    assert len(dataset.health) < expected_rows
    assert 0.02 <= missing_share <= 0.10


def test_profiles_cross_discretionary_and_activity_levels() -> None:
    assert {
        (profile.discretionary_level, profile.activity_level) for profile in PROFILES
    } == {
        ("low", "high"),
        ("high", "high"),
        ("high", "low"),
        ("low", "low"),
    }


def test_weekend_steps_are_measurably_lower_than_weekday_steps() -> None:
    health = _dataset(42).health
    weekend_steps = [row.steps for row in health if row.observation_date.weekday() >= 5]
    weekday_steps = [row.steps for row in health if row.observation_date.weekday() < 5]

    assert (
        sum(weekday_steps) / len(weekday_steps)
        - sum(weekend_steps) / len(weekend_steps)
        > 500
    )


def test_profiles_drive_steps_and_discretionary_spending() -> None:
    dataset = _dataset(42)
    step_means = {
        profile.user_id: _health_mean(dataset.health, profile.user_id)
        for profile in PROFILES
    }
    discretionary_means = {
        profile.user_id: _discretionary_mean(dataset, profile.user_id)
        for profile in PROFILES
    }
    high_activity = [
        profile.user_id for profile in PROFILES if profile.activity_level == "high"
    ]
    low_activity = [
        profile.user_id for profile in PROFILES if profile.activity_level == "low"
    ]
    high_discretionary = [
        profile.user_id for profile in PROFILES if profile.discretionary_level == "high"
    ]
    low_discretionary = [
        profile.user_id for profile in PROFILES if profile.discretionary_level == "low"
    ]

    assert min(step_means[user_id] for user_id in high_activity) > max(
        step_means[user_id] for user_id in low_activity
    )
    assert min(discretionary_means[user_id] for user_id in high_discretionary) > max(
        discretionary_means[user_id] for user_id in low_discretionary
    )
    assert tuple(sorted(step_means, key=step_means.get, reverse=True)) != tuple(
        sorted(discretionary_means, key=discretionary_means.get, reverse=True)
    )


def test_step_and_spending_outliers_are_present_and_rare() -> None:
    dataset = _dataset(42)
    step_means = {
        profile.user_id: _health_mean(dataset.health, profile.user_id)
        for profile in PROFILES
    }
    discretionary_means = {
        profile.user_id: _discretionary_mean(dataset, profile.user_id)
        for profile in PROFILES
    }
    step_outliers = [
        row for row in dataset.health if row.steps > step_means[row.user_id] + 3_000
    ]
    spending_outliers = [
        row
        for row in dataset.finance
        if float(row.discretionary_spending) > discretionary_means[row.user_id] + 80
    ]

    assert 0 < len(step_outliers) / len(dataset.health) < 0.05
    assert 0 < len(spending_outliers) / len(dataset.finance) < 0.05


def test_nullable_health_columns_have_missing_and_present_values() -> None:
    health = _dataset(42).health
    columns = (
        [row.resting_heart_rate for row in health],
        [row.sleep_minutes for row in health],
        [row.intensity_minutes for row in health],
        [row.stress_score for row in health],
    )

    for values in columns:
        assert any(value is None for value in values)
        assert any(value is not None for value in values)


def test_money_precision_and_step_bounds() -> None:
    dataset = _dataset(42)
    for row in dataset.finance:
        money = (
            row.total_spending,
            row.grocery_spending,
            row.restaurant_spending,
            row.transportation_spending,
            row.fitness_spending,
            row.discretionary_spending,
            row.cash_flow,
        )
        assert all(
            isinstance(value, Decimal) and value.as_tuple().exponent == -2
            for value in money
        )
        assert all(abs(value) <= Decimal("9999999999.99") for value in money)
        assert all(value >= 0 for value in money[:-1])
    for row in dataset.health:
        assert row.steps >= 0
        for value in (row.resting_heart_rate, row.stress_score):
            assert value is None or value.as_tuple().exponent == -2
            assert value is None or value <= Decimal("999.99")


def test_dates_cover_the_requested_calendar_range() -> None:
    dataset = _dataset(42)
    dates = {row.observation_date for row in dataset.finance}

    assert dataset.data_version == DATA_VERSION
    assert min(dates) == END_DATE - timedelta(days=DAYS - 1)
    assert max(dates) == END_DATE
