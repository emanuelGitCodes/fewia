from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, DecimalException
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class EvaluationRates(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, hide_input_in_errors=True
    )

    model_id: str
    region: str
    currency: Literal["USD"]
    input_usd_per_1000: Decimal
    output_usd_per_1000: Decimal
    cached_input_usd_per_1000: Decimal | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    cache_write_usd_per_1000: Decimal | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    cache_write_30m_usd_per_1000: Decimal | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    cache_write_12h_usd_per_1000: Decimal | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    source_url: str
    source_version: str
    published_at: datetime | None = None
    effective_date: date | None = None
    date_as_of: date | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    retrieved_at: date

    @model_validator(mode="after")
    def validate_provenance(self) -> EvaluationRates:
        if self.date_as_of is None and (
            self.published_at is None or self.effective_date is None
        ):
            raise ValueError("Rate provenance needs publication dates or date_as_of.")
        return self

    @field_validator("model_id", "region", "source_version", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid rate metadata.")
        return value

    @field_validator("input_usd_per_1000", "output_usd_per_1000", mode="before")
    @classmethod
    def validate_rate(cls, value: object) -> Decimal:
        pattern = r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise ValueError("Invalid decimal rate.")
        try:
            result = Decimal(value)
        except DecimalException:
            raise ValueError("Invalid decimal rate.") from None
        if not result.is_finite() or result < 0:
            raise ValueError("Invalid decimal rate.")
        return result

    @field_validator(
        "cached_input_usd_per_1000",
        "cache_write_usd_per_1000",
        "cache_write_30m_usd_per_1000",
        "cache_write_12h_usd_per_1000",
        mode="before",
    )
    @classmethod
    def validate_cached_rate(cls, value: object) -> Decimal | None:
        return None if value is None else cls.validate_rate(value)

    @field_validator("effective_date", "retrieved_at", "date_as_of", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> date | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
        ):
            raise ValueError("Invalid calendar date.")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("Invalid calendar date.") from None

    @field_validator("published_at", mode="before")
    @classmethod
    def validate_timestamp(cls, value: object) -> datetime | None:
        if value is None:
            return None
        pattern = (
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
        )
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise ValueError("Invalid publication timestamp.")
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid publication timestamp.") from None
        offset = value[-6:]
        if offset[0] in "+-" and (int(offset[1:3]) > 23 or int(offset[4:6]) > 59):
            raise ValueError("Invalid publication timestamp.")
        return result

    @field_validator("source_url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or any(
                char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
            )
        ):
            raise ValueError("Invalid source URL.")
        try:
            parts = urlsplit(value)
            url = AnyHttpUrl(value)
            _ = parts.port
        except ValueError:
            raise ValueError("Invalid source URL.") from None
        if (
            parts.scheme != "https"
            or not parts.hostname
            or url.scheme != "https"
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("Invalid source URL.")
        return value


def parse_rates(rates: object, *, model_id: str, region: str) -> EvaluationRates:
    if not isinstance(rates, dict):
        raise ValueError("Invalid evaluation rates.")
    try:
        result = EvaluationRates.model_validate(rates)
    except ValidationError:
        raise ValueError("Invalid evaluation rates.") from None
    if result.model_id != model_id or result.region != region:
        raise ValueError("Invalid evaluation rates.")
    return result
