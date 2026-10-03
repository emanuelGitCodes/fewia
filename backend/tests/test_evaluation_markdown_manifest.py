import hashlib
import json
from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_manifest import build_manifest
from app.evaluation_markdown_manifest import prepare_manifest

_FIELDS = (
    "version catalog_version model_id region model_config conditions catalog "
    "corpus_hash catalog_hash system_prompt_hash baseline_system_prompt_hash "
    "model_config_hash manifest_hash"
).split()
_HASHES = [name for name in _FIELDS if name.endswith("_hash")]


@pytest.fixture
def manifest() -> dict[str, object]:
    return build_manifest(
        {"scenarios": [{"id": "meal", "prompt": "Plan a meal."}]},
        model_id="us.openai.gpt-6-luna",
        region="us-east-1",
        model_config={"max_tokens": 1024, "temperature": 0, "reasoning_effort": "low"},
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resign(manifest: dict[str, object]) -> None:
    manifest["manifest_hash"] = _digest(
        {name: manifest[name] for name in _FIELDS if name != "manifest_hash"}
    )


def _assert_invalid(value: object) -> None:
    with pytest.raises(ValueError) as caught:
        prepare_manifest(value)
    assert str(caught.value) == "Invalid evaluation report input"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_actual_manifest_returns_only_metadata(manifest: dict[str, object]) -> None:
    original = deepcopy(manifest)
    result = prepare_manifest(manifest)
    assert result == {key: value for key, value in original.items() if key != "catalog"}
    assert set(result) == set(_FIELDS) - {"catalog"}
    assert all(result[name] == original[name] for name in _HASHES)
    assert manifest == original
    cast(dict[str, object], result["model_config"])["max_tokens"] = 1
    cast(list[str], result["conditions"]).clear()
    assert manifest == original


@pytest.mark.parametrize("field", _FIELDS)
def test_each_field_is_required(manifest: dict[str, object], field: str) -> None:
    del manifest[field]
    _assert_invalid(manifest)


@pytest.mark.parametrize("value", [None, [], "manifest", True, 1])
def test_manifest_requires_an_exact_map(value: object) -> None:
    _assert_invalid(value)


@pytest.mark.parametrize("field", _HASHES)
@pytest.mark.parametrize("value", [None, True, 1, "A" * 64, "g" * 64, "a" * 63])
def test_hashes_require_lowercase_hex(
    manifest: dict[str, object], field: str, value: object
) -> None:
    manifest[field] = value
    _assert_invalid(manifest)


@pytest.mark.parametrize("field", _HASHES)
def test_stale_hashes_fail(manifest: dict[str, object], field: str) -> None:
    manifest[field] = "0" * 64
    _assert_invalid(manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "evaluation-manifest-v2"),
        ("version", True),
        ("catalog_version", ""),
        ("catalog_version", "v" * 129),
        ("catalog_version", 1),
        ("model_id", "bad id"),
        ("model_id", "m" * 257),
        ("model_id", None),
        ("region", "eu-west-1"),
        ("region", True),
        ("model_config", []),
        ("catalog", []),
        ("conditions", ("tool_enabled", "no_tool", "deterministic")),
        ("conditions", ["tool_enabled", "no_tool"]),
        ("conditions", ["no_tool", "tool_enabled", "deterministic"]),
        ("conditions", ["tool_enabled", "no_tool", "controlled_fixture"]),
        ("conditions", ["tool_enabled", "no_tool", True]),
        ("conditions", ["tool_enabled", "no_tool", "deterministic", "no_tool"]),
    ],
)
def test_invalid_metadata_fails_with_valid_manifest_hash(
    manifest: dict[str, object], field: str, value: object
) -> None:
    manifest[field] = value
    _resign(manifest)
    _assert_invalid(manifest)


@pytest.mark.parametrize("field", ["model_id", "region", "conditions"])
def test_metadata_changes_require_new_manifest_hash(
    manifest: dict[str, object], field: str
) -> None:
    manifest[field] = {
        "model_id": "another.model",
        "region": "us-west-2",
        "conditions": ["no_tool", "tool_enabled", "deterministic"],
    }[field]
    _assert_invalid(manifest)


def test_stale_config_hash_fails(manifest: dict[str, object]) -> None:
    cast(dict[str, object], manifest["model_config"])["max_tokens"] = 2048
    _resign(manifest)
    _assert_invalid(manifest)


