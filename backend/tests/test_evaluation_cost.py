from copy import deepcopy
from decimal import Decimal
from typing import cast

import pytest

from app.evaluation_cost import estimate_cost
from app.evaluation_telemetry import summarize_telemetry

MODEL = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"


def rates() -> dict[str, object]:
    return {
        "model_id": MODEL,
        "region": REGION,
        "currency": "USD",
        "input_usd_per_1000": "0.0003300000",
        "output_usd_per_1000": "0.0027500000",
        "source_url": "https://pricing.example.org/bedrock.json",
        "source_version": "20260930230255",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def slot(
    inputs: object,
    outputs: object,
    *,
    condition: str = "tool_enabled",
    evidence: object = "real_bedrock",
) -> dict[str, object]:
    return {
        "case_id": "case",
        "repeat": 1,
        "condition": condition,
        "observation": {
            "condition": condition,
            "evidence_class": evidence,
            "model_id": MODEL,
            "status": "completed",
            "turns": [{"usage": {"inputTokens": inputs, "outputTokens": outputs}}],
        },
    }


def estimate(
    slots: list[dict[str, object]], pricing: dict[str, object] | None
) -> dict[str, object]:
    return estimate_cost(
        summarize_telemetry(slots), pricing, model_id=MODEL, region=REGION
    )


def test_hand_calculated_totals_and_pricing_evidence() -> None:
    result = estimate([slot(1000, 2000), slot(500, 250)], rates())
    assert result["status"] == "estimated"
    assert Decimal(str(result["estimated_usd"])) == Decimal("0.0066825")
    assert result["known_usage_lower_bound"] == result["estimated_usd"]
    assert result["pricing"] == rates()
    for exclusion in (
        "taxes",
        "other AWS resources",
        "caching",
        "billing reconciliation",
    ):
        assert exclusion in str(result["scope"])


def test_exact_decimal_beyond_default_precision() -> None:
    pricing = rates()
    pricing["input_usd_per_1000"] = "0.123456789012345678901234567890123456789"
    pricing["output_usd_per_1000"] = "0.000000000000000000000000000000000000001"
    result = estimate([slot(1000, 1000)], pricing)
    assert result["estimated_usd"] == "0.123456789012345678901234567890123456790"


@pytest.mark.parametrize("field", ["model_id", "region"])
def test_rate_metadata_matches_exactly(field: str) -> None:
    pricing = rates()
    pricing[field] = "mismatch"
    with pytest.raises(ValueError, match="^rates do not match model and region$"):
        estimate([slot(1000, 2000)], pricing)


def test_mixed_models_do_not_use_one_models_rates() -> None:
    other = slot(1, 1)
    observation = cast(dict[str, object], other["observation"])
    observation["model_id"] = "another-model"
    result = estimate([slot(1, 1), other], rates())
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None


def test_missing_rates_keeps_known_usage_cost_unknown() -> None:
    result = estimate([slot(1000, 2000)], None)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None
    assert result["pricing"] is None


def test_partial_unknown_usage_has_only_a_lower_bound() -> None:
    result = estimate([slot(1000, 2000), slot(500, None)], rates())
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert Decimal(str(result["known_usage_lower_bound"])) == Decimal("0.005995")


@pytest.mark.parametrize("pricing", [None, rates()])
@pytest.mark.parametrize("usage", [(1000, 2000), (0, 0), (None, None)])
@pytest.mark.parametrize(
    "evidence",
    ["deterministic_fake_provider", "deterministic_domain", "local_postgresql"],
)
def test_exact_local_evidence_cost_is_not_applicable(
    evidence: str,
    pricing: dict[str, object] | None,
    usage: tuple[object, object],
) -> None:
    result = estimate([slot(*usage, evidence=evidence)], pricing)
    assert result["status"] == "not_applicable"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None


def test_conditions_and_evidence_remain_separate() -> None:
    result = estimate(
        [
            slot(1000, 2000),
            slot(500, 250, condition="no_tool"),
            slot(9000, 9000, evidence="deterministic_fake_provider"),
            slot(
                9000,
                9000,
                condition="deterministic",
                evidence="deterministic_domain",
            ),
        ],
        rates(),
    )
    groups = cast(list[dict[str, object]], result["groups"])
    assert len(groups) == 4
    assert Decimal(str(result["estimated_usd"])) == Decimal("0.0066825")
    assert sum(group["status"] == "not_applicable" for group in groups) == 2
    assert {(group["condition"], group["evidence_class"]) for group in groups} == {
        ("tool_enabled", "real_bedrock"),
        ("no_tool", "real_bedrock"),
        ("tool_enabled", "deterministic_fake_provider"),
        ("deterministic", "deterministic_domain"),
    }


def test_zero_usage_differs_from_unknown_usage() -> None:
    known = estimate([slot(0, 0)], rates())
    unknown = estimate([slot(None, None)], rates())
    assert known["status"] == "estimated"
    assert Decimal(str(known["estimated_usd"])) == 0
    assert unknown["status"] == "unknown"
    assert unknown["estimated_usd"] is None
    assert unknown["known_usage_lower_bound"] is None
    assert estimate([], rates())["estimated_usd"] is None


@pytest.mark.parametrize("usage", [True, False, -1, 1.5, "10", float("nan")])
def test_invalid_usage_remains_unknown(usage: object) -> None:
    result = estimate([slot(usage, 0)], rates())
    assert result["estimated_usd"] is None


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        0,
        0.1,
        None,
        "",
        "NaN",
        "Infinity",
        "-Infinity",
        "-1",
        " 1",
        "bad",
    ],
)
@pytest.mark.parametrize("field", ["input_usd_per_1000", "output_usd_per_1000"])
def test_invalid_rates_have_static_errors(field: str, value: object) -> None:
    pricing = rates()
    pricing[field] = value
    with pytest.raises(ValueError) as caught:
        estimate([slot(1, 1)], pricing)
    assert str(caught.value) == "rates are invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency", "EUR"),
        ("source_version", " "),
        ("source_url", ""),
        ("source_url", "http://pricing.example.org"),
        ("source_url", "https://"),
        ("source_url", "https://user:synthetic-marker@pricing.example.org"),
        ("source_url", "https://[invalid"),
        ("published_at", "2026-02-30T00:00:00Z"),
        ("published_at", True),
        ("effective_date", "2026-13-01"),
        ("retrieved_at", "not-a-date"),
        ("retrieved_at", "20261002"),
    ],
)
def test_invalid_metadata_has_static_errors(field: str, value: object) -> None:
    pricing = rates()
    pricing[field] = value
    with pytest.raises(ValueError) as caught:
        estimate([slot(1, 1)], pricing)
    assert str(caught.value) == "rates are invalid"


