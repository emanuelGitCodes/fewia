from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from app.evaluation_cost import estimate_token_cost, token_rate_config

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"
SOURCE_URL = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
    "AmazonBedrock/current/us-east-1/index.json"
)
MARKER = "do-not-echo-raw-input"


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


def _telemetry(
    *,
    observed_slots: object = 1,
    known_usage_slots: object = 1,
    unknown_usage_slots: object = 0,
    known_input_tokens: object = 0,
    known_output_tokens: object = 0,
    input_tokens: object | None = 0,
    output_tokens: object | None = 0,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "observed_slots": observed_slots,
        "known_usage_slots": known_usage_slots,
        "unknown_usage_slots": unknown_usage_slots,
        "known_input_tokens": known_input_tokens,
        "known_output_tokens": known_output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if extra:
        body.update(extra)
    return body


def _estimate(
    telemetry: dict[str, object],
    rates: object | None = None,
    **kwargs: str,
) -> dict[str, object]:
    payload: object = _rates() if rates is None else rates
    return estimate_token_cost(
        telemetry,
        cast(dict[str, object], payload),
        model_id=kwargs.get("model_id", MODEL_ID),
        source_region=kwargs.get("source_region", REGION),
        routing=kwargs.get("routing", "geographic"),
        service_tier=kwargs.get("service_tier", "standard"),
    )


def test_known_million_tokens_use_explicit_geographic_standard_rates() -> None:
    result = _estimate(
        _telemetry(
            known_input_tokens=1_000_000,
            known_output_tokens=1_000_000,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
    )
    assert Decimal(str(result["estimated_usd"])) == Decimal("3.08")
    assert Decimal(str(result["known_subset_estimated_usd"])) == Decimal("3.08")
    assert type(result["estimated_usd"]) is str
    assert "." in str(result["estimated_usd"])
    assert len(str(result["estimated_usd"]).split(".", 1)[1]) >= 8
    assert result["model_id"] == MODEL_ID
    assert result["source_region"] == REGION
    assert result["routing"] == "geographic"
    assert result["service_tier"] == "standard"
    assert result["effective_date"] == "2026-09-01"
    assert result["retrieved_date"] == "2026-09-22"
    assert result["source_url"] == SOURCE_URL
    assert result["currency"] == "USD"
    assert "Text input/output" in str(result["scope"])
    assert "cache" in str(result["scope"])
    assert "account adjustments" in str(result["scope"])
    assert "invoice" in str(result["scope"])
    assert "quality" not in result


def test_partial_unknown_usage_keeps_overall_null() -> None:
    result = _estimate(
        _telemetry(
            observed_slots=2,
            known_usage_slots=1,
            unknown_usage_slots=1,
            known_input_tokens=1_000_000,
            known_output_tokens=1_000_000,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert result["estimated_usd"] is None
    assert Decimal(str(result["known_subset_estimated_usd"])) == Decimal("3.08")


def test_empty_fixture_only_telemetry_is_null() -> None:
    result = _estimate(
        _telemetry(
            observed_slots=0,
            known_usage_slots=0,
            unknown_usage_slots=0,
            known_input_tokens=0,
            known_output_tokens=0,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert result["estimated_usd"] is None
    assert result["known_subset_estimated_usd"] is None


def test_measured_zero_usage_is_zero() -> None:
    result = _estimate(_telemetry())
    assert Decimal(str(result["estimated_usd"])) == Decimal("0")
    assert Decimal(str(result["known_subset_estimated_usd"])) == Decimal("0")


def test_model_region_routing_and_tier_mismatch_raise() -> None:
    cases = [
        {"model_id": "other-model"},
        {"source_region": "us-west-2"},
        {"routing": "global"},
        {"service_tier": "priority"},
    ]
    telemetry = _telemetry()
    for kwargs in cases:
        with pytest.raises(ValueError, match="^model metadata does not match$"):
            _estimate(telemetry, **kwargs)


def test_rate_metadata_mismatch_raises() -> None:
    telemetry = _telemetry()
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(telemetry, _rates(model_id="other-model"))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(telemetry, _rates(source_region="us-west-2"))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(telemetry, _rates(routing="global"))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(telemetry, _rates(service_tier="priority"))


def test_mixed_telemetry_model_metadata_raises() -> None:
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(_telemetry(extra={"model_id": "other-model"}))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(_telemetry(extra={"source_region": "eu-west-1"}))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(_telemetry(extra={"routing": "global"}))
    with pytest.raises(ValueError, match="^model metadata does not match$"):
        _estimate(_telemetry(extra={"service_tier": "priority"}))


def test_invalid_rates_raise_static_error() -> None:
    telemetry = _telemetry()
    invalid = [
        _rates(input_usd_per_million="NaN"),
        _rates(output_usd_per_million="Inf"),
        _rates(input_usd_per_million="-0.1"),
        _rates(input_usd_per_million=0.33),
        _rates(output_usd_per_million=True),
        _rates(input_usd_per_million=0),
        _rates(currency="EUR"),
        _rates(source_url="http://example.invalid/rates"),
        _rates(source_url="https://user:pass@example.invalid/rates"),
        _rates(effective_date="2026-13-01"),
        _rates(retrieved_date="2026-08-31"),
        _rates(model_id=""),
        "not-a-map",
    ]
    for rates in invalid:
        with pytest.raises(ValueError, match="^rates is invalid$"):
            _estimate(telemetry, rates)


def test_huge_integer_tokens_keep_decimal_precision() -> None:
    token = 2**53 + 1
    result = _estimate(
        _telemetry(
            known_input_tokens=token,
            known_output_tokens=token,
            input_tokens=token,
            output_tokens=token,
        )
    )
    expected = (
        Decimal(token) * Decimal("0.33") + Decimal(token) * Decimal("2.75")
    ) / Decimal("1000000")
    assert Decimal(str(result["estimated_usd"])) == expected
    assert type(result["estimated_usd"]) is str


def test_errors_do_not_echo_raw_input() -> None:
    telemetry = _telemetry()
    with pytest.raises(ValueError) as rates_error:
        _estimate(
            telemetry,
            _rates(source_url=f"http://example.invalid/{MARKER}"),
        )
    assert MARKER not in str(rates_error.value)
    with pytest.raises(ValueError) as match_error:
        _estimate(telemetry, _rates(model_id=MARKER))
    assert MARKER not in str(match_error.value)
    with pytest.raises(ValueError) as usage_error:
        _estimate(
            _telemetry(known_usage_slots=True),
        )
    assert "True" not in str(usage_error.value)


def test_invalid_telemetry_counts_raise_static_error() -> None:
    invalid = [
        _telemetry(known_usage_slots=-1),
        _telemetry(unknown_usage_slots=-1),
        _telemetry(observed_slots=-1),
        _telemetry(known_input_tokens=-1),
        _telemetry(known_output_tokens=-1),
        _telemetry(known_usage_slots=True),
        _telemetry(known_input_tokens=True),
        _telemetry(
            observed_slots=1,
            known_usage_slots=0,
            unknown_usage_slots=0,
            input_tokens=None,
            output_tokens=None,
        ),
        _telemetry(
            known_usage_slots=0,
            unknown_usage_slots=0,
            observed_slots=0,
            known_input_tokens=4,
            known_output_tokens=0,
            input_tokens=None,
            output_tokens=None,
        ),
        _telemetry(
            known_usage_slots=1,
            unknown_usage_slots=0,
            input_tokens=None,
            output_tokens=0,
        ),
        _telemetry(
            known_usage_slots=1,
            unknown_usage_slots=0,
            known_input_tokens=4,
            known_output_tokens=0,
            input_tokens=5,
            output_tokens=0,
        ),
        _telemetry(
            observed_slots=2,
            known_usage_slots=1,
            unknown_usage_slots=1,
            input_tokens=1,
            output_tokens=1,
        ),
    ]
    for telemetry in invalid:
        with pytest.raises(ValueError, match="^telemetry is invalid$"):
            _estimate(telemetry)


def test_missing_usage_and_rates_are_not_zero() -> None:
    with pytest.raises(ValueError, match="^telemetry is invalid$"):
        _estimate({"observed_slots": 1, "known_usage_slots": 1})
    with pytest.raises(ValueError, match="^rates is invalid$"):
        _estimate(_telemetry(), {"model_id": MODEL_ID})


def test_token_rate_config_accepts_tier_alias_and_typed_config() -> None:
    rates = _rates()
    rates.pop("service_tier")
    rates["tier"] = "standard"
    config = token_rate_config(rates)
    result = estimate_token_cost(
        _telemetry(
            known_input_tokens=1_000_000,
            known_output_tokens=1_000_000,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        ),
        config,
        model_id=MODEL_ID,
        source_region=REGION,
    )
    assert Decimal(str(result["estimated_usd"])) == Decimal("3.08")
    assert result["service_tier"] == "standard"
    assert config.input_usd_per_million == Decimal("0.33")
    assert config.output_usd_per_million == Decimal("2.75")


def test_unknown_only_usage_keeps_overall_and_subset_null() -> None:
    result = _estimate(
        _telemetry(
            observed_slots=1,
            known_usage_slots=0,
            unknown_usage_slots=1,
            known_input_tokens=0,
            known_output_tokens=0,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert result["estimated_usd"] is None
    assert result["known_subset_estimated_usd"] is None


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
    ],
)
def test_direct_invalid_token_rate_config_raises_static_error(
    override: dict[str, object],
) -> None:
    valid = token_rate_config(_rates())
    config = replace(valid, **override)
    with pytest.raises(ValueError, match="^rates is invalid$"):
        _estimate(_telemetry(), config)


def test_token_rate_config_replace_nonfinite_raises() -> None:
    valid = token_rate_config(_rates())
    broken = replace(valid, input_usd_per_million=Decimal("NaN"))
    with pytest.raises(ValueError, match="^rates is invalid$"):
        _estimate(_telemetry(), broken)
