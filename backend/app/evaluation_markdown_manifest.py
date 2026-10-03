from typing import cast

from app.evaluation_manifest import _MODEL_ID, _REGIONS, _hash, _validate_config
from app.evaluation_markdown_values import as_map, pick, require, text

_ERROR = "Invalid evaluation report input"
_HASHES = (
    "manifest_hash corpus_hash catalog_hash system_prompt_hash "
    "baseline_system_prompt_hash model_config_hash"
).split()
_FIELDS = (
    "version catalog_version model_id region model_config conditions catalog "
    + " ".join(_HASHES)
)
_CONDITIONS = ["tool_enabled", "no_tool", "deterministic"]


def prepare_manifest(value: object) -> dict[str, object]:
    """Check metadata integrity while preserving declared corpus and prompt hashes."""
    try:
        source = pick(as_map(value), _FIELDS)
        require(set(source) == set(_FIELDS.split()))
        text(source["version"], "evaluation-manifest-v1")
        text(source["catalog_version"], r"[A-Za-z0-9._-]{1,128}")
        text(source["model_id"], _MODEL_ID.pattern)
        require(type(source["region"]) is str and source["region"] in _REGIONS)
        config = as_map(source["model_config"])
        if "max_tokens" in config:
            require(type(config["max_tokens"]) is int)
        _validate_config(config)
        conditions = source["conditions"]
        require(type(conditions) is list)
        require(all(type(item) is str for item in cast(list[object], conditions)))
        require(conditions == _CONDITIONS)
        for name in _HASHES:
            text(source[name], r"[0-9a-f]{64}")
        catalog = as_map(source["catalog"])
        require(type(catalog.get("version")) is str)
        require(catalog.get("version") == source["catalog_version"])
        require(source["catalog_hash"] == _hash(catalog))
        require(source["model_config_hash"] == _hash(config))
        identity = {key: item for key, item in source.items() if key != "manifest_hash"}
        require(source["manifest_hash"] == _hash(identity))
        result = {key: item for key, item in source.items() if key != "catalog"}
        result["model_config"] = dict(config)
        result["conditions"] = list(_CONDITIONS)
        return result
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError(_ERROR) from None
