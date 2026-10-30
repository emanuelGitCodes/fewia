from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from app.evaluation_cost_rates import EvaluationRates, parse_rates
from app.evaluation_io import load_json

_INVALID = "Invalid model profile"
_REGIONS = frozenset({"us-east-1", "us-west-2"})


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model_id: str
    family: Literal["nova", "claude"]
    regions: frozenset[str]
    model_config: dict[str, object]
    id_verified: bool


_NOVA_CONFIG: dict[str, object] = {
    "max_tokens": 4096,
    "temperature": 0,
    "reasoning_effort": "low",
}

PROFILES: dict[str, ModelProfile] = {
    profile.name: profile
    for profile in (
        ModelProfile(
            "nova-2-lite",
            "us.amazon.nova-2-lite-v1:0",
            "nova",
            _REGIONS,
            _NOVA_CONFIG,
            True,
        ),
        ModelProfile(
            "nova-2-pro",
            "us.amazon.nova-2-pro-v1:0",
            "nova",
            _REGIONS,
            _NOVA_CONFIG,
            False,
        ),
        ModelProfile(
            "claude-haiku",
            "us.anthropic.claude-haiku-5-5",
            "claude",
            _REGIONS,
            {"max_tokens": 4096},
            False,
        ),
    )
}


def resolve_profile(name: str, region: str) -> ModelProfile:
    profile = PROFILES.get(name) if isinstance(name, str) else None
    if profile is None or not isinstance(region, str) or region not in profile.regions:
        raise ValueError(_INVALID)
    return replace(profile, model_config=dict(profile.model_config))


def rates_for(profile: ModelProfile, path: Path, region: str) -> EvaluationRates:
    rates = load_json(path)
    if (
        not isinstance(region, str)
        or region not in profile.regions
        or rates.get("region") != region
    ):
        raise ValueError(_INVALID)
    return parse_rates(rates, model_id=profile.model_id, region=region)
