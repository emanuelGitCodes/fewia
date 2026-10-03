import math
from typing import cast

from app.evaluation_cost_rates import parse_rates
from app.evaluation_markdown_format import source_link, table
from app.evaluation_markdown_values import as_map, pick, require, slots, text

_PRICING_FIELDS = (
    "model_id region currency input_usd_per_1000 output_usd_per_1000 "
    "source_url source_version published_at effective_date retrieved_at"
)


def _labels(source: dict[str, object], fields: str) -> tuple[str, ...]:
    return tuple(text(source[key], r"(?s).*\S.*") for key in fields.split())


def _numbers(
    source: dict[str, object],
    fields: str,
    *,
    seconds: bool = False,
    nullable: bool = False,
) -> tuple[object, ...]:
    values = tuple(source[key] for key in fields.split())
    for value in values:
        if value is None and nullable:
            continue
        valid = type(value) is int
        valid |= seconds and type(value) is float and math.isfinite(value)
        require(valid and cast(int | float, value) >= 0)
    return values


def _amount(value: object) -> str | None:
    return None if value is None else text(value, r"[0-9]+(?:\.[0-9]+)?")


def _measurements(source: dict[str, object]) -> list[str]:
    parts = [table(("Total slots",), [_numbers(source, "total_slots")])]
    for group in slots(source["groups"]):
        labels = _labels(group, "condition evidence_class")
        parts.append(table(("Condition", "Evidence"), [labels]))
        counts = (
            "total_slots observed_slots known_usage_slots unknown_usage_slots "
            "known_usage_turns unknown_usage_turns"
        )
        tokens = "input_tokens output_tokens known_input_tokens known_output_tokens"
        values = dict(zip(counts.split(), _numbers(group, counts), strict=True))
        values.update(
            zip(tokens.split(), _numbers(group, tokens, nullable=True), strict=True)
        )
        parts.append("Known input/output token totals are lower bounds.")
        rows = [(key.replace("_", " "), value) for key, value in values.items()]
        parts.append(table(("Usage metric", "Value"), rows))
        calls = as_map(group["provider_calls"])
        call_values = (
            *_numbers(calls, "total known_total", nullable=True),
            *_numbers(calls, "sample_count unknown_count unknown_slot_count"),
        )
        parts.append("Provider-call samples and unknown counts refer to turns.")
        headers = ("Calls", "Known lower bound", "Samples", "Unknown", "Unknown slots")
        parts.append(table(headers, [call_values]))
        latency = as_map(group["slot_elapsed_seconds"])
        require(latency["percentile_method"] == "nearest-rank")
        latency_values = (
            *_numbers(latency, "p50 p95", seconds=True, nullable=True),
            *_numbers(latency, "sample_count unknown_count"),
            "nearest-rank",
        )
        parts.append("Slot latency measures end-to-end seconds.")
        parts.append(
            table(
                ("p50 (s)", "p95 (s)", "Sample slots", "Unknown slots", "Method"),
                [latency_values],
            )
        )
    return parts


def _cost(source: dict[str, object]) -> list[str]:
    status = text(source["status"], r"estimated|unknown|not_applicable")
    model, region, currency = _labels(source, "model_id region currency")
    require(currency == "USD")
    rows: list[tuple[object, ...]] = [
        ("Status", status),
        ("Estimated USD", _amount(source["estimated_usd"])),
        ("Known usage lower bound (USD)", _amount(source["known_usage_lower_bound"])),
        ("Model", model),
        ("Region", region),
        ("Currency", currency),
    ]
    parts = [table(("Cost field", "Value"), rows)]
    rows = []
    for group in slots(source["groups"]):
        rows.append(
            (
                *_labels(group, "condition evidence_class"),
                text(group["status"], r"estimated|unknown|not_applicable"),
                _amount(group["known_usage_lower_bound"]),
            )
        )
    parts.append(
        table(("Condition", "Evidence", "Cost status", "Known lower bound (USD)"), rows)
    )
    if source["pricing"] is None:
        parts.append("Pricing evidence: unavailable.")
    else:
        pricing = pick(as_map(source["pricing"]), _PRICING_FIELDS)
        parse_rates(pricing, model_id=model, region=region)
        url = text(pricing["source_url"], r"(?s).{1,256}")
        parts.append(source_link("Pricing source", url))
        rows = [
            (key, pricing[key])
            for key in _PRICING_FIELDS.split()
            if key != "source_url"
        ]
        parts.append(table(("Pricing field", "Value"), rows))
    parts.append(
        "Token-cost estimate in USD. Excludes taxes, other AWS resources, caching "
        "discounts, and billing reconciliation. Not an AWS bill. Model billing is "
        "not applicable for local/fake evidence; this does not mean a live benchmark "
        "is free."
    )
    return parts


def render_telemetry(
    telemetry: dict[str, object] | None, cost: dict[str, object] | None
) -> str:
    try:
        parts: list[str] = []
        for title, value, render in (
            ("Measured telemetry", telemetry, _measurements),
            ("Estimated cost", cost, _cost),
        ):
            parts.append(f"## {title}")
            if value is None:
                parts.append("Unavailable (legacy report).")
            else:
                parts.extend(render(as_map(value)))
        return "\n\n".join(parts)
    except (KeyError, ValueError):
        raise ValueError("Invalid evaluation report input") from None
