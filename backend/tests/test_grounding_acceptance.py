from time import perf_counter

import pytest

from app.agent.grounding import FactSet, facts_from_payloads, validate

_SERVINGS = 4
_BEFORE = {
    "energy_kcal": 500,
    "protein_mg": 20000,
    "carbohydrate_mg": 40000,
    "fat_mg": 11000,
}
_AFTER = {
    "energy_kcal": 480,
    "protein_mg": 25000,
    "carbohydrate_mg": 40000,
    "fat_mg": 8000,
}


def _times(values: dict[str, int]) -> dict[str, int]:
    return {key: value * _SERVINGS for key, value in values.items()}


def _diff(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


_PAYLOAD = {
    "status": "swapped",
    "servings": _SERVINGS,
    "before": {"per_serving": _BEFORE, "total": _times(_BEFORE)},
    "after": {"per_serving": _AFTER, "total": _times(_AFTER)},
    "delta": {
        "per_serving": _diff(_AFTER, _BEFORE),
        "total": _diff(_times(_AFTER), _times(_BEFORE)),
    },
    "delta_percent": {"protein_mg": 25, "fat_mg": -27},
}

_FACTS = facts_from_payloads([("what_if_substitute", _PAYLOAD)])

_INGREDIENT = {
    "ingredient_id": "tofu",
    "name": "Tofu",
    "quantity": 2,
    "unit": "block",
}
_QUANTITY_PAYLOAD = {
    **_PAYLOAD,
    "servings": _SERVINGS,
    "before": {**_PAYLOAD["before"], "ingredients": [_INGREDIENT]},
}


@pytest.fixture
def quantity_facts() -> FactSet:
    return facts_from_payloads([("what_if_substitute", _QUANTITY_PAYLOAD)])


ACCEPTANCE = [
    ("Fat drops by 3 g per serving, protein by 25 g.", False),
    ("Fat drops by 3 g per serving, and protein by 25 g.", False),
    ("Protein changes by 20 g.", False),
    ("Protein changes by 25 g.", False),
    ("Animal protein: 25 g.", False),
    ("Plant protein: 25 g.", False),
    ("Protein decreased from 25 g to 20 g per serving.", False),
    ("Protein decreased from 20 g to 25 g per serving.", False),
    ("Protein fell sharply from 25 g to 20 g.", False),
    ("Calories rose sharply from 500 kcal to 480 kcal.", False),
    ("Calories rose, from 500 kcal to 480 kcal.", False),
    ("Calories are up from 500 kcal to 480 kcal.", False),
    ("Calories rose sharply from 480 kcal to 500 kcal.", False),
    ("Calories are down from 500 kcal to 480 kcal.", True),
    ("Plant\nprotein: 25 g", False),
    ("Fat rose from 8 g to 11 g.", False),
    ("Calories rose from 480 kcal to 500 kcal.", False),
    ("Protein rose from 20 g to 25 g per serving.", True),
    ("Fat dropped from 11 g to 8 g.", True),
    ("Calories fell from 500 kcal to 480 kcal.", True),
    ("Protein: 25 g\nFat: 8 g", True),
    ("Protein 25 g\nCarbs 40 g\nFat 8 g", True),
    ("Protein 25 g per serving\nFat 8 g per serving", True),
    ("- Protein: 25 g\n- Fat: 8 g", True),
    ("Calories rose " + "and so on " * 25 + "from 500 kcal to 480 kcal.", False),
    ("Calories went up:\n- from 500 kcal to 480 kcal", False),
    ("Calories went down:\n- from 500 kcal to 480 kcal", True),
    ("Plant" + "\n" * 17 + "protein: 25 g", False),
    ("Plant" + "*" * 16 + " protein: 25 g", False),
    ("Serves 4 with plant\nprotein: 25 g", False),
    ("Total protein: 25 g.", True),
    ("The protein is 25 g per serving.", True),
    ("Protein rises by 5 g per serving.", True),
    ("Fat drops by 3 g per serving.", True),
    ("Calories rose from just 480 kcal to 500 kcal.", False),
    ("Calories rose from 480 kcal all the way to 500 kcal.", False),
    ("Calories fell from 500 kcal all the way to 480 kcal.", True),
    ("Protein changes by" + "*" * 64 + " 25 g.", False),
    ("Calories rose from" + "_" * 64 + " 480 kcal to 500 kcal.", False),
    ("Protein decreased from" + "_" * 64 + " 25 g to 20 g per serving.", False),
    ("The meal has 1920 kcal per person.", False),
    ("The meal has 1920 kcal, per serving.", False),
    ("The meal has 480 kcal, per serving.", True),
    ("Protein from tofu is 25 g.", False),
    ("Calories fell from 2000 kcal to 1920 per serving.", False),
    ("Protein rose from 80 g to 100 per serving.", False),
    ("Calories fell from 500 kcal to 480 in total.", False),
    ("Protein rose from 20 g to 25 in total.", False),
    ("Calories fell from 2000 kcal to 1920 per person.", False),
    ("Calories fell from 2000 kcal to 1920 kcal per serving.", False),
    ("Calories fell from 500 kcal to 480 per serving.", True),
    ("Protein rose from 20 g to 25 per serving.", True),
    ("Calories fell from 2000 kcal to 1920 in total.", True),
    ("Protein rose from 80 g to 100 in total.", True),
    ("Calories fell from 500 kcal to 480.", True),
    ("Calories fell from 2000 kcal to 1920.", True),
    ("Calories fell from 500 kcal to 480 kcal per serving.", True),
    ("Protein 20 to 25 g per serving (+5 g).", True),
    ("Protein 80 to 100 g in total (+20 g).", True),
]

QUANTITY_ROWS = [
    ("Protein is 100 g for 2 servings.", False),
    ("Protein is 100 g for 4 servings.", True),
]

_PLAN_FACTS = facts_from_payloads([("plan_nutrition", {"energy_kcal": 1920})])

GUARD_ROWS = [
    (_PLAN_FACTS, "The meal has 1920 kcal per person.", False),
    (_PLAN_FACTS, "The meal has 1920 kcal.", True),
    (_FACTS, "Calories rose from 500 kcal.", False),
    (_FACTS, "Calories fell from 500 kcal.", False),
]

ADVERSARIAL = [
    " ".join(f"fiber y {i} z" for i in range(400))[:1200],
    "Protein" + "*" * 1150 + "x 25 g",
    "Protein " + " " * 1180 + "25 g",
    ("25 g" + "*" * 1180 + "x\nprotein: 25 g")[:1200],
]


@pytest.mark.parametrize(("text", "expected"), ACCEPTANCE)
def test_acceptance_table(text: str, expected: bool) -> None:
    assert validate(text, _FACTS).ok == expected


@pytest.mark.parametrize(("text", "expected"), QUANTITY_ROWS)
def test_quantity_payload_servings(
    text: str, expected: bool, quantity_facts: FactSet
) -> None:
    assert validate(text, quantity_facts).ok == expected


@pytest.mark.parametrize(("facts", "text", "expected"), GUARD_ROWS)
def test_unmatched_basis_and_open_from_guards(
    facts: FactSet, text: str, expected: bool
) -> None:
    assert validate(text, facts).ok == expected


@pytest.mark.parametrize("text", ADVERSARIAL)
def test_adversarial_reply_validates_quickly(text: str) -> None:
    assert len(text) <= 1200
    start = perf_counter()
    validate(text, _FACTS)
    assert perf_counter() - start < 0.5
