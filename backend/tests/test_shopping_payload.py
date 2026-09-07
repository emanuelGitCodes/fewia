"""Tests for the Instacart development shopping-list payload."""

import copy
import hashlib
import json
from dataclasses import replace
from datetime import date

import pytest

from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import GroceryRequest
from app.services.grocery_planner import PlanEstimate, plan_groceries
from app.services.shopping_payload import (
    NoShoppingItems,
    build_shopping_payload,
    shopping_payload_hash,
)

BEAN_TACOS_2_QUANTITIES = {
    "black beans": 240,
    "corn tortillas": 4,
    "ground cumin": 2,
    "olive oil": 20,
    "onion": 60,
    "salsa": 80,
    "salt": 2,
}
BEAN_TACOS_2_ORDER = (
    "black beans",
    "ground cumin",
    "olive oil",
    "onion",
    "salsa",
    "salt",
    "corn tortillas",
)
SHARED_QUANTITIES = {
    "black beans": 120,
    "chicken breast": 100,
    "corn tortillas": 4,
    "ground cumin": 2,
    "olive oil": 20,
    "onion": 60,
    "salsa": 80,
    "salt": 2,
}
SHARED_ORDER = (
    "black beans",
    "chicken breast",
    "ground cumin",
    "olive oil",
    "onion",
    "salsa",
    "salt",
    "corn tortillas",
)
BEAN_PANTRY_IDS = [
    "black_beans",
    "cumin",
    "olive_oil",
    "onion",
    "salsa",
    "salt",
    "tortillas",
]
FORBIDDEN_TOKENS = (
    "available_cents",
    "bank",
    "budget",
    "catalog_version",
    "cost",
    "credential",
    "from_pantry",
    "health",
    "ingredient_id",
    "instruction",
    "notice",
    "owner",
    "packages",
    "price",
    "product_id",
    "secret",
    "token",
    "upc",
    "warning",
)
SECRET = "PAYLOAD_SECRET_MARKER"


def bean_plan(
    pantry: list[str] | None = None,
    *,
    servings: int = 2,
    available_cents: int = 10_000,
    extra_meals: list[dict[str, object]] | None = None,
) -> PlanEstimate:
    meals: list[dict[str, object]] = [{"recipe_id": "bean_tacos", "servings": servings}]
    if extra_meals is not None:
        meals.extend(extra_meals)
    values: dict[str, object] = {
        "meals": meals,
        "budget_period": date(2026, 9, 1),
    }
    if pantry is not None:
        values["pantry_ingredients"] = pantry
    return plan_groceries(
        GroceryRequest.model_validate(values),
        BudgetResult(available_cents, 0, False, ()),
    )


def line_quantities(payload: dict[str, object]) -> dict[str, int]:
    items = payload["line_items"]
    assert isinstance(items, list)
    quantities: dict[str, int] = {}
    for item in items:
        assert isinstance(item, dict)
        assert set(item) == {"name", "line_item_measurements"}
        name = item["name"]
        measurements = item["line_item_measurements"]
        assert isinstance(name, str)
        assert isinstance(measurements, list)
        assert len(measurements) == 1
        measurement = measurements[0]
        assert isinstance(measurement, dict)
        assert set(measurement) == {"quantity", "unit"}
        quantity = measurement["quantity"]
        assert type(quantity) is int
        quantities[name] = quantity
    return quantities


def line_names(payload: dict[str, object]) -> tuple[str, ...]:
    items = payload["line_items"]
    assert isinstance(items, list)
    names: list[str] = []
    for item in items:
        assert isinstance(item, dict)
        name = item["name"]
        assert isinstance(name, str)
        names.append(name)
    return tuple(names)


