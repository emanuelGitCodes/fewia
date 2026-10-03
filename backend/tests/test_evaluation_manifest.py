import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_manifest as manifests
from app.agent import chat_loop
from app.domain import catalog
from app.domain.grocery import SUPPORTED_RECIPE_IDS


@pytest.fixture
def corpus() -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _manifest(
    corpus: dict[str, object],
    config: dict[str, object] | None = None,
    *,
    model_id: str = "us.openai.gpt-6-luna",
    region: str = "us-east-1",
) -> dict[str, object]:
    if config is None:
        config = {"max_tokens": 4096, "reasoning_effort": "low"}
    return manifests.build_manifest(
        corpus,
        model_id=model_id,
        region=region,
        model_config=config,
    )


def _hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_catalog_contains_complete_current_facts() -> None:
    snapshot = manifests.catalog_snapshot()
    recipes = cast(list[dict[str, object]], snapshot["recipes"])
    ingredients = cast(list[dict[str, object]], snapshot["ingredients"])
    assert snapshot["version"] == catalog.CATALOG_VERSION
    assert snapshot["estimate_notice"] == catalog.ESTIMATE_NOTICE
    assert len(recipes) == 40
    assert len(ingredients) == 22
    assert [item["id"] for item in recipes] == sorted(SUPPORTED_RECIPE_IDS)
    assert ingredients == [
        asdict(item)
        for item in sorted(catalog.INGREDIENTS.values(), key=lambda item: item.id)
    ]
    for record in recipes:
        recipe = catalog.RECIPES[cast(str, record["id"])]
        assert record == {
            "id": recipe.id,
            "servings": recipe.servings,
            "ingredients": [
                {"ingredient_id": ingredient_id, "quantity": quantity}
                for ingredient_id, quantity in sorted(recipe.ingredients)
            ],
        }
    assert "expected" not in json.dumps(snapshot)


def test_manifest_hashes_match_canonical_json(corpus: dict[str, object]) -> None:
    manifest = _manifest(corpus)
    assert manifest["corpus_hash"] == _hash(corpus)
    assert manifest["catalog_hash"] == _hash(manifest["catalog"])
    assert manifest["system_prompt_hash"] == _hash(chat_loop.SYSTEM_PROMPT)
    assert manifest["model_config_hash"] == _hash(manifest["model_config"])
    identity = manifest.pop("manifest_hash")
    assert identity == _hash(manifest)
    assert manifest["conditions"] == ["tool_enabled", "no_tool", "deterministic"]
    assert manifest["model_id"] == "us.openai.gpt-6-luna"
    assert manifest["region"] == "us-east-1"
    assert manifest["catalog_version"] == catalog.CATALOG_VERSION
    assert set(manifest) == {
        "version",
        "corpus_hash",
        "catalog",
        "catalog_hash",
        "catalog_version",
        "system_prompt_hash",
        "model_id",
        "region",
        "model_config",
        "model_config_hash",
        "conditions",
    }


def test_nested_key_order_does_not_change_hashes() -> None:
    left: dict[str, object] = {"scenario": {"prompt": "meal", "inputs": {"x": 1}}}
    right: dict[str, object] = {"scenario": {"inputs": {"x": 1}, "prompt": "meal"}}
    assert _manifest(left, {"max_tokens": 1024, "temperature": 0}) == _manifest(
        right, {"temperature": 0, "max_tokens": 1024}
    )