def test_stale_catalog_hash_fails(manifest: dict[str, object]) -> None:
    cast(dict[str, object], manifest["catalog"])["estimate_notice"] = "Changed."
    _resign(manifest)
    _assert_invalid(manifest)


@pytest.mark.parametrize("value", [None, 1, "different-version"])
def test_catalog_version_agrees_with_metadata(
    manifest: dict[str, object], value: object
) -> None:
    cast(dict[str, object], manifest["catalog"])["version"] = value
    manifest["catalog_hash"] = _digest(manifest["catalog"])
    _resign(manifest)
    _assert_invalid(manifest)


@pytest.mark.parametrize(
    "config",
    [
        {"unsupported_setting": "TEST_ONLY_MARKER"},
        {"max_tokens": True},
        {"max_tokens": 1.0},
        {"max_tokens": 0},
        {"max_tokens": 4097},
        {"temperature": True},
        {"temperature": -0.1},
        {"temperature": 1.1},
        {"reasoning_effort": True},
        {"reasoning_effort": "max"},
    ],
)
def test_invalid_config_is_denied_even_when_hashes_match(
    manifest: dict[str, object], config: dict[str, object]
) -> None:
    manifest["model_config"] = config
    manifest["model_config_hash"] = _digest(config)
    _resign(manifest)
    _assert_invalid(manifest)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_config_fails(manifest: dict[str, object], value: float) -> None:
    manifest["model_config"] = {"temperature": value}
    _assert_invalid(manifest)


@pytest.mark.parametrize(
    "config",
    [{}, {"max_tokens": 1}, {"temperature": 1.0}, {"reasoning_effort": "high"}],
)
def test_all_valid_config_shapes_are_accepted(config: dict[str, object]) -> None:
    value = build_manifest(
        {}, model_id="model", region="us-west-2", model_config=config
    )
    assert prepare_manifest(value)["model_config"] == config


def test_unknown_manifest_fields_are_not_hashed_or_returned(
    manifest: dict[str, object],
) -> None:
    expected = prepare_manifest(manifest)
    manifest["private_notes"] = {"marker": object()}
    manifest["extra_context"] = manifest
    assert prepare_manifest(manifest) == expected
    assert manifest["extra_context"] is manifest


def test_declared_corpus_and_prompt_identities_are_preserved(
    manifest: dict[str, object],
) -> None:
    names = ["corpus_hash", "system_prompt_hash", "baseline_system_prompt_hash"]
    for index, name in enumerate(names):
        manifest[name] = str(index) * 64
    _resign(manifest)
    result = prepare_manifest(manifest)
    assert all(result[name] == manifest[name] for name in names)


@pytest.mark.parametrize("value", [object(), float("nan"), {1: "value"}])
def test_invalid_catalog_json_has_static_error(
    manifest: dict[str, object], value: object
) -> None:
    cast(dict[str, object], manifest["catalog"])["invalid"] = value
    _assert_invalid(manifest)


def test_cyclic_catalog_has_static_error(manifest: dict[str, object]) -> None:
    catalog = cast(dict[str, object], manifest["catalog"])
    catalog["cycle"] = catalog
    _assert_invalid(manifest)


class _IntSubclass(int):
    pass


class _StrSubclass(str):
    pass


class _DictSubclass(dict[str, object]):
    pass


class _ListSubclass(list[str]):
    pass


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", _StrSubclass("model")),
        ("catalog_version", _StrSubclass("version")),
        ("region", _StrSubclass("us-east-1")),
        ("version", _StrSubclass("evaluation-manifest-v1")),
        ("corpus_hash", _StrSubclass("0" * 64)),
        ("model_config", {"max_tokens": _IntSubclass(1024)}),
        ("model_config", _DictSubclass()),
        ("catalog", _DictSubclass()),
        ("conditions", _ListSubclass(["tool_enabled", "no_tool", "deterministic"])),
        ("conditions", ["tool_enabled", "no_tool", _StrSubclass("deterministic")]),
    ],
)
def test_types_are_exact(
    manifest: dict[str, object], field: str, value: object
) -> None:
    manifest[field] = value
    _resign(manifest)
    _assert_invalid(manifest)


def test_manifest_subclass_is_denied(manifest: dict[str, object]) -> None:
    _assert_invalid(_DictSubclass(manifest))