def assert_static(error: BaseException, message: str, *secrets: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    for secret in secrets:
        assert secret not in rendered


def replace_line(plan: PlanEstimate, index: int, **changes: object) -> PlanEstimate:
    lines = list(plan.lines)
    lines[index] = replace(lines[index], **changes)
    return replace(plan, lines=tuple(lines))


INVALID_PAYLOAD = "payload is not a prepared shopping payload"


def mutate_first_measurement(
    payload: dict[str, object], **changes: object
) -> dict[str, object]:
    mutated = copy.deepcopy(payload)
    items = mutated["line_items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    measurements = item["line_item_measurements"]
    assert isinstance(measurements, list)
    measurement = measurements[0]
    assert isinstance(measurement, dict)
    measurement.update(changes)
    return mutated


def test_bean_tacos_two_servings_has_seven_exact_rows_and_stable_hash() -> None:
    plan = bean_plan()
    payload = build_shopping_payload(plan)
    assert list(payload) == ["title", "link_type", "expires_in", "line_items"]
    assert payload["title"] == "FEWIA grocery plan"
    assert payload["link_type"] == "shopping_list"
    assert payload["expires_in"] == 7
    assert line_names(payload) == BEAN_TACOS_2_ORDER
    assert line_quantities(payload) == BEAN_TACOS_2_QUANTITIES
    items = payload["line_items"]
    assert isinstance(items, list)
    units: dict[str, object] = {}
    for item in items:
        assert isinstance(item, dict)
        name = item["name"]
        measurements = item["line_item_measurements"]
        assert isinstance(name, str)
        assert isinstance(measurements, list)
        measurement = measurements[0]
        assert isinstance(measurement, dict)
        units[name] = measurement["unit"]
    assert units["corn tortillas"] == "each"
    assert units["black beans"] == "g"
    first = shopping_payload_hash(payload)
    second = shopping_payload_hash(build_shopping_payload(bean_plan()))
    assert first == second
    assert len(first) == 64


def test_shared_ingredients_are_aggregated() -> None:
    plan = bean_plan(
        servings=1,
        extra_meals=[{"recipe_id": "chicken_tacos", "servings": 1}],
    )
    payload = build_shopping_payload(plan)
    assert line_quantities(payload) == SHARED_QUANTITIES
    assert line_names(payload) == SHARED_ORDER


def test_pantry_oil_removes_only_oil() -> None:
    payload = build_shopping_payload(bean_plan(pantry=["olive_oil"]))
    quantities = line_quantities(payload)
    assert "olive oil" not in quantities
    expected = dict(BEAN_TACOS_2_QUANTITIES)
    del expected["olive oil"]
    assert quantities == expected
    assert len(quantities) == 6


def test_all_pantry_raises_without_external_action() -> None:
    plan = bean_plan(pantry=BEAN_PANTRY_IDS)
    with pytest.raises(NoShoppingItems) as raised:
        build_shopping_payload(plan)
    assert isinstance(raised.value, ValueError)
    assert_static(raised.value, "shopping list has no items")


def test_incomplete_and_rejected_plans_are_refused() -> None:
    incomplete = replace(bean_plan(), accepted=False, total_cents=None)
    with pytest.raises(ValueError) as incomplete_error:
        build_shopping_payload(incomplete)
    assert_static(incomplete_error.value, "plan MUST be accepted")
    rejected = bean_plan(available_cents=0)
    assert rejected.accepted is False
    with pytest.raises(ValueError) as rejected_error:
        build_shopping_payload(rejected)
    assert_static(rejected_error.value, "plan MUST be accepted")


@pytest.mark.parametrize("total", [None, -1, True, 1.5, "1703"])
def test_forged_or_nonexact_totals_are_refused(total: object) -> None:
    plan = replace(bean_plan(), total_cents=total)  # type: ignore[arg-type]
    with pytest.raises(ValueError) as raised:
        build_shopping_payload(plan)
    assert_static(raised.value, "plan total is invalid")


def test_inconsistent_total_is_refused() -> None:
    plan = bean_plan()
    forged = replace(plan, total_cents=plan.total_cents + 1)  # type: ignore[operator]
    with pytest.raises(ValueError) as raised:
        build_shopping_payload(forged)
    assert_static(raised.value, "plan total does not match line costs")


def test_not_a_plan_estimate_is_refused() -> None:
    with pytest.raises(TypeError) as raised:
        build_shopping_payload("not-a-plan")  # type: ignore[arg-type]
    assert_static(raised.value, "plan MUST be a PlanEstimate")


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": 0},
        {"packages": 0},
        {"packages": True},
        {"cost_cents": -1},
        {"cost_cents": None},
        {"from_pantry": 1},
    ],
)
def test_malformed_purchase_line_fields_are_refused(changes: dict[str, object]) -> None:
    plan = replace_line(bean_plan(), 0, **changes)
    with pytest.raises(ValueError) as raised:
        build_shopping_payload(plan)
    assert_static(raised.value, "shopping line is invalid")