def test_catalog_order_does_not_change_hashes(
    corpus: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _manifest(corpus)
    monkeypatch.setattr(
        catalog, "INGREDIENTS", dict(reversed(catalog.INGREDIENTS.items()))
    )
    recipes = {
        key: replace(recipe, ingredients=tuple(reversed(recipe.ingredients)))
        for key, recipe in reversed(catalog.RECIPES.items())
    }
    monkeypatch.setattr(catalog, "RECIPES", recipes)
    assert _manifest(corpus) == before


@pytest.mark.parametrize("change", ["recipe", "price", "diet", "version"])
def test_catalog_changes_alter_catalog_and_manifest_hashes(
    corpus: dict[str, object], monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    before = _manifest(corpus)
    if change == "recipe":
        recipe = catalog.RECIPES["chicken_tacos"]
        ingredient_id, quantity = recipe.ingredients[0]
        monkeypatch.setitem(
            catalog.RECIPES,
            recipe.id,
            replace(
                recipe,
                ingredients=((ingredient_id, quantity + 1),) + recipe.ingredients[1:],
            ),
        )
    elif change == "version":
        monkeypatch.setattr(catalog, "CATALOG_VERSION", "sample-prices-test")
    else:
        ingredient = catalog.INGREDIENTS["eggs"]
        updated = (
            replace(ingredient, price_cents=350)
            if change == "price"
            else replace(ingredient, vegan=True)
        )
        monkeypatch.setitem(catalog.INGREDIENTS, ingredient.id, updated)
    after = _manifest(corpus)
    assert after["catalog_hash"] != before["catalog_hash"]
    assert after["manifest_hash"] != before["manifest_hash"]
    assert after["corpus_hash"] == before["corpus_hash"]
    assert after["system_prompt_hash"] == before["system_prompt_hash"]


def test_prompt_change_alters_prompt_hash(
    corpus: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _manifest(corpus)
    monkeypatch.setattr(chat_loop, "SYSTEM_PROMPT", chat_loop.SYSTEM_PROMPT + " Test.")
    after = _manifest(corpus)
    assert after["system_prompt_hash"] != before["system_prompt_hash"]
    assert after["manifest_hash"] != before["manifest_hash"]
    assert after["catalog_hash"] == before["catalog_hash"]


def test_expected_corpus_change_alters_only_corpus_identity() -> None:
    corpus: dict[str, object] = {"expected": {"accepted": True}}
    before = _manifest(corpus)
    corpus["expected"] = {"accepted": False}
    after = _manifest(corpus)
    assert after["corpus_hash"] != before["corpus_hash"]
    assert after["manifest_hash"] != before["manifest_hash"]
    assert after["catalog_hash"] == before["catalog_hash"]
    assert after["system_prompt_hash"] == before["system_prompt_hash"]
    assert "expected" not in json.dumps(after)


@pytest.mark.parametrize(
    ("before_config", "after_config"),
    [
        ({"max_tokens": 1024}, {"max_tokens": 2048}),
        ({"temperature": 0}, {"temperature": 0.5}),
        ({"reasoning_effort": "low"}, {"reasoning_effort": "medium"}),
    ],
)
def test_config_changes_alter_config_hash(
    before_config: dict[str, object], after_config: dict[str, object]
) -> None:
    before = _manifest({}, before_config)
    after = _manifest({}, after_config)
    assert after["model_config_hash"] != before["model_config_hash"]
    assert after["manifest_hash"] != before["manifest_hash"]
    assert after["catalog_hash"] == before["catalog_hash"]


def test_model_and_region_change_run_identity(corpus: dict[str, object]) -> None:
    before = _manifest(corpus)
    model = _manifest(corpus, model_id="us.amazon.nova-2-lite-v1:0")
    region = _manifest(corpus, region="us-west-2")
    assert before["manifest_hash"] != model["manifest_hash"]
    assert before["manifest_hash"] != region["manifest_hash"]


def test_copy_isolation(corpus: dict[str, object]) -> None:
    config: dict[str, object] = {"max_tokens": 4096, "reasoning_effort": "low"}
    manifest = _manifest(corpus, config)
    original = json.loads(json.dumps(manifest))
    cast(dict[str, object], corpus["baseline"])["seed"] = 0
    config["max_tokens"] = 1
    assert manifest == original
    snapshot = cast(dict[str, object], manifest["catalog"])
    cast(list[dict[str, object]], snapshot["ingredients"])[0]["price_cents"] = 0
    first_recipe = cast(list[dict[str, object]], snapshot["recipes"])[0]
    cast(list[dict[str, object]], first_recipe["ingredients"])[0]["quantity"] = 0
    cast(dict[str, object], manifest["model_config"])["max_tokens"] = 2
    cast(list[str], manifest["conditions"]).clear()
    assert manifests.catalog_snapshot() == original["catalog"]
    assert _manifest({}, {"max_tokens": 4096})["model_config"] == {"max_tokens": 4096}
    assert _manifest({})["conditions"] == ["tool_enabled", "no_tool", "deterministic"]


@pytest.mark.parametrize(
    "config",
    [
        {"aws_secret_access_key": "TEST_ONLY_MARKER"},
        {"profile_name": "example"},
        {"additionalModelRequestFields": {}},
        {"max_tokens": True},
        {"max_tokens": 1.0},
        {"max_tokens": 0},
        {"max_tokens": 4097},
        {"temperature": False},
        {"temperature": -0.1},
        {"temperature": 1.1},
        {"temperature": float("nan")},
        {"temperature": float("inf")},
        {"reasoning_effort": True},
        {"reasoning_effort": "unknown"},
        [],
        None,
    ],
)
def test_invalid_config_has_static_error(config: object) -> None:
    with pytest.raises(ValueError) as caught:
        manifests.build_manifest(
            {},
            model_id="us.openai.gpt-6-luna",
            region="us-east-1",
            model_config=cast(dict[str, object], config),
        )
    assert str(caught.value) == (
        "model_config MUST contain valid allowed inference values"
    )
    assert "TEST_ONLY_MARKER" not in str(caught.value)


@pytest.mark.parametrize("model_id", ["", " ", "bad id", "x" * 257, None, True, []])
def test_invalid_model_id_has_static_error(model_id: object) -> None:
    with pytest.raises(ValueError) as caught:
        _manifest({}, model_id=cast(str, model_id))
    assert str(caught.value) == (
        "model_id MUST be a valid identifier of at most 256 characters"
    )


@pytest.mark.parametrize("region", ["", "eu-west-1", "us-east-1 ", None, True, []])
def test_invalid_region_has_static_error(region: object) -> None:
    with pytest.raises(ValueError) as caught:
        _manifest({}, region=cast(str, region))
    assert str(caught.value) == "region MUST be us-east-1 or us-west-2"


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), (1, 2), {1, 2}, object(), {1: "x"}],
)
def test_non_json_corpus_values_have_static_error(value: object) -> None:
    with pytest.raises(ValueError) as caught:
        _manifest({"nested": [value]})
    assert str(caught.value) == "evaluation facts MUST contain finite JSON data"


def test_cyclic_corpus_has_static_error() -> None:
    corpus: dict[str, object] = {}
    corpus["cycle"] = corpus
    with pytest.raises(
        ValueError, match="evaluation facts MUST contain finite JSON data"
    ):
        _manifest(corpus)


@pytest.mark.parametrize("corpus", [None, [], "corpus"])
def test_corpus_requires_an_object(corpus: object) -> None:
    with pytest.raises(
        ValueError, match="evaluation facts MUST contain finite JSON data"
    ):
        _manifest(cast(dict[str, object], corpus))


def test_json_values_and_missing_sample_prices_remain_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingredient = catalog.INGREDIENTS["eggs"]
    monkeypatch.setitem(
        catalog.INGREDIENTS, ingredient.id, replace(ingredient, price_cents=None)
    )
    manifest = _manifest({"data": [None, True, False, 1, 0.5, "meal"]}, {})
    snapshot = cast(dict[str, object], manifest["catalog"])
    ingredients = cast(list[dict[str, object]], snapshot["ingredients"])
    eggs = next(item for item in ingredients if item["id"] == "eggs")
    assert eggs["price_cents"] is None
