"""HTTP models for chat jobs."""

import json
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
)

from app.agent.chat_context import MAX_MESSAGE_LEN

_CALLER_FIELDS = (
    "message",
    "monthly_limit_cents",
    "plan_cap_cents",
    "plan_revision_id",
    "previous_job_id",
)


class CreateChatJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: StrictStr = Field(min_length=1, max_length=MAX_MESSAGE_LEN)
    monthly_limit_cents: StrictInt = Field(ge=0)
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)
    previous_job_id: UUID | None = None
    plan_revision_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message is invalid")
        return value

    def matches_stored_caller_fields(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("operation") != "chat":
            return False
        extracted: dict[str, object] = {}
        for key in _CALLER_FIELDS:
            if key in payload:
                extracted[key] = payload[key]
        try:
            stored = CreateChatJobBody.model_validate(extracted)
            left = json.dumps(
                stored.model_dump(mode="json"), sort_keys=True, allow_nan=False
            )
            right = json.dumps(
                self.model_dump(mode="json"), sort_keys=True, allow_nan=False
            )
        except (ValidationError, TypeError, ValueError):
            return False
        return left == right
