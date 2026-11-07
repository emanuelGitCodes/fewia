"""True number forms that the validator must accept, and the false ones it must not."""

import pytest

from app.agent.grounding import FactSet, facts_from_payloads, validate

_SERVINGS = 2


def _what_if(
    before: dict[str, int], after: dict[str, int], percent: dict[str, int]
) -> dict[str, object]:
    """A what-if payload; the totals are the per-serving values times the servings."""

    def total(values: dict[str, int]) -> dict[str, int]:
        return {key: value * _SERVINGS for key, value in values.items()}

    def diff(new: dict[str, int], old: dict[str, int]) -> dict[str, int]:
        return {key: new[key] - old[key] for key in old}

    return {
        "status": "swapped",
        "servings": _SERVINGS,
        "before": {"per_serving": before, "total": total(before)},
        "after": {"per_serving": after, "total": total(after)},
        "delta": {
            "per_serving": diff(after, before),
            "total": diff(total(after), total(before)),
        },
        "delta_percent": percent,
    }


def _facts(payload: dict[str, object], tool: str = "what_if_substitute") -> FactSet:
    return facts_from_payloads([(tool, payload)])


# Protein +9,972 mg (+69%), carbohydrate -28,452 mg (-51%), fat +5,000 mg (+37%),
# and energy +28 kcal.
_MAIN = _facts(
    _what_if(
        {
            "energy_kcal": 559,
            "protein_mg": 14484,
            "carbohydrate_mg": 55780,
            "fat_mg": 13600,
        },
        {
            "energy_kcal": 587,
            "protein_mg": 24456,
            "carbohydrate_mg": 27328,
            "fat_mg": 18600,
        },
        {"protein_mg": 69, "carbohydrate_mg": -51, "fat_mg": 37},
    )
)
# Protein falls 2,800 mg, from 31.2 g to 28.4 g.
_DROP = _facts(_what_if({"protein_mg": 31200}, {"protein_mg": 28400}, {}))
# Carbohydrate rises 4,452 mg, from 55.8 g to 60.2 g: the tenth-gram values differ by
# 4.4 g, but 4,452 mg rounds to 4.5 g.
_KEEP = _facts(
    _what_if(
        {"protein_mg": 20000, "carbohydrate_mg": 55780},
        {"protein_mg": 20000, "carbohydrate_mg": 60232},
        {},
    )
)
_MOVE = _facts(
    _what_if(
        {"protein_mg": 20000, "carbohydrate_mg": 55780},
        {"protein_mg": 22000, "carbohydrate_mg": 60232},
        {},
    )
)
_BUDGET = _facts({"period": "2026-09-01", "available_cents": 10000}, "get_budget")
_NO_PERIOD = _facts({"available_cents": 10000}, "get_budget")


def _scaled(ingredient_id: str, percent: int) -> FactSet:
    return _facts(
        {
            "scale_ingredient_id": ingredient_id,
            "scale_factor_percent": percent,
            "total_cents": 2113,
        }
    )


# Protein falls 2,880 mg, from 31.2 g to 28.4 g; carbohydrate rises 4,452 mg, from
# 55.8 g to 60.2 g.
_PAIR = _facts(
    _what_if(
        {"protein_mg": 31240, "carbohydrate_mg": 55780},
        {"protein_mg": 28360, "carbohydrate_mg": 60232},
        {},
    )
)
# One what-if with a zero protein change and one with a nonzero protein change.
_BOTH = facts_from_payloads(
    [
        (
            "what_if_substitute",
            _what_if(
                {"protein_mg": 20000, "carbohydrate_mg": 55780},
                {"protein_mg": 20000, "carbohydrate_mg": 60232},
                {},
            ),
        ),
        (
            "what_if_substitute",
            _what_if(
                {"protein_mg": 20000, "carbohydrate_mg": 55780},
                {"protein_mg": 22000, "carbohydrate_mg": 60232},
                {},
            ),
        ),
    ]
)

ACCEPT = [
    (_MAIN, "Protein: Increases from 14,484 mg to 24,456 mg per serving (about +69%)."),
    (_MAIN, "Carbohydrate: Decreases from 55,780 mg to 27,328 mg per serving (-51%)."),
    (_DROP, "Protein: Drops by about 2.8 g per serving (from 31.2 g to 28.4 g)."),
    (_MAIN, "Fat: Increases by about 5.0 g per serving (from 13.6 g to 18.6 g)."),
    (
        _MAIN,
        "Calories: Rise by about 28 kcal per serving (from 559 kcal to 587 kcal).",
    ),
    (
        _KEEP,
        "adds 4.5 g of carbohydrates per serving, while keeping the protein the same.",
    ),
    (_BUDGET, "Your budget for 2026-09-01 is USD $100.00."),
    (_PAIR, "Carbohydrate: Increases from 55.8 g to 60.2 g per serving."),
    (
        _PAIR,
        "Protein: Drops by about 2.9 g per serving (from 31.2 g to 28.4 g).",
    ),
]

