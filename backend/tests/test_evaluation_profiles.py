import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app import evaluation_cli_config as cli
from app.evaluation_profiles import PROFILES, ModelProfile, rates_for, resolve_profile

CORPUS = Path(__file__).parent / "evaluation" / "scenarios.json"
REVISION = "40d41fdec79d7c24e964c570d3afe19328addb74"
REGIONS = frozenset({"us-east-1", "us-west-2"})


def rates_body(model_id: str, region: str = "us-east-1") -> dict[str, object]:
    return {
        "model_id": model_id,
        "region": region,
        "currency": "USD",
        "input_usd_per_1000": "0.0003300000",
        "output_usd_per_1000": "0.0027500000",
        "source_url": "https://pricing.us-east-1.amazonaws.com/index.json",
        "source_version": "test-rates-v1",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def write_rates(tmp_path: Path, body: dict[str, object]) -> Path:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(body))
    return path


def test_exactly_three_profiles_with_fixed_fields() -> None:
    assert {
        name: (p.model_id, p.family, p.id_verified) for name, p in PROFILES.items()
    } == {
        "nova-2-lite": ("us.amazon.nova-2-lite-v1:0", "nova", True),
        "nova-2-pro": ("us.amazon.nova-2-pro-v1:0", "nova", False),
        "claude-haiku": ("us.anthropic.claude-haiku-5-5", "claude", False),
    }
    for name, profile in PROFILES.items():
        assert profile.name == name
        assert profile.regions == REGIONS


def test_profile_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        PROFILES["nova-2-lite"].name = "x"  # type: ignore[misc]


@pytest.mark.parametrize("name", list(PROFILES))
@pytest.mark.parametrize("region", sorted(REGIONS))
def test_resolve_profile_accepts_allowlist(name: str, region: str) -> None:
    profile = resolve_profile(name, region)
    assert isinstance(profile, ModelProfile)
    assert profile is PROFILES[name]


@pytest.mark.parametrize(
    ("name", "region"),
    [
        ("nova-2-micro", "us-east-1"),
        ("", "us-east-1"),
        ("NOVA-2-LITE", "us-east-1"),
        ("us.amazon.nova-2-lite-v1:0", "us-east-1"),
        ("nova-2-lite", "eu-west-1"),
        ("claude-haiku", ""),
        ("claude-haiku", "US-EAST-1"),
    ],
)
def test_resolve_profile_rejects_unknown_name_or_region_with_one_message(
    name: str, region: str
) -> None:
    with pytest.raises(ValueError) as error:
        resolve_profile(name, region)
    assert str(error.value) == "Invalid model profile"


@pytest.mark.parametrize("name", list(PROFILES))
def test_rates_for_accepts_matching_file(tmp_path: Path, name: str) -> None:
    profile = PROFILES[name]
    path = write_rates(tmp_path, rates_body(profile.model_id, "us-west-2"))

    rates = rates_for(profile, path)

    assert rates.model_id == profile.model_id
    assert rates.region == "us-west-2"


def test_rates_for_rejects_other_model_id(tmp_path: Path) -> None:
    path = write_rates(tmp_path, rates_body(PROFILES["nova-2-pro"].model_id))

    with pytest.raises(ValueError, match=r"^Invalid evaluation rates\.$"):
        rates_for(PROFILES["nova-2-lite"], path)


def test_rates_for_rejects_region_outside_profile(tmp_path: Path) -> None:
    profile = PROFILES["claude-haiku"]
    path = write_rates(tmp_path, rates_body(profile.model_id, "eu-west-1"))

    with pytest.raises(ValueError, match="^Invalid model profile$"):
        rates_for(profile, path)


@pytest.mark.parametrize(
    "model_id",
    [
        profile.model_id
        for profile in PROFILES.values()
        if profile.name != "nova-2-lite"
    ],
)
def test_batch_cli_still_accepts_only_nova_2_lite(
    tmp_path: Path, model_id: str
) -> None:
    argv = [
        "--corpus",
        str(CORPUS),
        "--output-dir",
        str(tmp_path / "output"),
        "--revision",
        REVISION,
        "--model-id",
        model_id,
    ]

    with pytest.raises(ValueError, match="^Invalid evaluation CLI input$"):
        cli.load_options(argv, fixture=True)
