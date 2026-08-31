"""Load synthetic records into the database."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import DailyEnvironment, DailyFinance, DailyHealth, User
from app.synth.records import PROFILES, Dataset


def load(session: Session, dataset: Dataset) -> None:
    """Load one dataset and replace rows with matching primary keys."""

    for profile in PROFILES:
        session.merge(User(id=profile.user_id, display_name=profile.display_name))
    session.flush()
    session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('users', 'id'), "
            "(SELECT max(id) FROM users), true)"
        )
    )
    for finance_row in dataset.finance:
        session.merge(
            DailyFinance(
                user_id=finance_row.user_id,
                observation_date=finance_row.observation_date,
                total_spending=finance_row.total_spending,
                grocery_spending=finance_row.grocery_spending,
                restaurant_spending=finance_row.restaurant_spending,
                transportation_spending=finance_row.transportation_spending,
                fitness_spending=finance_row.fitness_spending,
                discretionary_spending=finance_row.discretionary_spending,
                cash_flow=finance_row.cash_flow,
                source=dataset.data_version,
            )
        )
    for environment_row in dataset.environment:
        session.merge(
            DailyEnvironment(
                user_id=environment_row.user_id,
                observation_date=environment_row.observation_date,
                park_count=environment_row.park_count,
                gym_count=environment_row.gym_count,
                grocery_store_count=environment_row.grocery_store_count,
                restaurant_count=environment_row.restaurant_count,
                location_type=environment_row.location_type,
                source=dataset.data_version,
            )
        )
    for health_row in dataset.health:
        session.merge(
            DailyHealth(
                user_id=health_row.user_id,
                observation_date=health_row.observation_date,
                steps=health_row.steps,
                resting_heart_rate=health_row.resting_heart_rate,
                sleep_minutes=health_row.sleep_minutes,
                intensity_minutes=health_row.intensity_minutes,
                stress_score=health_row.stress_score,
                source=dataset.data_version,
            )
        )
