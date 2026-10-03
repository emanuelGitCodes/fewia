import hashlib
import json
import math
import re
from dataclasses import asdict
from typing import cast

from app.agent import chat_loop
from app.domain import catalog
from app.evaluation_baseline_response import BASELINE_SYSTEM_PROMPT

_CONFIG_KEYS = frozenset({"max_tokens", "temperature", "reasoning_effort"})
_REGIONS = frozenset({"us-east-1", "us-west-2"})
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_JSON_ERROR = "evaluation facts MUST contain finite JSON data"
_CONFIG_ERROR = "model_config MUST contain valid allowed inference values"


def _validate_json(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _validate_json(item)
        return
    if type(value) is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError(_JSON_ERROR)
            _validate_json(item)
        return
    raise ValueError(_JSON_ERROR)


def _canonical_json(value: object) -> str:
    try:
        _validate_json(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValueError(_JSON_ERROR) from None


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _copy_object(value: dict[str, object]) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(_JSON_ERROR)
    return cast(dict[str, object], json.loads(_canonical_json(value)))


def catalog_snapshot() -> dict[str, object]:
    """Return catalog facts with sample prices in integer USD cents."""
    snapshot: dict[str, object] = {
        "version": catalog.CATALOG_VERSION,
        "estimate_notice": catalog.ESTIMATE_NOTICE,
        "recipes": [
            {
                "id": recipe.id,
                "servings": recipe.servings,
                "ingredients": [
                    {"ingredient_id": ingredient_id, "quantity": quantity}
                    for ingredient_id, quantity in sorted(recipe.ingredients)
                ],
            }
            for recipe in sorted(catalog.RECIPES.values(), key=lambda item: item.id)
        ],
        "ingredients": [
            asdict(ingredient)
            for ingredient in sorted(
                catalog.INGREDIENTS.values(), key=lambda item: item.id
            )
        ],
    }
    return _copy_object(snapshot)


def _validate_config(config: dict[str, object]) -> None:
    if type(config) is not dict or not set(config).issubset(_CONFIG_KEYS):
        raise ValueError(_CONFIG_ERROR)
    if "max_tokens" in config:
        tokens = config["max_tokens"]
        if (
            not isinstance(tokens, int)
            or type(tokens) is bool
            or not 1 <= tokens <= 4096
        ):
            raise ValueError(_CONFIG_ERROR)
    if "temperature" in config:
        temperature = config["temperature"]
        if type(temperature) not in (int, float):
            raise ValueError(_CONFIG_ERROR)
        if not 0 <= cast(float, temperature) <= 1:
            raise ValueError(_CONFIG_ERROR)
    if "reasoning_effort" in config:
        effort = config["reasoning_effort"]
        if type(effort) is not str or effort not in ("low", "medium", "high"):
            raise ValueError(_CONFIG_ERROR)


def build_manifest(
    corpus: dict[str, object],
    *,
    model_id: str,
    region: str,
    model_config: dict[str, object],
) -> dict[str, object]:
    """Freeze evaluation inputs without asserting execution or evidence status."""
    if type(model_id) is not str or _MODEL_ID.fullmatch(model_id) is None:
        raise ValueError(
            "model_id MUST be a valid identifier of at most 256 characters"
        )
    if type(region) is not str or region not in _REGIONS:
        raise ValueError("region MUST be us-east-1 or us-west-2")
    _validate_config(model_config)
    frozen_corpus = _copy_object(corpus)
    config = _copy_object(model_config)
    snapshot = catalog_snapshot()
    manifest: dict[str, object] = {
        "version": "evaluation-manifest-v1",
        "corpus_hash": _hash(frozen_corpus),
        "catalog": snapshot,
        "catalog_hash": _hash(snapshot),
        "catalog_version": snapshot["version"],
        "system_prompt_hash": _hash(chat_loop.SYSTEM_PROMPT),
        "baseline_system_prompt_hash": _hash(BASELINE_SYSTEM_PROMPT),
        "model_id": model_id,
        "region": region,
        "model_config": config,
        "model_config_hash": _hash(config),
        "conditions": ["tool_enabled", "no_tool", "deterministic"],
    }
    manifest["manifest_hash"] = _hash(manifest)
    return manifest
