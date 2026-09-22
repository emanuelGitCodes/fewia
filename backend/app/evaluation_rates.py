"""Dated explicit token rates for evaluation cost estimates."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

_RATES_ERROR = "rates is invalid"


@dataclass(frozen=True)
class TokenRateConfig:
    model_id: str
    source_region: str
    routing: str
    service_tier: str
    currency: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    effective_date: date
    retrieved_date: date
    source_url: str


def token_rate_config(value: object) -> TokenRateConfig:
    payload: object = value
    if isinstance(value, TokenRateConfig):
        payload = _mapping_from_config(value)
    if not isinstance(payload, Mapping):
        raise ValueError(_RATES_ERROR)
    if payload.get("currency") != "USD":
        raise ValueError(_RATES_ERROR)
    effective = _day(payload.get("effective_date"))
    retrieved = _day(payload.get("retrieved_date"))
    if retrieved < effective:
        raise ValueError(_RATES_ERROR)
    url = _text(payload.get("source_url"))
    _require_https_source(url)
    return TokenRateConfig(
        model_id=_text(payload.get("model_id")),
        source_region=_text(payload.get("source_region")),
        routing=_text(payload.get("routing")),
        service_tier=_text(payload.get("service_tier", payload.get("tier"))),
        currency="USD",
        input_usd_per_million=_rate(payload.get("input_usd_per_million")),
        output_usd_per_million=_rate(payload.get("output_usd_per_million")),
        effective_date=effective,
        retrieved_date=retrieved,
        source_url=url,
    )


def _mapping_from_config(value: TokenRateConfig) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, item in asdict(value).items():
        if isinstance(item, Decimal):
            payload[key] = format(item, "f")
        elif isinstance(item, date):
            payload[key] = item.isoformat()
        else:
            payload[key] = item
    return payload


def _text(item: object) -> str:
    if type(item) is not str:
        raise ValueError(_RATES_ERROR)
    trimmed = item.strip()
    if trimmed == "":
        raise ValueError(_RATES_ERROR)
    return trimmed


def _day(item: object) -> date:
    if type(item) is not str:
        raise ValueError(_RATES_ERROR)
    try:
        return date.fromisoformat(item)
    except ValueError:
        raise ValueError(_RATES_ERROR) from None


def _rate(item: object) -> Decimal:
    if type(item) is not str:
        raise ValueError(_RATES_ERROR)
    try:
        amount = Decimal(item)
    except InvalidOperation:
        raise ValueError(_RATES_ERROR) from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(_RATES_ERROR)
    return amount


def _require_https_source(url: str) -> None:
    try:
        parsed = urlparse(url)
    except ValueError:
        raise ValueError(_RATES_ERROR) from None
    if parsed.scheme != "https":
        raise ValueError(_RATES_ERROR)
    if parsed.hostname is None or parsed.hostname == "":
        raise ValueError(_RATES_ERROR)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(_RATES_ERROR)
