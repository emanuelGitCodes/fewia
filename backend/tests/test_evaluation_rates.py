from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from app.evaluation_rates import TokenRateConfig, token_rate_config

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"
SOURCE_URL = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
    "AmazonBedrock/current/us-east-1/index.json"
)
MARKER = "do-not-echo-raw-input"
PRICING_PATH = (
    Path(__file__).parent / "evaluation/pricing/nova2-lite-use1-20260922.json"
)


def _rates(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model_id": MODEL_ID,
        "source_region": REGION,
        "routing": "geographic",
        "service_tier": "standard",
        "currency": "USD",
        "input_usd_per_million": "0.33",
        "output_usd_per_million": "2.75",
        "effective_date": "2026-09-01",
        "retrieved_date": "2026-09-22",
        "source_url": SOURCE_URL,
    }
    body.update(overrides)
    return body


def test_dated_geographic_rates_from_pricing_file() -> None:
    payload = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    config = token_rate_config(payload)
    assert config.model_id == payload["model_id"]
    assert config.source_region == payload["source_region"]
    assert config.routing == "geographic"
    assert config.service_tier == "standard"
    assert config.currency == "USD"
    assert config.input_usd_per_million == Decimal("0.33")
    assert config.output_usd_per_million == Decimal("2.75")
    assert config.effective_date == date.fromisoformat(str(payload["effective_date"]))
    assert config.retrieved_date == date.fromisoformat(str(payload["retrieved_date"]))
    assert config.source_url == payload["source_url"]


def test_valid_dataclass_roundtrip() -> None:
    original = TokenRateConfig(
        model_id=MODEL_ID,
        source_region=REGION,
        routing="geographic",
        service_tier="standard",
        currency="USD",
        input_usd_per_million=Decimal("0.33"),
        output_usd_per_million=Decimal("2.75"),
        effective_date=date(2026, 9, 1),
        retrieved_date=date(2026, 9, 22),
        source_url=SOURCE_URL,
    )
    assert token_rate_config(original) == original
    assert token_rate_config(_rates()) == original


def test_token_rate_config_accepts_tier_alias_and_mapping_proxy() -> None:
    rates = _rates()
    rates.pop("service_tier")
    rates["tier"] = "standard"
    config = token_rate_config(MappingProxyType(rates))
    assert config.service_tier == "standard"
    assert config.input_usd_per_million == Decimal("0.33")
    assert config.output_usd_per_million == Decimal("2.75")


def test_identity_strings_are_trimmed() -> None:
    config = token_rate_config(
        _rates(
            model_id=f"  {MODEL_ID}  ",
            source_region=f"  {REGION}  ",
            routing="  geographic  ",
            service_tier="  standard  ",
        )
    )
    assert config.model_id == MODEL_ID
    assert config.source_region == REGION
    assert config.routing == "geographic"
    assert config.service_tier == "standard"


def test_same_day_dates_and_zero_rates_are_valid() -> None:
    config = token_rate_config(
        _rates(
            input_usd_per_million="0",
            output_usd_per_million="0",
            retrieved_date="2026-09-01",
        )
    )
    assert config.input_usd_per_million == Decimal("0")
    assert config.output_usd_per_million == Decimal("0")
    assert config.retrieved_date == config.effective_date


@pytest.mark.parametrize(
    "override",
    [
        {"input_usd_per_million": "NaN"},
        {"output_usd_per_million": "Inf"},
        {"input_usd_per_million": "-0.1"},
        {"input_usd_per_million": 0.33},
        {"output_usd_per_million": True},
        {"input_usd_per_million": 0},
        {"currency": "EUR"},
        {"source_url": "http://example.invalid/rates"},
        {"source_url": "https://user:pass@example.invalid/rates"},
        {"effective_date": "2026-13-01"},
        {"retrieved_date": "2026-08-31"},
        {"model_id": ""},
        {"model_id": "   "},
        {"source_region": "\t"},
        {"routing": " "},
        {"service_tier": "\n"},
    ],
)
def test_invalid_rate_mapping_raises_static_error(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="^rates is invalid$"):
        token_rate_config(_rates(**override))


def test_non_mapping_and_incomplete_rates_raise_static_error() -> None:
    with pytest.raises(ValueError, match="^rates is invalid$"):
        token_rate_config("not-a-map")
    with pytest.raises(ValueError, match="^rates is invalid$"):
        token_rate_config({"model_id": MODEL_ID})


@pytest.mark.parametrize(
    "override",
    [
        {"input_usd_per_million": Decimal("-1")},
        {"input_usd_per_million": Decimal("NaN")},
        {"output_usd_per_million": Decimal("Infinity")},
        {"currency": "EUR"},
        {"source_url": "https://user:pass@example.invalid/rates"},
        {"retrieved_date": date(2026, 8, 31)},
        {"model_id": ""},
        {"model_id": "   "},
    ],
)
def test_direct_invalid_token_rate_config_raises_static_error(
    override: dict[str, object],
) -> None:
    valid = token_rate_config(_rates())
    config = replace(valid, **override)
    with pytest.raises(ValueError, match="^rates is invalid$"):
        token_rate_config(config)


def test_malformed_source_url_raises_static_error_without_marker() -> None:
    urls = [
        f"http://example.invalid/{MARKER}",
        f"https://user:pass@example.invalid/{MARKER}",
        f"https://[{MARKER}",
        "https://[::1",
        "https://",
    ]
    for url in urls:
        with pytest.raises(ValueError, match="^rates is invalid$") as error:
            token_rate_config(_rates(source_url=url))
        assert MARKER not in str(error.value)
        assert "Invalid IPv6" not in str(error.value)
