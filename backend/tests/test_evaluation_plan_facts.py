from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_plan_facts import plan_integrity


def _object(result: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], result[key])


def _lines(result: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _object(result, "plan")["lines"])


def _line(result: dict[str, object], ingredient_id: str) -> dict[str, object]:
    return next(
        line for line in _lines(result) if line["ingredient_id"] == ingredient_id
    )


@pytest.fixture
def observed() -> dict[str, object]:
    records = (
        ("chicken_breast", "chicken breast", "g", 200, 799),
        ("cumin", "ground cumin", "g", 1, 199),
        ("garlic", "garlic", "g", 5, 89),
        ("mixed_vegetables", "mixed vegetables", "g", 80, 199),
        ("olive_oil", "olive oil", "g", 20, 599),
        ("onion", "onion", "g", 60, 129),
        ("rice", "white rice", "g", 75, 199),
        ("salsa", "salsa", "g", 40, 249),
        ("salt", "salt", "g", 2, 99),
        ("tortillas", "corn tortillas", "each", 2, 299),
    )
    return {
        "request": {
            "meals": [
                {"recipe_id": "chicken_tacos", "servings": 1},
                {"recipe_id": "chicken_and_rice_bowls", "servings": 1},
            ],
            "budget_period": "2026-09-01",
            "plan_cap_cents": None,
            "pantry_ingredients": [],
            "ingredient_exclusions": [],
            "diet": "omnivore",
        },
        "plan": {
            "lines": [
                {
                    "ingredient_id": item,
                    "name": name,
                    "unit": unit,
                    "quantity": quantity,
                    "packages": 1,
                    "cost_cents": cost,
                    "from_pantry": False,
                }
                for item, name, unit, quantity, cost in records
            ],
            "total_cents": 2860,
            "accepted": True,
            "catalog_version": "sample-prices-v2",
            "notice": SAMPLE_ESTIMATE_NOTICE,
        },
        "budget": {"available_cents": 10000, "pending_cents": 400, "stale": False},
    }


def test_shared_chicken_rounds_after_aggregation(observed: dict[str, object]) -> None:
    assert all(plan_integrity(observed).values())
    _line(observed, "chicken_breast").update(packages=2, cost_cents=1598)
    _object(observed, "plan")["total_cents"] = 3659
    checks = plan_integrity(observed)
    assert checks["quantities"]
    assert not checks["package_rounding"]
    assert not checks["sample_costs"]
    assert not checks["total_cents"]


def test_pantry_keeps_consumed_quantity(observed: dict[str, object]) -> None:
    _object(observed, "request")["pantry_ingredients"] = ["chicken_breast"]
    chicken = _line(observed, "chicken_breast")
    chicken.update(packages=0, cost_cents=0, from_pantry=True)
    _object(observed, "plan")["total_cents"] = 2061
    assert all(plan_integrity(observed).values())
    chicken["quantity"] = 199
    assert not plan_integrity(observed)["quantities"]


@pytest.mark.parametrize(
    ("available", "cap", "accepted", "valid"),
    [
        (2860, None, True, True),
        (2859, None, True, False),
        (2859, None, False, True),
        (10000, 2860, True, True),
        (10000, 2859, True, False),
        (10000, 2859, False, True),
        (10000, None, False, False),
    ],
)
def test_acceptance_matches_budget_and_cap(
    observed: dict[str, object],
    available: int,
    cap: int | None,
    accepted: bool,
    valid: bool,
) -> None:
    _object(observed, "request")["plan_cap_cents"] = cap
    _object(observed, "budget")["available_cents"] = available
    _object(observed, "plan")["accepted"] = accepted
    checks = plan_integrity(observed)
    assert checks["acceptance"] is valid
    if cap is not None and accepted and cap < 2860:
        assert not checks["budget_cap"]


@pytest.mark.parametrize("mode", ["drop", "duplicate", "unknown", "extra"])
def test_exact_ingredient_coverage(observed: dict[str, object], mode: str) -> None:
    lines = _lines(observed)
    if mode == "drop":
        lines.pop(0)
    elif mode == "duplicate":
        lines.append(dict(lines[0]))
    elif mode == "unknown":
        lines[0]["ingredient_id"] = "unknown_ingredient"
    else:
        lines.append(
            {
                "ingredient_id": "eggs",
                "name": "eggs",
                "unit": "each",
                "quantity": 1,
                "packages": 1,
                "cost_cents": 349,
                "from_pantry": False,
            }
        )
    checks = plan_integrity(observed)
    assert not checks["ingredient_coverage"]
    assert not checks["total_cents"]
    assert not all(checks.values())