def test_pantry_lines_must_have_zero_packages_and_cost() -> None:
    plan = bean_plan(pantry=["olive_oil"])
    oil_index = next(
        index
        for index, line in enumerate(plan.lines)
        if line.ingredient_id == "olive_oil"
    )
    with pytest.raises(ValueError) as packages_error:
        build_shopping_payload(replace_line(plan, oil_index, packages=1))
    assert_static(packages_error.value, "shopping line is invalid")
    with pytest.raises(ValueError) as cost_error:
        build_shopping_payload(replace_line(plan, oil_index, cost_cents=5))
    assert_static(cost_error.value, "shopping line is invalid")


def test_unknown_and_duplicate_ingredient_ids_are_refused() -> None:
    unknown = replace_line(bean_plan(), 0, ingredient_id="not_in_catalog")
    with pytest.raises(ValueError) as unknown_error:
        build_shopping_payload(unknown)
    assert_static(unknown_error.value, "ingredient id is unknown")
    plan = bean_plan()
    duplicate = replace(plan, lines=plan.lines + (plan.lines[0],))
    with pytest.raises(ValueError) as duplicate_error:
        build_shopping_payload(duplicate)
    assert_static(duplicate_error.value, "ingredient id is duplicated")


def test_name_and_unit_must_match_catalog() -> None:
    with pytest.raises(ValueError) as name_error:
        build_shopping_payload(replace_line(bean_plan(), 0, name="forged name"))
    assert_static(
        name_error.value, "ingredient name or unit does not match the catalog"
    )
    with pytest.raises(ValueError) as unit_error:
        build_shopping_payload(replace_line(bean_plan(), 0, unit="oz"))
    assert_static(
        unit_error.value, "ingredient name or unit does not match the catalog"
    )


def test_payload_omits_budget_cost_and_raw_metadata() -> None:
    payload = build_shopping_payload(bean_plan())
    serialized = json.dumps(payload)
    lowered = serialized.lower()
    for token in FORBIDDEN_TOKENS:
        assert token not in lowered
    items = payload["line_items"]
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, dict)
        assert "quantity" not in item
        assert "unit" not in item


