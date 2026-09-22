"""HTTP models for Plaid Item sync."""

from datetime import UTC, datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)


class CreateSyncJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("item_id")
    @classmethod
    def validate_item_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("item_id is invalid")
        return value

    def matches_stored_caller_fields(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        return (
            payload.get("item_id") == self.item_id
            and payload.get("operation") == "plaid_sync"
        )


class SyncItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: StrictStr
    last_synced_at: AwareDatetime | None

    @field_validator("last_synced_at", mode="before")
    @classmethod
    def as_utc(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
