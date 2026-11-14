from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from pathlib import Path
from typing import Literal

from app.agent.provider import LLMUnavailable
from app.evaluation_cost_rates import EvaluationRates, parse_rates

MAX_INPUT_TOKENS = 65_536
MAX_OUTPUT_TOKENS = 4_096
_PROFILES = frozenset({"us.amazon.nova-2-lite-v1:0", "us.amazon.nova-2-pro-v1:0"})
_ARTIFACT = Path(__file__).resolve().parents[1] / "providers" / "runtime_rates.json"


class ModelRatesUnavailable(LLMUnavailable):
    code = "model_rates_unavailable"

    def __init__(self) -> None:
        super().__init__("Model rates are unavailable. Do not retry this call.")


def canonical_model(model_id: str, region: str) -> str:
    if model_id == "gpt-6-luna" and region in {"global", "us"}:
        return model_id
    if region == "us-east-1":
        if model_id in _PROFILES:
            return model_id
        match = re.fullmatch(
            r"arn:aws:bedrock:us-east-1:[0-9]{12}:inference-profile/(.+)", model_id
        )
        if match is not None and match[1] in _PROFILES:
            return match[1]
    raise ModelRatesUnavailable()


def _positive_rates(rates: EvaluationRates) -> None:
    prices = (
        (rates.input_usd_per_1000, False),
        (rates.output_usd_per_1000, False),
        (rates.cached_input_usd_per_1000, False),
        (rates.cache_write_usd_per_1000, True),
        (rates.cache_write_30m_usd_per_1000, False),
        (rates.cache_write_12h_usd_per_1000, False),
    )
    for price, allow_zero in prices:
        if price is not None and (
            not price.is_finite()
            or price < 0
            or (not allow_zero and price == 0)
            or price > Decimal("1000000")
            or len(price.as_tuple().digits) > 30
            or abs(int(price.as_tuple().exponent)) > 30
        ):
            raise ModelRatesUnavailable()


@dataclass(frozen=True)
class RuntimeRates:
    record: EvaluationRates
    version: str

    def __post_init__(self) -> None:
        _positive_rates(self.record)
        if (
            canonical_model(self.record.model_id, self.record.region)
            != self.record.model_id
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.version) is None
        ):
            raise ModelRatesUnavailable()
        if self.provider == "openai":
            if (
                self.record.cache_write_usd_per_1000 is not None
                or self.record.cache_write_30m_usd_per_1000 is None
                or self.record.cache_write_12h_usd_per_1000 is None
            ):
                raise ModelRatesUnavailable()
        elif (
            self.record.cache_write_30m_usd_per_1000 is not None
            or self.record.cache_write_12h_usd_per_1000 is not None
        ):
            raise ModelRatesUnavailable()

    @property
    def provider(self) -> Literal["openai", "bedrock"]:
        return "openai" if self.record.model_id == "gpt-6-luna" else "bedrock"

    @property
    def unclassified_input_rate(self) -> Decimal:
        return max(
            self.record.input_usd_per_1000,
            self.record.cache_write_30m_usd_per_1000 or Decimal(0),
            self.record.cache_write_12h_usd_per_1000 or Decimal(0),
        )

    def cost(
        self, incoming: int, outgoing: int, cached: int = 0, written: int = 0
    ) -> int:
        if (
            any(
                type(value) is not int or value < 0
                for value in (incoming, outgoing, cached, written)
            )
            or incoming + cached + written > MAX_INPUT_TOKENS
            or outgoing > MAX_OUTPUT_TOKENS
            or (self.provider == "openai" and written != 0)
        ):
            raise ModelRatesUnavailable()
        cached_rate = self.record.cached_input_usd_per_1000
        write_rate = self.record.cache_write_usd_per_1000
        if (cached and cached_rate is None) or (written and write_rate is None):
            raise ModelRatesUnavailable()
        incoming_rate = (
            self.unclassified_input_rate
            if self.provider == "openai"
            else self.record.input_usd_per_1000
        )
        with localcontext() as context:
            context.prec = 100
            amount = (
                Decimal(incoming) * incoming_rate
                + Decimal(outgoing) * self.record.output_usd_per_1000
                + Decimal(cached) * (cached_rate or Decimal(0))
                + Decimal(written) * (write_rate or Decimal(0))
            ) * 1000
            return int(amount.to_integral_value(rounding=ROUND_CEILING))

    @property
    def reservation_microdollars(self) -> int:
        with localcontext() as context:
            context.prec = 100
            incoming_rate = max(
                self.record.input_usd_per_1000,
                self.record.cached_input_usd_per_1000 or Decimal(0),
                self.record.cache_write_usd_per_1000 or Decimal(0),
                self.record.cache_write_30m_usd_per_1000 or Decimal(0),
                self.record.cache_write_12h_usd_per_1000 or Decimal(0),
            )
            amount = (
                Decimal(MAX_INPUT_TOKENS) * incoming_rate
                + Decimal(MAX_OUTPUT_TOKENS) * self.record.output_usd_per_1000
            ) * 1000
            return int(amount.to_integral_value(rounding=ROUND_CEILING))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ModelRatesUnavailable()
        result[key] = value
    return result


def load_runtime_rates(
    *, model_id: str, region: str, test_rates_path: Path | None = None
) -> RuntimeRates:
    """The caller MUST use test_rates_path only for isolated test injection."""
    canonical = canonical_model(model_id, region)
    try:
        payload = (test_rates_path or _ARTIFACT).read_bytes()
        if len(payload) > 1_048_576:
            raise ModelRatesUnavailable()
        artifact: object = json.loads(payload, object_pairs_hook=_unique_object)
        records = artifact.get("rates") if isinstance(artifact, dict) else artifact
        if not isinstance(records, list) or not records:
            raise ModelRatesUnavailable()
        matches: list[EvaluationRates] = []
        seen: set[tuple[str, str]] = set()
        for raw in records:
            if not isinstance(raw, dict):
                raise ModelRatesUnavailable()
            record_model, record_region = raw.get("model_id"), raw.get("region")
            if not isinstance(record_model, str) or not isinstance(record_region, str):
                raise ModelRatesUnavailable()
            rates = parse_rates(raw, model_id=record_model, region=record_region)
            key = (rates.model_id, rates.region)
            if key in seen:
                raise ModelRatesUnavailable()
            seen.add(key)
            _positive_rates(rates)
            if key == (canonical, region):
                matches.append(rates)
        if len(matches) != 1:
            raise ModelRatesUnavailable()
        identity = json.dumps(
            {"artifact": artifact, "model_id": canonical, "region": region},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        version = "sha256:" + hashlib.sha256(identity).hexdigest()
        return RuntimeRates(matches[0], version)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        raise ModelRatesUnavailable() from None
