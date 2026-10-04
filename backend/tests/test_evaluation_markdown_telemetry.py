from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_cost import estimate_cost
from app.evaluation_markdown_telemetry import render_telemetry
from app.evaluation_telemetry import summarize_telemetry

MODEL = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"


def _rates() -> dict[str, object]:
    return {
        "model_id": MODEL,
        "region": REGION,
        "currency": "USD",
        "input_usd_per_1000": "0.00033",
        "output_usd_per_1000": "0.00275",
        "source_url": "https://pricing.example.org/bedrock.json",
        "source_version": "20260930230255",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def _slot(
    inputs: object = 1000,
    outputs: object = 2000,
    *,
    elapsed: object = 2.0,
    calls: object = 1,
    condition: str = "tool_enabled",
    evidence: str = "real_bedrock",
) -> dict[str, object]:
    return {
        "condition": condition,
        "elapsed_seconds": elapsed,
        "observation": {
            "evidence_class": evidence,
            "model_id": MODEL,
            "status": "completed",
            "turns": [
                {
                    "usage": {"inputTokens": inputs, "outputTokens": outputs},
                    "provider_calls": calls,
                    "provider_elapsed_seconds": 0.25,
                }
            ],
        },
    }


def _reports(
    samples: list[dict[str, object]], pricing: dict[str, object] | None
) -> tuple[dict[str, object], dict[str, object]]:
    telemetry = summarize_telemetry(samples)
    cost = estimate_cost(telemetry, pricing, model_id=MODEL, region=REGION)
    return telemetry, cost


def _group(source: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], source["groups"])[0]


def test_mixed_groups_keep_usage_bounds_and_costs_separate() -> None:
    telemetry, cost = _reports(
        [
            _slot(),
            _slot(500, None, elapsed=None, calls=None),
            _slot(9000, 9000, evidence="deterministic_fake_provider"),
            _slot(50, 100, evidence="controlled_fixture"),
            _slot(1000, 0, condition="no_tool"),
        ],
        _rates(),
    )
    before = deepcopy((telemetry, cost))
    rendered = render_telemetry(telemetry, cost)
    assert "| Total slots |\n| --- |\n| 5 |" in rendered
    assert "| input tokens | Unknown |" in rendered
    assert "| output tokens | Unknown |" in rendered
    assert "| known input tokens | 1500 |" in rendered
    assert "| known output tokens | 2000 |" in rendered
    assert "| known usage slots | 1 |" in rendered
    assert "| unknown usage slots | 1 |" in rendered
    assert "| known usage turns | 1 |" in rendered
    assert "| unknown usage turns | 1 |" in rendered
    assert "| Unknown | 1 | 1 | 1 | 1 |" in rendered
    assert "| Estimated USD | Unknown |" in rendered
    assert "| tool\\_enabled | real\\_bedrock | unknown | 0\\.005995 |" in rendered
    assert "| no\\_tool | real\\_bedrock | estimated | 0\\.00033 |" in rendered
    assert (
        "| tool\\_enabled | deterministic\\_fake\\_provider | "
        "not\\_applicable | Unknown |" in rendered
    )
    assert "| tool\\_enabled | controlled\\_fixture | unknown | Unknown |" in rendered
    assert "does not mean a live benchmark is free" in rendered
    assert (telemetry, cost) == before


def test_nearest_rank_percentiles_and_measured_samples() -> None:
    samples = [_slot(elapsed=value) for value in range(20, 0, -1)]
    samples.append(_slot(elapsed=None))
    telemetry, cost = _reports(samples, _rates())
    rendered = render_telemetry(telemetry, cost)
    assert "Slot latency measures end-to-end seconds." in rendered
    assert "| 10.0 | 19.0 | 20 | 1 | nearest\\-rank |" in rendered
    assert "| 21 | 21 | 21 | 0 | 0 |" in rendered
    assert "| Estimated USD | 0\\.12243 |" in rendered
    assert "provider_elapsed_seconds" not in rendered
    assert "target" not in rendered.lower()