def test_wrong_servings_quantities(observed: dict[str, object]) -> None:
    meals = cast(list[dict[str, object]], _object(observed, "request")["meals"])
    meals[0]["servings"] = 2
    assert not plan_integrity(observed)["quantities"]


@pytest.mark.parametrize("diet", ["vegetarian", "vegan"])
def test_chicken_conflicts_with_diet(observed: dict[str, object], diet: str) -> None:
    _object(observed, "request")["diet"] = diet
    assert not plan_integrity(observed)["diet"]


def test_excluded_pantry_ingredient_still_conflicts(
    observed: dict[str, object],
) -> None:
    _object(observed, "request").update(
        pantry_ingredients=["chicken_breast"], ingredient_exclusions=["chicken_breast"]
    )
    _line(observed, "chicken_breast").update(packages=0, cost_cents=0, from_pantry=True)
    _object(observed, "plan")["total_cents"] = 2061
    assert not plan_integrity(observed)["exclusions"]
    _lines(observed).pop(0)
    checks = plan_integrity(observed)
    assert not checks["exclusions"]
    assert not checks["ingredient_coverage"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("name", "retailer chicken"), ("unit", "each"), ("from_pantry", True)],
)
def test_line_metadata_matches_catalog_and_request(
    observed: dict[str, object], field: str, value: object
) -> None:
    _line(observed, "chicken_breast")[field] = value
    assert not plan_integrity(observed)["quantities"]


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("plan", "total_cents", True),
        ("plan", "total_cents", "2860"),
        ("plan", "total_cents", 2860.0),
        ("plan", "total_cents", -1),
        ("plan", "accepted", 1),
        ("plan", "lines", None),
        ("plan", "catalog_version", 2),
        ("plan", "notice", None),
        ("budget", "available_cents", False),
        ("budget", "available_cents", "10000"),
        ("budget", "available_cents", -1),
        ("budget", "pending_cents", True),
        ("budget", "pending_cents", "400"),
        ("budget", "stale", 0),
        ("request", "budget_period", "2026-09-02"),
        ("request", "plan_cap_cents", True),
        ("request", "meals", []),
        ("request", "pantry_ingredients", [1]),
        ("request", "pantry_ingredients", ["unknown_ingredient"]),
        ("request", "ingredient_exclusions", ["unknown_ingredient"]),
    ],
)
def test_malformed_envelope_fields_fail_schema(
    observed: dict[str, object], section: str, field: str, value: object
) -> None:
    _object(observed, section)[field] = value
    checks = plan_integrity(observed)
    assert not checks["schema"]
    assert not all(checks.values())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ingredient_id", 1),
        ("name", None),
        ("unit", 1),
        ("quantity", True),
        ("quantity", "200"),
        ("quantity", 200.0),
        ("quantity", 0),
        ("packages", False),
        ("packages", -1),
        ("cost_cents", True),
        ("cost_cents", "799"),
        ("cost_cents", -1),
        ("from_pantry", "false"),
    ],
)
def test_malformed_line_fields_fail_schema(
    observed: dict[str, object], field: str, value: object
) -> None:
    _line(observed, "chicken_breast")[field] = value
    assert not plan_integrity(observed)["schema"]


@pytest.mark.parametrize("servings", [True, "1", 1.0, 0, 9])
def test_request_servings_use_strict_integers(
    observed: dict[str, object], servings: object
) -> None:
    meals = cast(list[dict[str, object]], _object(observed, "request")["meals"])
    meals[0]["servings"] = servings
    assert not plan_integrity(observed)["schema"]


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("plan", "total_cents"),
        ("plan", "accepted"),
        ("plan", "lines"),
        ("plan", "catalog_version"),
        ("plan", "notice"),
        ("budget", "available_cents"),
        ("budget", "pending_cents"),
        ("budget", "stale"),
        ("request", "budget_period"),
        ("request", "meals"),
    ],
)
def test_missing_required_fields_fail_schema(
    observed: dict[str, object], section: str, field: str
) -> None:
    _object(observed, section).pop(field)
    assert not plan_integrity(observed)["schema"]