def test_missing_rate_fields_are_rejected() -> None:
    for field in rates():
        pricing = rates()
        del pricing[field]
        with pytest.raises(ValueError, match="^rates are invalid$"):
            estimate([slot(1, 1)], pricing)


@pytest.mark.parametrize(
    "evidence",
    [
        "unknown",
        "live_bedrock",
        "fixture",
        "fake_provider",
        "deterministic",
        "sqlite",
        "postgresql",
        "floci",
        "Real_bedrock",
        " real_bedrock",
        "",
        None,
        123,
    ],
)
def test_unknown_evidence_keeps_total_unknown(evidence: object) -> None:
    unknown = slot(0, 0, evidence=evidence)
    result = estimate([slot(1000, 2000), unknown], rates())
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert Decimal(str(result["known_usage_lower_bound"])) == Decimal("0.00583")
    alone = estimate([unknown], rates())
    assert alone["status"] == "unknown"
    assert alone["known_usage_lower_bound"] is None


@pytest.mark.parametrize(
    "field",
    [
        "total_slots",
        "known_usage_slots",
        "unknown_usage_slots",
        "input_tokens",
        "output_tokens",
        "known_input_tokens",
        "known_output_tokens",
    ],
)
@pytest.mark.parametrize("value", [True, False, -1, 1.5, "1", None])
def test_invalid_group_counts_do_not_certify_full_usage(
    field: str, value: object
) -> None:
    telemetry = summarize_telemetry([slot(0, 0)])
    groups = cast(list[dict[str, object]], telemetry["groups"])
    groups[0][field] = value
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None


def test_missing_group_keeps_total_cost_unknown() -> None:
    telemetry = summarize_telemetry([slot(1, 1)])
    telemetry["total_slots"] = 2
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is not None


def test_rates_with_extra_fields_are_rejected_by_the_approved_parser() -> None:
    pricing = rates()
    pricing["unrelated"] = "synthetic-marker"
    with pytest.raises(ValueError, match="^rates are invalid$"):
        estimate([slot(1, 1)], pricing)


@pytest.mark.parametrize("pricing", [True, 0, [], "invalid"])
def test_invalid_rate_containers_keep_static_errors(pricing: object) -> None:
    with pytest.raises(ValueError, match="^rates are invalid$"):
        estimate([slot(1, 1)], cast(dict[str, object], pricing))