def test_missing_rates_and_usage_remain_unknown() -> None:
    telemetry, cost = _reports([_slot(None, None, calls=None, elapsed=None)], None)
    rendered = render_telemetry(telemetry, cost)
    assert "| input tokens | Unknown |" in rendered
    assert "| known input tokens | Unknown |" in rendered
    assert "| Unknown | Unknown | 0 | 1 | 1 |" in rendered
    assert "| Unknown | Unknown | 0 | 1 | nearest\\-rank |" in rendered
    assert "| Estimated USD | Unknown |" in rendered
    assert "Pricing evidence: unavailable." in rendered


def test_missing_rates_do_not_assign_known_usage_a_zero_cost() -> None:
    telemetry, cost = _reports([_slot()], None)
    rendered = render_telemetry(telemetry, cost)
    assert "| input tokens | 1000 |" in rendered
    assert "| Estimated USD | Unknown |" in rendered
    assert "| Known usage lower bound \\(USD\\) | Unknown |" in rendered


def test_zero_usage_and_local_model_billing_have_distinct_statuses() -> None:
    telemetry, cost = _reports([_slot(0, 0, calls=0, elapsed=0)], _rates())
    rendered = render_telemetry(telemetry, cost)
    assert "| input tokens | 0 |" in rendered
    assert "| Status | estimated |" in rendered
    assert "| Estimated USD | 0" in rendered
    telemetry, cost = _reports([_slot(evidence="local_postgresql")], None)
    rendered = render_telemetry(telemetry, cost)
    assert "| Status | not\\_applicable |" in rendered
    assert "| Estimated USD | Unknown |" in rendered
    assert "Model billing is not applicable for local/fake evidence" in rendered


def test_empty_and_legacy_reports_have_no_invented_measurements() -> None:
    assert render_telemetry(None, None).count("Unavailable (legacy report).") == 2
    telemetry, cost = _reports([], None)
    rendered = render_telemetry(telemetry, cost)
    assert "| Total slots |\n| --- |\n| 0 |" in rendered
    assert "| Estimated USD | Unknown |" in rendered
    assert render_telemetry(telemetry, None).count("Unavailable (legacy report).") == 1
    assert render_telemetry(None, cost).count("Unavailable (legacy report).") == 1


def test_pricing_provenance_is_allowlisted_and_link_is_safe() -> None:
    pricing = _rates()
    pricing["source_url"] = "https://pricing.example.org/rates(foo)?q=<tag>#note"
    telemetry, cost = _reports([_slot(condition="x|<script>\n#title")], pricing)
    _group(telemetry)["answer"] = "UNUSED_ANSWER_MARKER"
    telemetry["error"] = "UNUSED_ERROR_MARKER"
    cost["scope"] = "UNUSED_SCOPE_MARKER"
    cast(dict[str, object], cost["pricing"])["extra"] = "UNUSED_PRICING_MARKER"
    before = deepcopy((telemetry, cost))
    rendered = render_telemetry(telemetry, cost)
    assert "| x\\|\\<script\\> \\#title | real\\_bedrock |" in rendered
    assert (
        "[Pricing source](https://pricing.example.org/rates%28foo%29?q=%3Ctag%3E#note)"
        in rendered
    )
    for expected in (
        "| source\\_version | 20260930230255 |",
        "| published\\_at | 2026\\-09\\-30T23\\:02\\:55Z |",
        "| effective\\_date | 2026\\-09\\-01 |",
        "| retrieved\\_at | 2026\\-10\\-02 |",
        "| input\\_usd\\_per\\_1000 | 0\\.00033 |",
        "| output\\_usd\\_per\\_1000 | 0\\.00275 |",
        "| currency | USD |",
        "| Model | us\\.amazon\\.nova\\-2\\-lite\\-v1\\:0 |",
        "| Region | us\\-east\\-1 |",
    ):
        assert expected in rendered
    assert "UNUSED_" not in rendered
    assert (telemetry, cost) == before


def test_long_dynamic_labels_are_bounded() -> None:
    telemetry, cost = _reports([_slot(condition="x" * 1000)], None)
    rendered = render_telemetry(telemetry, cost)
    assert "x" * 255 + "…" in rendered
    assert "x" * 256 not in rendered