def test_altered_quantities_change_hash_and_input_is_not_mutated() -> None:
    payload = build_shopping_payload(bean_plan())
    snapshot = copy.deepcopy(payload)
    digest = shopping_payload_hash(payload)
    assert payload == snapshot
    items = payload["line_items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    measurements = first["line_item_measurements"]
    assert isinstance(measurements, list)
    measurement = measurements[0]
    assert isinstance(measurement, dict)
    quantity = measurement["quantity"]
    assert type(quantity) is int
    measurement["quantity"] = quantity + 1
    assert shopping_payload_hash(payload) != digest
    assert shopping_payload_hash(snapshot) == digest


def test_hash_matches_canonical_sorted_compact_ascii_sha256() -> None:
    payload = build_shopping_payload(bean_plan())
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert encoded.encode("ascii")
    expected = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    assert shopping_payload_hash(payload) == expected


def test_reversed_plan_lines_keep_sorted_id_order() -> None:
    plan = bean_plan()
    reversed_plan = replace(plan, lines=tuple(reversed(plan.lines)))
    assert build_shopping_payload(reversed_plan) == build_shopping_payload(plan)


def test_hash_rejects_invalid_objects_without_echoing_payload() -> None:
    with pytest.raises(TypeError) as type_error:
        shopping_payload_hash(["not-an-object"])  # type: ignore[arg-type]
    assert_static(type_error.value, "payload MUST be a JSON object")
    poisoned: dict[str, object] = {"title": SECRET, "link_type": "shopping_list"}
    with pytest.raises(ValueError) as value_error:
        shopping_payload_hash(poisoned)
    assert_static(
        value_error.value,
        "payload is not a prepared shopping payload",
        SECRET,
    )
    nan_payload = build_shopping_payload(bean_plan())
    nan_payload["expires_in"] = float("nan")
    with pytest.raises(ValueError) as nan_error:
        shopping_payload_hash(nan_payload)
    assert_static(nan_error.value, "payload is not a prepared shopping payload")


def test_valid_builder_payload_hash_and_quantities_are_unchanged() -> None:
    payload = build_shopping_payload(bean_plan())
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert payload["expires_in"] == 7
    assert type(payload["expires_in"]) is int
    assert line_quantities(payload) == BEAN_TACOS_2_QUANTITIES
    assert line_names(payload) == BEAN_TACOS_2_ORDER
    assert (
        shopping_payload_hash(payload)
        == hashlib.sha256(encoded.encode("ascii")).hexdigest()
    )


def test_hash_rejects_float_expiry_and_keeps_integer_seven_hash() -> None:
    payload = build_shopping_payload(bean_plan())
    digest = shopping_payload_hash(payload)
    mutated = copy.deepcopy(payload)
    mutated["expires_in"] = 7.0
    with pytest.raises(ValueError) as raised:
        shopping_payload_hash(mutated)
    assert_static(raised.value, INVALID_PAYLOAD)
    assert payload["expires_in"] == 7
    assert shopping_payload_hash(payload) == digest
    assert line_quantities(payload) == BEAN_TACOS_2_QUANTITIES


def test_hash_rejects_dict_unit_with_static_value_error() -> None:
    payload = mutate_first_measurement(
        build_shopping_payload(bean_plan()), unit={"unit": "g"}
    )
    with pytest.raises(ValueError) as raised:
        shopping_payload_hash(payload)
    assert_static(raised.value, INVALID_PAYLOAD)


def test_hash_rejects_cycles_and_depth_with_static_value_error() -> None:
    cyclic = copy.deepcopy(build_shopping_payload(bean_plan()))
    items = cyclic["line_items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    measurements = item["line_item_measurements"]
    assert isinstance(measurements, list)
    measurement = measurements[0]
    assert isinstance(measurement, dict)
    measurement["unit"] = cyclic
    with pytest.raises(ValueError) as cyclic_error:
        shopping_payload_hash(cyclic)
    assert_static(cyclic_error.value, INVALID_PAYLOAD)
    deep: object = "leaf"
    for _ in range(2000):
        deep = [deep]
    nested = copy.deepcopy(build_shopping_payload(bean_plan()))
    nested["title"] = deep
    with pytest.raises(ValueError) as depth_error:
        shopping_payload_hash(nested)
    assert_static(depth_error.value, INVALID_PAYLOAD)


def test_hash_rejects_unknown_duplicate_and_oversized_names() -> None:
    unknown = copy.deepcopy(build_shopping_payload(bean_plan()))
    items = unknown["line_items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    first["name"] = "not a catalog ingredient"
    with pytest.raises(ValueError) as unknown_error:
        shopping_payload_hash(unknown)
    assert_static(unknown_error.value, INVALID_PAYLOAD)
    duplicate = copy.deepcopy(build_shopping_payload(bean_plan()))
    dup_items = duplicate["line_items"]
    assert isinstance(dup_items, list)
    duplicate["line_items"] = [dup_items[0], copy.deepcopy(dup_items[0])]
    with pytest.raises(ValueError) as duplicate_error:
        shopping_payload_hash(duplicate)
    assert_static(duplicate_error.value, INVALID_PAYLOAD)
    oversized = copy.deepcopy(build_shopping_payload(bean_plan()))
    source_items = oversized["line_items"]
    assert isinstance(source_items, list)
    row = copy.deepcopy(source_items[0])
    oversized["line_items"] = [copy.deepcopy(row) for _ in range(len(INGREDIENTS) + 1)]
    with pytest.raises(ValueError) as oversized_error:
        shopping_payload_hash(oversized)
    assert_static(oversized_error.value, INVALID_PAYLOAD)


def test_hash_requires_catalog_unit_for_item_name() -> None:
    payload = mutate_first_measurement(build_shopping_payload(bean_plan()), unit="each")
    items = payload["line_items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    assert item["name"] == "black beans"
    with pytest.raises(ValueError) as raised:
        shopping_payload_hash(payload)
    assert_static(raised.value, INVALID_PAYLOAD)


@pytest.mark.parametrize("quantity", [True, 1.0, 0, -1])
def test_hash_requires_positive_exact_integer_quantity(quantity: object) -> None:
    payload = mutate_first_measurement(
        build_shopping_payload(bean_plan()), quantity=quantity
    )
    with pytest.raises(ValueError) as raised:
        shopping_payload_hash(payload)
    assert_static(raised.value, INVALID_PAYLOAD)
