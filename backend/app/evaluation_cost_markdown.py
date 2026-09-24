"""Markdown section for dated token-cost estimates."""

import unicodedata
from collections.abc import Mapping
from re import compile
from typing import NoReturn
from urllib.parse import urlparse

from app.evaluation_cost import TokenRateConfig, estimate_token_cost
from app.evaluation_report_values import INVALID, label

_AMOUNT = compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_FIELDS = (
    "estimated_usd",
    "known_subset_estimated_usd",
    "input_usd_per_million",
    "output_usd_per_million",
    "currency",
    "model_id",
    "source_region",
    "routing",
    "service_tier",
    "effective_date",
    "retrieved_date",
    "source_url",
)
_SCOPE = (
    "Text input/output token estimate only. Excludes cache, other charges, "
    "and account adjustments. Not an AWS invoice or observed billing."
)


def _reject() -> NoReturn:
    raise ValueError(INVALID)


def _amount(value: object) -> str:
    if value is None:
        return "unknown"
    if type(value) is not str or len(value) > 48:
        _reject()
    if _AMOUNT.fullmatch(value) is None:
        _reject()
    return value


def _href(value: object) -> str:
    if type(value) is not str or not (8 <= len(value) <= 512):
        _reject()
    for char in value:
        if (
            char in "`<>[]\\"
            or char.isspace()
            or unicodedata.category(char).startswith("C")
        ):
            _reject()
    try:
        parsed = urlparse(value)
    except ValueError:
        raise ValueError(INVALID) from None
    host = parsed.hostname
    if parsed.scheme != "https" or host is None or host == "":
        _reject()
    if parsed.username is not None or parsed.password is not None:
        _reject()
    return value.replace("(", "%28").replace(")", "%29")


def render_cost_markdown(
    telemetry: Mapping[str, object],
    rates: TokenRateConfig | Mapping[str, object],
    *,
    model_id: str,
    source_region: str,
    routing: str = "geographic",
    service_tier: str = "standard",
) -> str:
    try:
        raw = estimate_token_cost(
            telemetry,
            rates,
            model_id=model_id,
            source_region=source_region,
            routing=routing,
            service_tier=service_tier,
        )
    except Exception:
        raise ValueError(INVALID) from None
    if any(key not in raw for key in _FIELDS):
        _reject()
    estimated = _amount(raw["estimated_usd"])
    subset = _amount(raw["known_subset_estimated_usd"])
    in_rate = raw["input_usd_per_million"]
    out_rate = raw["output_usd_per_million"]
    if in_rate is None or out_rate is None:
        _reject()
    href = _href(raw["source_url"])
    return "\n".join(
        [
            "## Estimated model cost",
            "",
            f"estimated_usd: {estimated}",
            f"known_subset_estimated_usd: {subset}",
            f"currency: {label(raw['currency'])}",
            f"input_usd_per_million: {_amount(in_rate)}",
            f"output_usd_per_million: {_amount(out_rate)}",
            f"model_id: {label(raw['model_id'])}",
            f"source_region: {label(raw['source_region'])}",
            f"routing: {label(raw['routing'])}",
            f"service_tier: {label(raw['service_tier'])}",
            f"effective_date: {label(raw['effective_date'])}",
            f"retrieved_date: {label(raw['retrieved_date'])}",
            f"source_url: [source]({href})",
            "",
            _SCOPE,
            "",
        ]
    )
