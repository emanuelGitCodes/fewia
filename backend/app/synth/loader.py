"""Load synthetic records into the database."""

from sqlalchemy.orm import Session

from app.models import DailyEnvironment, DailyFinance, DailyHealth, User
from app.synth.records import PROFILES, Dataset


def load(session: Session, dataset: Dataset) -> None:
    """Load one dataset and replace rows with matching primary keys."""

    for profile in PROFILES:
        session.merge(User(id=profile.user_id, display_name=profile.display_name))
    for finance_row in dataset.finance:
        session.merge(DailyFinance(**vars(finance_row), source=dataset.data_version))
    for environment_row in dataset.environment:
        session.merge(
            DailyEnvironment(**vars(environment_row), source=dataset.data_version)
        )
    for health_row in dataset.health:
        session.merge(DailyHealth(**vars(health_row), source=dataset.data_version))