REJECT = [
    pytest.param(
        _MAIN,
        "Protein: Increases from 28,968 mg to 48,912 mg per serving (about +69%).",
        id="total-called-per-serving",
    ),
    pytest.param(
        _MAIN,
        "Protein: Increases from 14,484 mg to 24,456 mg in total (about +69%).",
        id="per-serving-called-total",
    ),
    pytest.param(
        _MAIN,
        "Protein: Decreases from 14,484 mg to 24,456 mg per serving (about +69%).",
        id="wrong-sign",
    ),
    pytest.param(
        _MAIN,
        "Protein: Increases from 24,456 mg to 14,484 mg per serving (about +69%).",
        id="before-called-after",
    ),
    pytest.param(
        _MAIN,
        "Protein: Increases from 14,484 mg to 24,456 mg per serving (about +37%).",
        id="percent-of-another-nutrient",
    ),
    pytest.param(
        _MAIN,
        "Protein: Increases from 14,484 mg to 25,000 mg per serving (about +69%).",
        id="value-from-no-payload",
    ),
    pytest.param(
        _MAIN,
        "Calories: Rise by about 28 kcal per serving (from 1118 kcal to 1174 kcal).",
        id="energy-totals-called-per-serving",
    ),
    pytest.param(_DROP, "Protein: Add 28 g.", id="after-value-as-change"),
    pytest.param(_MAIN, "Calories: Rise by 587 kcal.", id="energy-after-as-change"),
    pytest.param(
        _MAIN,
        "Protein: Increases from 14,484 mg to 24,457 mg per serving (about +69%).",
        id="milligram-digit-changed",
    ),
    pytest.param(
        _DROP,
        "Protein: Drops by about 2.9 g per serving (from 31.2 g to 28.4 g).",
        id="gram-off-by-a-tenth",
    ),
    pytest.param(
        _KEEP,
        "adds 4.4 g of carbohydrates per serving.",
        id="tenth-gram-difference",
    ),
    pytest.param(
        _KEEP,
        "adds 4.4 g of carbohydrates per serving, while keeping the protein the same.",
        id="tenth-gram-difference-with-tail",
    ),
    pytest.param(
        _MOVE,
        "adds 4.5 g of carbohydrates per serving, while keeping the protein the same.",
        id="kept-nutrient-changed",
    ),
    pytest.param(
        _BUDGET, "Your budget for 2026-09-02 is USD $100.00.", id="date-day-changed"
    ),
    pytest.param(
        _NO_PERIOD, "Your budget for 2026-09-01 is USD $100.00.", id="date-no-period"
    ),
    pytest.param(
        _BUDGET, "Your budget for 2026-09-01T10:00 is USD $100.00.", id="date-time"
    ),
    pytest.param(
        _scaled("rice", 50), "with half the white rice price.", id="half-the-price"
    ),
    pytest.param(_scaled("rice", 50), "with half the calories.", id="half-calories"),
    pytest.param(_scaled("rice", 50), "half the protein.", id="half-protein"),
    pytest.param(
        _PAIR,
        "Protein: Drops by about 2.8 g per serving (from 31.2 g to 28.4 g).",
        id="pair-gram-off-by-a-tenth",
    ),
    pytest.param(
        _PAIR,
        "Protein: Rises from 31.2 g to 28.4 g per serving.",
        id="pair-wrong-direction",
    ),
    pytest.param(
        _PAIR,
        "Carbohydrate: Increases from 55.8 g to 60.3 g per serving.",
        id="pair-after-value-changed",
    ),
    pytest.param(
        _PAIR, "adds 4.4 g of carbohydrates per serving.", id="pair-tenth-difference"
    ),
    pytest.param(
        _BOTH,
        "adds 4.5 g of carbohydrates per serving, while keeping the protein the same.",
        id="kept-nutrient-flat-in-one-payload-only",
    ),
]

# "half" is a number word and is never grounded, even for a payload that halves.
NUMBER_WORD = [
    pytest.param(
        _scaled("rice", 50), "with half the rice is USD $21.13.", id="half-the-rice"
    ),
    pytest.param(_scaled("rice", 50), "with half the salt.", id="half-the-salt"),
]


@pytest.mark.parametrize(("facts", "text"), ACCEPT)
def test_true_forms_are_accepted(facts: FactSet, text: str) -> None:
    verdict = validate(text, facts)
    assert verdict.ok, verdict


@pytest.mark.parametrize(("facts", "text"), REJECT)
def test_false_forms_are_rejected(facts: FactSet, text: str) -> None:
    assert not validate(text, facts).ok


@pytest.mark.parametrize(("facts", "text"), NUMBER_WORD)
def test_half_is_a_number_word(facts: FactSet, text: str) -> None:
    assert "number_word" in validate(text, facts).reasons
