from decimal import Decimal, localcontext
from typing import cast

from app.evaluation_cost_rates import EvaluationRates, parse_rates

_SCOPE = (
    "Token-cost estimate in USD. Excludes taxes, other AWS resources, caching "
    "discounts, and actual billing reconciliation. Not an AWS bill."
)
_LOCAL = {"deterministic_fake_provider", "deterministic_domain", "local_postgresql"}


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _cost(input_tokens: int, output_tokens: int, rates: EvaluationRates) -> Decimal:
    terms = (rates.input_usd_per_1000, rates.output_usd_per_1000)
    digits = max(len(str(input_tokens)), len(str(output_tokens)))
    low = min(int(term.as_tuple().exponent) for term in terms)
    high = max(term.adjusted() for term in terms)
    with localcontext() as context:
        context.prec = max(28, high - low + digits + 4)
        return (input_tokens * terms[0] + output_tokens * terms[1]) / Decimal(1000)


def estimate_cost(
    telemetry: dict[str, object],
    rates: dict[str, object] | None,
    *,
    model_id: str,
    region: str,
) -> dict[str, object]:
    config: EvaluationRates | None = None
    if rates is not None:
        try:
            config = parse_rates(rates, model_id=model_id, region=region)
        except ValueError:
            if not isinstance(rates, dict):
                raise ValueError("rates are invalid") from None
            try:
                parse_rates(
                    rates,
                    model_id=cast(str, rates.get("model_id")),
                    region=cast(str, rates.get("region")),
                )
            except ValueError:
                raise ValueError("rates are invalid") from None
            raise ValueError("rates do not match model and region") from None
    groups = telemetry.get("groups")
    rows: list[dict[str, object]] = []
    known_input = known_output = covered_slots = 0
    has_known = False
    valid_coverage = isinstance(groups, list)
    for item in groups if isinstance(groups, list) else []:
        group = cast(dict[str, object], item) if isinstance(item, dict) else {}
        total_slots = _count(group.get("total_slots"))
        valid_coverage &= total_slots is not None and total_slots > 0
        covered_slots += total_slots or 0
        condition, evidence = group.get("condition"), group.get("evidence_class")
        local = evidence in _LOCAL if isinstance(evidence, str) else False
        status = "not_applicable" if local else "unknown"
        known: Decimal | None = None
        samples = group.get("slots")
        valid_models = (
            isinstance(samples, list)
            and total_slots is not None
            and total_slots > 0
            and len(samples) == total_slots
            and all(
                isinstance(sample, dict) and sample.get("model_id") == model_id
                for sample in samples
            )
        )
        if evidence == "real_bedrock" and config and valid_models:
            inputs = _count(group.get("known_input_tokens"))
            outputs = _count(group.get("known_output_tokens"))
            if inputs is not None or outputs is not None:
                known = _cost(inputs or 0, outputs or 0, config)
                known_input += inputs or 0
                known_output += outputs or 0
                has_known = True
            slots = _count(group.get("known_usage_slots"))
            complete = slots is not None and slots > 0
            complete &= slots == total_slots
            complete &= _count(group.get("unknown_usage_slots")) == 0
            for key, count in (("input", inputs), ("output", outputs)):
                complete &= count is not None
                complete &= count == _count(group.get(f"{key}_tokens"))
            status = "estimated" if complete else "unknown"
        amount = format(known, "f") if known is not None else None
        rows.append(
            {
                "condition": condition,
                "evidence_class": evidence,
                "status": status,
                "known_usage_lower_bound": amount,
            }
        )
    applicable = [row["status"] for row in rows if row["status"] != "not_applicable"]
    cost = _cost(known_input, known_output, config) if has_known and config else None
    lower_bound = format(cost, "f") if cost is not None else None
    status = "unknown" if not applicable or "unknown" in applicable else "estimated"
    if rows and not applicable:
        status = "not_applicable"
    if not valid_coverage or _count(telemetry.get("total_slots")) != covered_slots:
        status = "unknown"
    return {
        "status": status,
        "estimated_usd": lower_bound if status == "estimated" else None,
        "known_usage_lower_bound": lower_bound,
        "currency": "USD",
        "model_id": model_id,
        "region": region,
        "pricing": config.model_dump(mode="json") if config else None,
        "scope": _SCOPE,
        "groups": rows,
    }
