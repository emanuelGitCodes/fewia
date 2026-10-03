from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.evaluation_cost_rates import EvaluationRates, parse_rates

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"


@pytest.fixture
def rates() -> dict[str, object]:
    return {
        "model_id": MODEL_ID,
        "region": REGION,
        "currency": "USD",
        "input_usd_per_1000": "0.0003300000",
        "output_usd_per_1000": "0.0027500000",
        "source_url": (
            "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
            "AmazonBedrock/current/us-east-1/index.json"
        ),
        "source_version": "20260930230255",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def test_fixture_preserves_exact_decimals(rates: dict[str, object]) -> None:
    result = parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert isinstance(result, EvaluationRates)
    assert result.model_id == MODEL_ID
    assert result.region == REGION
    assert result.currency == "USD"
    assert result.input_usd_per_1000.as_tuple() == Decimal("0.0003300000").as_tuple()
    assert result.output_usd_per_1000.as_tuple() == Decimal("0.0027500000").as_tuple()
    expected_publication = datetime.fromisoformat("2026-09-30T23:02:55+00:00")
    assert result.published_at == expected_publication
    assert result.effective_date == date(2026, 9, 1)
    assert result.retrieved_at == date(2026, 10, 2)


def test_model_is_frozen_and_json_is_public(rates: dict[str, object]) -> None:
    result = parse_rates(rates, model_id=MODEL_ID, region=REGION)

    with pytest.raises(ValidationError, match="frozen"):
        result.source_version = "replacement"
    assert result.model_dump(mode="json") == rates
    rates["source_version"] = "replacement"
    assert result.source_version == "20260930230255"


@pytest.mark.parametrize("value", ["0", "1.", ".5", "+0.5", "1E+3", "1e-20"])
def test_decimal_notation_preserves_value(rates: dict[str, object], value: str) -> None:
    rates["input_usd_per_1000"] = value

    result = parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert result.input_usd_per_1000.as_tuple() == Decimal(value).as_tuple()


@pytest.mark.parametrize(
    "field",
    [
        "model_id",
        "region",
        "currency",
        "input_usd_per_1000",
        "output_usd_per_1000",
        "source_url",
        "source_version",
        "published_at",
        "effective_date",
        "retrieved_at",
    ],
)
def test_missing_fields_fail(rates: dict[str, object], field: str) -> None:
    del rates[field]

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=MODEL_ID, region=REGION)


def test_extra_fields_fail_with_static_error(rates: dict[str, object]) -> None:
    rates["untrusted-field-sentinel"] = "untrusted-value-sentinel"

    with pytest.raises(ValueError) as error:
        parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert str(error.value) == "Invalid evaluation rates."
    assert error.value.__suppress_context__


@pytest.mark.parametrize("rates_input", [None, [], "untrusted-input", 0, True])
def test_non_objects_fail(rates_input: object) -> None:
    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates_input, model_id=MODEL_ID, region=REGION)


@pytest.mark.parametrize(
    ("model_id", "region"),
    [
        (MODEL_ID.upper(), REGION),
        (MODEL_ID + " ", REGION),
        (MODEL_ID, "us-west-2"),
        (MODEL_ID, REGION.upper()),
        (MODEL_ID, REGION + " "),
    ],
)
def test_model_and_region_must_match_exactly(
    rates: dict[str, object],
    model_id: str,
    region: str,
) -> None:
    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=model_id, region=region)


@pytest.mark.parametrize("value", ["usd", "EUR", " USD", "USD ", None, 1, True])
def test_non_usd_currency_fails(rates: dict[str, object], value: object) -> None:
    rates["currency"] = value

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=MODEL_ID, region=REGION)


