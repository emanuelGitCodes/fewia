from app.domain.catalog import INGREDIENTS
from app.domain.spoonacular_catalog import SPOONACULAR_IDS


def test_spoonacular_ids_match_ingredients() -> None:
    assert set(SPOONACULAR_IDS) == set(INGREDIENTS)


def test_spoonacular_ids_are_positive_ints() -> None:
    for spoonacular_id in SPOONACULAR_IDS.values():
        assert type(spoonacular_id) is int
        assert spoonacular_id > 0


def test_eggs_id() -> None:
    assert SPOONACULAR_IDS["eggs"] == 1123


def test_chicken_breast_id() -> None:
    assert SPOONACULAR_IDS["chicken_breast"] == 5062