@pytest.mark.parametrize("section", ["request", "plan", "budget"])
def test_missing_envelope_sections_fail_schema(
    observed: dict[str, object], section: str
) -> None:
    observed.pop(section)
    assert not plan_integrity(observed)["schema"]
    assert not plan_integrity({})["schema"]


@pytest.mark.parametrize(
    ("accepted", "total", "valid"),
    [
        (False, None, True),
        (True, None, False),
        (False, 2061, False),
        (True, 2061, False),
    ],
)
def test_missing_price_cannot_certify_complete_total(
    observed: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    accepted: bool,
    total: int | None,
    valid: bool,
) -> None:
    monkeypatch.setitem(
        INGREDIENTS,
        "chicken_breast",
        replace(INGREDIENTS["chicken_breast"], price_cents=None),
    )
    _line(observed, "chicken_breast")["cost_cents"] = None
    _object(observed, "plan").update(accepted=accepted, total_cents=total)
    checks = plan_integrity(observed)
    assert checks["sample_costs"] is valid
    assert checks["total_cents"] is valid
    assert checks["acceptance"] is (not accepted)
    assert all(checks.values()) is valid


def test_known_catalog_price_rejects_omitted_cost(
    observed: dict[str, object],
) -> None:
    assert INGREDIENTS["chicken_breast"].price_cents is not None
    _line(observed, "chicken_breast")["cost_cents"] = None
    _object(observed, "plan").update(accepted=False, total_cents=None)
    checks = plan_integrity(observed)
    assert not checks["sample_costs"]
    assert not checks["total_cents"]
    assert not all(checks.values())


def test_missing_pantry_cost_is_invalid(observed: dict[str, object]) -> None:
    _object(observed, "request")["pantry_ingredients"] = ["chicken_breast"]
    _line(observed, "chicken_breast").update(
        from_pantry=True, packages=0, cost_cents=None
    )
    _object(observed, "plan").update(accepted=False, total_cents=None)
    assert not plan_integrity(observed)["sample_costs"]


def test_acceptance_requires_a_complete_total(observed: dict[str, object]) -> None:
    _object(observed, "plan")["total_cents"] = None
    checks = plan_integrity(observed)
    assert not checks["total_cents"]
    assert not checks["acceptance"]


def test_catalog_missing_price_rejects_invented_cost(
    observed: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        INGREDIENTS,
        "chicken_breast",
        replace(INGREDIENTS["chicken_breast"], price_cents=None),
    )
    assert not plan_integrity(observed)["sample_costs"]
    _line(observed, "chicken_breast")["cost_cents"] = None
    _object(observed, "plan").update(accepted=False, total_cents=None)
    assert all(plan_integrity(observed).values())


@pytest.mark.parametrize("mode", ["cost", "total", "both", "null_total"])
def test_sample_cost_and_total_mutations_fail(
    observed: dict[str, object], mode: str
) -> None:
    if mode in {"cost", "both"}:
        _line(observed, "chicken_breast")["cost_cents"] = 800
    if mode in {"total", "both"}:
        _object(observed, "plan")["total_cents"] = 2861
    if mode == "null_total":
        _object(observed, "plan").update(total_cents=None, accepted=False)
    checks = plan_integrity(observed)
    assert not checks["total_cents"]
    assert not all(checks.values())


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        ("notice", "Verified retailer quote", "notice"),
        ("catalog_version", "sample-prices-v1", "catalog_version"),
    ],
)
def test_notice_and_version_match_catalog(
    observed: dict[str, object], field: str, value: str, check: str
) -> None:
    _object(observed, "plan")[field] = value
    assert not plan_integrity(observed)[check]


def test_input_is_unchanged(observed: dict[str, object]) -> None:
    before = deepcopy(observed)
    assert all(plan_integrity(observed).values())
    assert observed == before
    _line(observed, "chicken_breast")["cost_cents"] = None
    before = deepcopy(observed)
    assert not all(plan_integrity(observed).values())
    assert observed == before
