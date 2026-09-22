from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from re import escape
from types import MappingProxyType
from typing import cast

import pytest

from app.evaluation_cost import TokenRateConfig
from app.evaluation_cost_markdown import render_cost_markdown
from app.evaluation_rates import token_rate_config
from app.evaluation_report_values import INVALID

PRICING = Path(__file__).parent / "evaluation/pricing/nova2-lite-use1-20260922.json"
MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"
SOURCE_URL = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
    "AmazonBedrock/current/us-east-1/index.json"
)
MARKER = "FIXTURE_SECRET_MARKER"
KNOWN = "0.13163909"


def _rates(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = json.loads(PRICING.read_text(encoding="utf-8"))
    body.update(overrides)
    return body


def _telemetry(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "observed_slots": 24,
        "known_usage_slots": 24,
        "unknown_usage_slots": 0,
        "known_input_tokens": 166198,
        "known_output_tokens": 27925,
        "input_tokens": 166198,
        "output_tokens": 27925,
    }
    body.update(overrides)
    return body


def _render(
    telemetry: Mapping[str, object] | None = None,
    rates: object | None = None,
    **kwargs: str,
) -> str:
    payload = _rates() if rates is None else rates
    usage = _telemetry() if telemetry is None else telemetry
    return render_cost_markdown(
        usage,
        cast(TokenRateConfig | Mapping[str, object], payload),
        model_id=kwargs.get("model_id", MODEL_ID),
        source_region=kwargs.get("source_region", REGION),
        routing=kwargs.get("routing", "geographic"),
        service_tier=kwargs.get("service_tier", "standard"),
    )


def _invalid(run: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=f"^{escape(INVALID)}$") as caught:
        run()
    assert str(caught.value) == INVALID
    assert MARKER not in str(caught.value)


def _bad_source(url: str) -> None:
    _invalid(lambda: _render(rates=_rates(source_url=url)))


def test_dated_fixture_known_cost_for_twenty_four_slots() -> None:
    text = _render()
    assert text.startswith("## Estimated model cost\n")
    assert f"estimated_usd: {KNOWN}" in text
    assert f"known_subset_estimated_usd: {KNOWN}" in text
    assert "currency: `USD`" in text
    assert "input_usd_per_million: 0.33" in text
    assert "output_usd_per_million: 2.75" in text
    assert f"model_id: `{MODEL_ID}`" in text
    assert f"source_region: `{REGION}`" in text
    assert "routing: `geographic`" in text
    assert "service_tier: `standard`" in text
    assert "effective_date: `2026-09-01`" in text
    assert "retrieved_date: `2026-09-22`" in text
    assert f"source_url: [source]({SOURCE_URL})" in text
    assert "Text input/output token estimate only." in text
    assert "Excludes cache, other charges, and account adjustments." in text
    assert "Not an AWS invoice or observed billing." in text
    assert "source_version" not in text
    assert "source_rows" not in text
    assert "source_publication_date" not in text
    assert "other services" not in text
    typed = _render(rates=token_rate_config(_rates()))
    assert f"estimated_usd: {KNOWN}" in typed
    encoded = _render(rates=_rates(source_url="https://example.invalid/a(b)"))
    assert "source_url: [source](https://example.invalid/a%28b%29)" in encoded


def test_partial_unknown_keeps_overall_unknown_and_shows_subset() -> None:
    text = _render(
        _telemetry(
            known_usage_slots=12,
            unknown_usage_slots=12,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert "estimated_usd: unknown" in text
    assert f"known_subset_estimated_usd: {KNOWN}" in text


def test_zero_known_slots_are_unknown() -> None:
    text = _render(
        _telemetry(
            known_usage_slots=0,
            unknown_usage_slots=24,
            known_input_tokens=0,
            known_output_tokens=0,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert "estimated_usd: unknown" in text
    assert "known_subset_estimated_usd: unknown" in text
    assert "estimated_usd: 0" not in text
    assert "known_subset_estimated_usd: 0" not in text


def test_true_zero_known_usage_is_zero() -> None:
    text = _render(
        _telemetry(
            known_input_tokens=0,
            known_output_tokens=0,
            input_tokens=0,
            output_tokens=0,
        )
    )
    assert "estimated_usd: 0.00000000" in text
    assert "known_subset_estimated_usd: 0.00000000" in text
    assert "estimated_usd: unknown" not in text


def test_mismatched_metadata_and_malformed_rates_are_static() -> None:
    _invalid(lambda: _render(model_id="other-model"))
    _invalid(lambda: _render(source_region="us-west-2"))
    _invalid(lambda: _render(routing="global"))
    _invalid(lambda: _render(service_tier="priority"))
    _invalid(lambda: _render(rates=_rates(model_id="other-model")))
    _invalid(lambda: _render(rates=_rates(input_usd_per_million="NaN")))
    _invalid(lambda: _render(rates=_rates(currency="EUR")))
    _invalid(lambda: _render(rates="not-a-map"))
    _invalid(lambda: _render(rates=_rates(source_url="http://example.invalid/rates")))


def test_malicious_source_url_and_texts_do_not_leak_marker() -> None:
    _bad_source(f"https://user:pass@example.invalid/{MARKER}")
    _bad_source(f"http://example.invalid/{MARKER}")
    _bad_source(f"https://example.invalid/{MARKER}`")
    _bad_source(f"https://example.invalid/<{MARKER}>")
    _bad_source(f"https://example.invalid/[{MARKER}]")
    _bad_source(f"https://example.invalid/{MARKER}/\npath")
    _bad_source(f"https://example.invalid/{MARKER}/ path")
    _bad_source(f"https://example.invalid/{MARKER}\\")
    _bad_source(f"https://example.invalid/{MARKER}\u2028path")
    _bad_source(f"https://example.invalid/{MARKER}\u00a0path")
    _bad_source(f"https://example.invalid/{MARKER}\u200bpath")
    _invalid(lambda: _render(model_id=f"evil `{MARKER}`"))
    _invalid(lambda: _render(rates=_rates(model_id=f"[{MARKER}]")))
    _invalid(lambda: _render(_telemetry(known_usage_slots=MARKER)))


def test_caller_inputs_are_unmodified() -> None:
    telemetry = _telemetry()
    rates = _rates()
    snap_t = deepcopy(telemetry)
    snap_r = deepcopy(rates)
    text = render_cost_markdown(
        MappingProxyType(telemetry),
        MappingProxyType(rates),
        model_id=MODEL_ID,
        source_region=REGION,
    )
    assert telemetry == snap_t
    assert rates == snap_r
    assert f"estimated_usd: {KNOWN}" in text
    render_cost_markdown(
        telemetry,
        rates,
        model_id=MODEL_ID,
        source_region=REGION,
    )
    assert telemetry == snap_t
    assert rates == snap_r