@pytest.mark.parametrize("value", [True, -1, 1.5, "1", {}, [], float("inf")])
@pytest.mark.parametrize("field", ["total_slots", "known_usage_turns", "input_tokens"])
def test_malformed_usage_numbers_have_static_errors(field: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    _group(telemetry)[field] = value
    before = deepcopy((telemetry, cost))
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)
    assert (telemetry, cost) == before


@pytest.mark.parametrize("value", [True, -1, "1", {}, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["p50", "p95", "sample_count"])
def test_malformed_latency_numbers_have_static_errors(
    field: str, value: object
) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    metric = cast(dict[str, object], _group(telemetry)["slot_elapsed_seconds"])
    metric[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


@pytest.mark.parametrize("value", [None, 1, True, {}, [], "", " "])
@pytest.mark.parametrize("field", ["condition", "evidence_class"])
def test_malformed_labels_have_static_errors(field: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    _group(telemetry)[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)
    telemetry, cost = _reports([_slot()], _rates())
    _group(cost)[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


@pytest.mark.parametrize("value", [None, {}, "INVALID_STRUCTURE_MARKER", [None], [{}]])
@pytest.mark.parametrize("section", ["telemetry", "cost"])
def test_malformed_groups_have_static_errors(section: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    source = telemetry if section == "telemetry" else cost
    source["groups"] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


@pytest.mark.parametrize("value", [True, 1, "NaN", "-1", "UNSAFE_AMOUNT_MARKER", {}])
@pytest.mark.parametrize("field", ["estimated_usd", "known_usage_lower_bound"])
def test_malformed_cost_amounts_have_static_errors(field: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    cost[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "javascript:UNSAFE_URL_MARKER"),
        ("source_url", "https://user:UNSAFE_URL_MARKER@pricing.example.org"),
        ("source_url", "https://pricing.example.org/" + "x" * 256),
        ("published_at", "invalid"),
        ("source_version", {}),
        ("input_usd_per_1000", "NaN"),
        ("currency", "EUR"),
    ],
)
def test_malformed_pricing_has_static_errors(field: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    cast(dict[str, object], cost["pricing"])[field] = value
    before = deepcopy((telemetry, cost))
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)
    assert (telemetry, cost) == before


def test_missing_expected_fields_are_rejected() -> None:
    telemetry, cost = _reports([_slot()], _rates())
    del _group(telemetry)["provider_calls"]
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


def test_unobserved_slots_keep_totals_unknown_without_inventing_turns() -> None:
    telemetry, cost = _reports([{"condition": "tool_enabled"}], _rates())
    rendered = render_telemetry(telemetry, cost)
    assert "| observed slots | 0 |" in rendered
    assert "| unknown usage slots | 1 |" in rendered
    assert "| unknown usage turns | 0 |" in rendered
    assert "| input tokens | Unknown |" in rendered
    assert "| Unknown | Unknown | 0 | 0 | 1 |" in rendered
    assert "| Estimated USD | Unknown |" in rendered


@pytest.mark.parametrize("value", [True, -1, 1.5, "1", {}, float("nan")])
@pytest.mark.parametrize("field", ["total", "known_total", "sample_count"])
def test_malformed_provider_call_numbers_have_static_errors(
    field: str, value: object
) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    calls = cast(dict[str, object], _group(telemetry)["provider_calls"])
    calls[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", {}), ("status", "free"), ("model_id", []), ("region", None)],
)
def test_malformed_cost_labels_have_static_errors(field: str, value: object) -> None:
    telemetry, cost = _reports([_slot()], _rates())
    cost[field] = value
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)


def test_invalid_percentile_method_has_a_static_error() -> None:
    telemetry, cost = _reports([_slot()], _rates())
    metric = cast(dict[str, object], _group(telemetry)["slot_elapsed_seconds"])
    metric["percentile_method"] = {"value": "UNSAFE_METHOD_MARKER"}
    with pytest.raises(ValueError, match="^Invalid evaluation report input$"):
        render_telemetry(telemetry, cost)
