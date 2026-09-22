"""Dated explicit token-cost estimates from evaluation telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal

from app.evaluation_rates import TokenRateConfig, token_rate_config

_TELEMETRY_ERROR = "telemetry is invalid"
_MATCH_ERROR = "model metadata does not match"
_SCOPE = (
    "Text input/output token estimate only. Excludes cache, other charges, "
    "and account adjustments. Not an AWS invoice or observed billing."
)

__all__ = ["TokenRateConfig", "estimate_token_cost", "token_rate_config"]


def estimate_token_cost(
    telemetry: Mapping[str, object],
    rates: TokenRateConfig | Mapping[str, object],
    *,
    model_id: str,
    source_region: str,
    routing: str = "geographic",
    service_tier: str = "standard",
) -> dict[str, object]:
    config = token_rate_config(rates)
    wanted = {
        "model_id": model_id,
        "source_region": source_region,
        "routing": routing,
        "service_tier": service_tier,
    }
    if any(getattr(config, key) != item for key, item in wanted.items()):
        raise ValueError(_MATCH_ERROR)
    if any(key in telemetry and telemetry[key] != item for key, item in wanted.items()):
        raise ValueError(_MATCH_ERROR)

    def count(item: object) -> int:
        if type(item) is not int or item < 0:
            raise ValueError(_TELEMETRY_ERROR)
        return item

    observed = count(telemetry.get("observed_slots"))
    known_slots = count(telemetry.get("known_usage_slots"))
    unknown_slots = count(telemetry.get("unknown_usage_slots"))
    known_in = count(telemetry.get("known_input_tokens"))
    known_out = count(telemetry.get("known_output_tokens"))
    tokens = (telemetry.get("input_tokens"), telemetry.get("output_tokens"))
    overall_in = None if tokens[0] is None else count(tokens[0])
    overall_out = None if tokens[1] is None else count(tokens[1])
    overall_known = known_slots > 0 and unknown_slots == 0
    if (
        known_slots + unknown_slots != observed
        or (known_slots == 0 and (known_in != 0 or known_out != 0))
        or (overall_known and (overall_in != known_in or overall_out != known_out))
        or (not overall_known and (overall_in is not None or overall_out is not None))
    ):
        raise ValueError(_TELEMETRY_ERROR)
    known_cost: str | None = None
    if known_slots > 0:
        total = Decimal(known_in) * config.input_usd_per_million
        total += Decimal(known_out) * config.output_usd_per_million
        text = format(total / Decimal("1000000"), "f")
        pad = "0" * max(0, 8 - len(text.partition(".")[2]))
        known_cost = (text if "." in text else f"{text}.") + pad
    result: dict[str, object] = {str(k): v for k, v in asdict(config).items()}
    result["input_usd_per_million"] = format(config.input_usd_per_million, "f")
    result["output_usd_per_million"] = format(config.output_usd_per_million, "f")
    result["effective_date"] = config.effective_date.isoformat()
    result["retrieved_date"] = config.retrieved_date.isoformat()
    result["known_subset_estimated_usd"] = known_cost
    result["estimated_usd"] = known_cost if overall_known else None
    result["scope"] = _SCOPE
    return result