def test_invalid_rates_take_priority_over_model_mismatch() -> None:
    pricing = rates()
    pricing["model_id"] = "another-model"
    pricing["input_usd_per_1000"] = "invalid"
    with pytest.raises(ValueError, match="^rates are invalid$"):
        estimate([slot(1, 1)], pricing)


def test_approved_decimal_syntax_and_serialized_metadata() -> None:
    pricing = rates()
    pricing["input_usd_per_1000"] = ".5"
    pricing["output_usd_per_1000"] = "1e-3"
    pricing["published_at"] = "2026-09-30T23:02:55+05:30"
    result = estimate([slot(1000, 1000)], pricing)
    assert result["estimated_usd"] == "0.501"
    assert result["pricing"] == {
        **pricing,
        "input_usd_per_1000": "0.5",
        "output_usd_per_1000": "0.001",
    }


def test_missing_evidence_does_not_prove_applicability() -> None:
    sample = slot(1000, 2000)
    observation = cast(dict[str, object], sample["observation"])
    del observation["evidence_class"]
    result = estimate([sample], rates())
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None


@pytest.mark.parametrize("evidence", [None, "unknown", "deterministic"])
def test_deterministic_condition_alone_does_not_prove_not_applicable(
    evidence: object,
) -> None:
    result = estimate(
        [slot(0, 0, condition="deterministic", evidence=evidence)], rates()
    )
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None


def test_exact_real_evidence_controls_eligibility_for_any_condition() -> None:
    result = estimate([slot(1000, 2000, condition="deterministic")], rates())
    assert result["status"] == "estimated"
    assert Decimal(str(result["estimated_usd"])) == Decimal("0.00583")


@pytest.mark.parametrize(
    "rows",
    [
        None,
        1,
        "invalid",
        {},
        [],
        [None],
        ["invalid"],
        [{}],
        [{"model_id": None}],
        [{"model_id": 123}],
        [{"model_id": "another-model"}],
        [{"model_id": MODEL}, {"model_id": MODEL}],
    ],
)
def test_malformed_or_incomplete_model_rows_cannot_estimate(rows: object) -> None:
    telemetry = summarize_telemetry([slot(1000, 2000)])
    groups = cast(list[dict[str, object]], telemetry["groups"])
    groups[0]["slots"] = rows
    original = deepcopy(telemetry)
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None
    assert telemetry == original


def test_missing_rows_exclude_only_the_ineligible_groups_cost() -> None:
    telemetry = summarize_telemetry(
        [slot(1000, 2000, condition="no_tool"), slot(9000, 9000)]
    )
    groups = cast(list[dict[str, object]], telemetry["groups"])
    for group in groups:
        if group["condition"] == "tool_enabled":
            del group["slots"]
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert Decimal(str(result["known_usage_lower_bound"])) == Decimal("0.00583")
    result_groups = cast(list[dict[str, object]], result["groups"])
    excluded = next(g for g in result_groups if g["condition"] == "tool_enabled")
    assert excluded["known_usage_lower_bound"] is None


@pytest.mark.parametrize("groups", [None, {}, "invalid", [], [None], [{}]])
def test_missing_or_malformed_groups_remain_unknown(groups: object) -> None:
    telemetry: dict[str, object] = {"total_slots": 1, "groups": groups}
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert result["known_usage_lower_bound"] is None


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "1", None, 2])
def test_invalid_or_incomplete_total_keeps_only_a_lower_bound(value: object) -> None:
    telemetry = summarize_telemetry([slot(1000, 2000)])
    telemetry["total_slots"] = value
    result = estimate_cost(telemetry, rates(), model_id=MODEL, region=REGION)
    assert result["status"] == "unknown"
    assert result["estimated_usd"] is None
    assert Decimal(str(result["known_usage_lower_bound"])) == Decimal("0.00583")


def test_inputs_are_unchanged_on_success_and_failure() -> None:
    telemetry = summarize_telemetry([slot(1, 1)])
    pricing = rates()
    original_telemetry, original_pricing = deepcopy(telemetry), deepcopy(pricing)
    estimate_cost(telemetry, pricing, model_id=MODEL, region=REGION)
    assert telemetry == original_telemetry
    assert pricing == original_pricing
    pricing["source_version"] = ""
    original_pricing = deepcopy(pricing)
    with pytest.raises(ValueError):
        estimate_cost(telemetry, pricing, model_id=MODEL, region=REGION)
    assert telemetry == original_telemetry
    assert pricing == original_pricing
