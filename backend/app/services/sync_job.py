from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.providers.plaid import PlaidNotReady, PlaidSyncMutation, PlaidUnavailable
from app.services.job_delivery import JobHandler, LeaseLost, RetryableJobError
from app.services.plaid_sync import SyncProvider, sync_item

_UNAVAILABLE = "The Plaid provider is unavailable."
_RETRY = "Plaid sync is retryable."
_DEMO_USER_ID = 1


class SyncJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["plaid_sync"] = "plaid_sync"
    item_id: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("item_id")
    @classmethod
    def validate_item_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("item_id is invalid")
        return value


def make_sync_handler(
    factory: sessionmaker[Session],
    provider: SyncProvider | None,
) -> JobHandler:
    def handle(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        parsed = SyncJobInput.model_validate(payload)
        if provider is None:
            raise ValueError(_UNAVAILABLE)
        try:
            count = sync_item(
                factory,
                parsed.item_id,
                provider,
                user_id=_DEMO_USER_ID,
                heartbeat=heartbeat,
            )
        except LeaseLost:
            raise
        except (PlaidUnavailable, PlaidNotReady, PlaidSyncMutation):
            pass
        else:
            return {"source": "plaid_sandbox", "changed_count": count}
        raise RetryableJobError(_RETRY)

    return handle