@pytest.mark.parametrize("field", ["input_usd_per_1000", "output_usd_per_1000"])
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        0,
        1.5,
        Decimal("1.5"),
        None,
        "",
        " ",
        " 1",
        "1 ",
        "1\n",
        "1 0",
        "-1",
        "-0",
        "-0.0",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "inf",
        "1_000",
        "١",
        "1,5",
        ".",
        "+",
        "1e",
        "1e+",
        "0x10",
        "untrusted-rate-sentinel",
        "1e99999999999999999999999999999999999",
    ],
)
def test_invalid_rates_fail_with_static_errors(
    rates: dict[str, object],
    field: str,
    value: object,
) -> None:
    rates[field] = value

    with pytest.raises(ValueError) as error:
        parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert str(error.value) == "Invalid evaluation rates."


@pytest.mark.parametrize("field", ["model_id", "region", "source_version"])
@pytest.mark.parametrize("value", ["", " \t", None, 1, True])
def test_invalid_metadata_fails(
    rates: dict[str, object],
    field: str,
    value: object,
) -> None:
    rates[field] = value

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=MODEL_ID, region=REGION)


@pytest.mark.parametrize("field", ["effective_date", "retrieved_at"])
@pytest.mark.parametrize(
    "value",
    [
        "2026-02-29",
        "2026-13-01",
        "2026-09-31",
        "0000-01-01",
        "20260901",
        "2026-9-1",
        "2026-09-01T00:00:00Z",
        " 2026-09-01",
        "2026-09-01\n",
        None,
        True,
        20260901,
        date(2026, 9, 1),
    ],
)
def test_invalid_dates_fail(
    rates: dict[str, object],
    field: str,
    value: object,
) -> None:
    rates[field] = value

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=MODEL_ID, region=REGION)


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-29T23:02:55Z",
        "2026-09-30T24:02:55Z",
        "2026-09-30T23:60:55Z",
        "2026-09-30T23:02:60Z",
        "2026-09-30T23:02:55+24:00",
        "2026-09-30T23:02:55+01:60",
        "2026-09-30T23:02:55",
        "2026-09-30",
        "2026-09-30 23:02:55Z",
        "2026-09-30T23:02:55Z\n",
        None,
        True,
        0,
        datetime.fromisoformat("2026-09-30T23:02:55+00:00"),
    ],
)
def test_invalid_timestamps_fail(rates: dict[str, object], value: object) -> None:
    rates["published_at"] = value

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        parse_rates(rates, model_id=MODEL_ID, region=REGION)


def test_valid_leap_date_and_timestamp_offset(rates: dict[str, object]) -> None:
    rates["effective_date"] = "2024-02-29"
    rates["published_at"] = "2026-09-30T23:02:55.123456+05:30"

    result = parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert result.effective_date == date(2024, 2, 29)
    assert result.published_at.isoformat() == "2026-09-30T23:02:55.123456+05:30"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://",
        "https:///offers.json",
        "https://:443/offers.json",
        "http://example.com/offers.json",
        "ftp://example.com/offers.json",
        "example.com/offers.json",
        " https://example.com/offers.json",
        "https://example.com/offers.json\n",
        "https://exa mple.com/offers.json",
        "https://example.com/offer\x00.json",
        "https://example.com:invalid/offers.json",
        "https://example.com:65536/offers.json",
        "https://[invalid]/offers.json",
        "https:\\example.com/offers.json",
        "https://@example.com/offers.json",
        "https://user@example.com/offers.json",
        "https://user:placeholder@example.com/offers.json",
        "https://:placeholder@example.com/offers.json",
        None,
        True,
        1,
    ],
)
def test_invalid_urls_fail_with_static_errors(
    rates: dict[str, object],
    value: object,
) -> None:
    rates["source_url"] = value

    with pytest.raises(ValueError) as error:
        parse_rates(rates, model_id=MODEL_ID, region=REGION)

    assert str(error.value) == "Invalid evaluation rates."


def test_direct_model_validation_rejects_numeric_rates(
    rates: dict[str, object],
) -> None:
    rates["input_usd_per_1000"] = 0

    with pytest.raises(ValidationError) as error:
        EvaluationRates.model_validate(rates)

    assert "Invalid decimal rate." in str(error.value)
    assert "input_value" not in str(error.value)
