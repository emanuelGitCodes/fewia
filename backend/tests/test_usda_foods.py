import gzip
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.domain import usda_foods
from app.domain.curated_foods import (
    ALL_INGREDIENTS,
    ALL_NUTRITION,
    FOOD_TERMS,
    USDA_DEFAULTS,
)
from app.domain.nutrition import NutritionFacts
from app.domain.usda_foods import (
    BUNDLE_VERSION,
    COLUMNS,
    UsdaIndex,
    display_name,
    load_bundle,
    load_defaults,
    parse_bundle,
    word_tokens,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_usda_foods.py"
_FIXTURE = Path(__file__).parent / "fixtures" / "usda_sr"
_SHA = "cd" * 32
_CURATED_FDC_IDS = {174036, 173110, 167902, 168314, 171505, 175167}
_EXPECTED_DEFAULTS = {
    "tofu": 172475,
    "firm tofu": 172475,
    "tempeh": 174272,
    "shrimp": 175179,
    "cheese": 173414,
    "cheddar": 173414,
    "cheddar cheese": 173414,
    "mozzarella": 170845,
    "feta": 173420,
    "parmesan": 171247,
    "bacon": 168277,
    "tomatoes": 170457,
    "fresh tomato": 170457,
    "mushroom": 169251,
    "mushrooms": 169251,
    "potatoes": 170026,
    "tuna": 173709,
    "cod": 171955,
    "tilapia": 175176,
    "steak": 168726,
    "lamb": 174370,
    "avocado": 171705,
    "avocados": 171705,
    "greek yogurt": 170903,
    "yogurt": 171284,
    "milk": 171265,
    "pinto beans": 174286,
    "kidney beans": 174285,
    "spinach": 168462,
    "broccoli": 170379,
    "cauliflower": 169986,
    "peanut butter": 174266,
    "quinoa": 168874,
    "turkey breast": 171098,
    "italian sausage": 171631,
    "sausage": 171631,
    # Recipes and macro tracking use boneless skinless thigh, so meat only and raw
    # is the default (SR Legacy 173627); with skin stays one search away.
    "chicken thigh": 173627,
    "chicken thighs": 173627,
}
_CATEGORIES = (1, 2, 4, 5, 7, 9, 10, 11, 12, 13, 15, 16, 17, 20)
_VEGAN = {9, 11, 12, 16, 20}
_VEGETARIAN = _VEGAN | {1}
_INVALID = "^USDA foods are invalid: "


Mutation = Callable[[dict[str, Any]], object]


def _build_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_usda_foods", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(rows: list[list[object]]) -> dict[str, Any]:
    return {
        "version": BUNDLE_VERSION,
        "source": "USDA FoodData Central SR Legacy 2018-04",
        "source_sha256": _SHA,
        "columns": list(COLUMNS),
        "rows": rows,
    }


def row(fdc_id: int, description: str, category: int = 1) -> list[object]:
    return [fdc_id, description, category, 10, 20, 30, 40, 50]


def fixture_foods() -> list[usda_foods.UsdaFood]:
    script = _build_script()
    rows = script.build_rows(_FIXTURE, script.curated_fdc_ids())
    return parse_bundle(bundle(rows))


def index_of(*descriptions: str) -> UsdaIndex:
    rows = [row(number, text) for number, text in enumerate(descriptions, start=1)]
    return UsdaIndex(parse_bundle(bundle(rows)), {})


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "Tofu, raw, firm, prepared with calcium sulfate",
            "tofu (raw, firm, prepared with calcium sulfate)",
        ),
        ("Tempeh", "tempeh"),
        (
            "Beef, ground, 80% lean meat / 20% fat, raw",
            "beef (ground, 80% lean meat / 20% fat, raw)",
        ),
        (
            "Beans, kidney, raw (Includes foods for USDA's Food Program)",
            "beans (kidney, raw)",
        ),
        ("Beef (Includes x (nested) y), raw", "beef (raw)"),
        ("Rice (Includes brown)", "rice"),
        ("Spices,   pepper,   black", "spices (pepper, black)"),
        ("Fish, salmon (wild), raw", "fish (salmon (wild), raw)"),
        (
            "Chicken, broilers or fryers, dark meat, thigh, meat only, raw",
            "chicken (dark meat, thigh, meat only, raw)",
        ),
        ("Pork, fresh, loin, separable lean and fat, raw", "pork (loin, raw)"),
        ("Pork, Fresh", "pork (Fresh)"),
        (
            "Pork, fresh, composite of trimmed leg, loin, shoulder, and spareribs,"
            " separable lean only, cooked, braised, roasted",
            "pork (composite, cooked, braised, roasted)",
        ),
    ],
)
def test_display_names(description: str, expected: str) -> None:
    assert display_name(description) == expected
    if "composite of" in description:
        assert "composite" in display_name(description)


def test_a_long_last_qualifier_is_cut_at_a_word_boundary() -> None:
    assert display_name("Soup, alpha beta gamma delta", limit=20) == "soup (alpha beta)"
    assert display_name("Soup, alpha beta", limit=14) == "soup (alpha)"


def test_a_cut_never_leaves_an_open_parenthesis() -> None:
    assert display_name("Soup, milk (fat free and more)", limit=22) == "soup (milk)"


def test_includes_is_stripped_in_any_case() -> None:
    assert display_name("Beef (INCLUDES x), raw") == "beef (raw)"


def test_a_cut_never_lands_inside_a_word() -> None:
    assert display_name("Soup, alphabetagamma", limit=10) == "soup"
    assert display_name("Soup, composite of x, alphabetagamma", limit=10) == (
        "soup (composite)"
    )


def test_a_larger_limit_keeps_more_qualifiers() -> None:
    description = (
        "Pork, alpha beta gamma, delta epsilon zeta, eta theta iota,"
        " kappa lambda mu, nu xi omicron, raw"
    )
    short, long = display_name(description, 60), display_name(description, 90)
    assert len(long.split(", ")) > len(short.split(", "))
    assert "delta epsilon zeta" in long
    assert "delta epsilon zeta" not in short


def test_a_description_without_a_head_is_rejected() -> None:
    for text in ("(Includes x)", ", alpha, beta", "  , raw"):
        with pytest.raises(ValueError, match="USDA foods are invalid"):
            display_name(text)
        with pytest.raises(ValueError, match="USDA foods are invalid"):
            parse_bundle(bundle([row(1, text)]))


def test_names_that_collide_at_the_short_limit_are_retried_at_the_long_limit() -> None:
    same = "c" * 30
    foods = parse_bundle(
        bundle(
            [
                row(1, f"Pork, fresh, {'a' * 30}, {same}, raw"),
                row(2, f"Pork, fresh, {'b' * 30}, {same}, raw"),
            ]
        )
    )
    assert display_name(foods[0].description) == display_name(foods[1].description)
    # The full-name fallback would keep "fresh"; the 90 retry drops it.
    assert all("fresh" not in food.ingredient.name for food in foods)
    assert [food.ingredient.name for food in foods] == [
        f"pork ({'a' * 30}, {same}, raw)",
        f"pork ({'b' * 30}, {same}, raw)",
    ]


def test_identical_descriptions_fail_the_load() -> None:
    with pytest.raises(ValueError, match="names must be unique"):
        parse_bundle(bundle([row(1, "Pork, raw"), row(2, "Pork, raw")]))


@pytest.mark.parametrize(
    ("description", "expected", "state"),
    [
        (
            "Pork, fresh, composite of trimmed leg, loin, shoulder, and spareribs,"
            " separable lean only, cooked, braised, roasted",
            "pork (composite, separable lean only, cooked, braised, roasted)",
            "cooked",
        ),
        (
            "Beef, composite of trimmed retail cuts, separable lean and fat,"
            ' trimmed to 1/8" fat, all grades, raw',
            'beef (composite, trimmed to 1/8" fat, raw)',
            "raw",
        ),
    ],
)
def test_composite_cuts_are_named_composite_not_one_cut(
    description: str, expected: str, state: str
) -> None:
    name = display_name(description, limit=90)
    assert name == expected
    assert "composite" in name and state in name
    assert not any(cut in name for cut in ("leg", "loin", "shoulder", "spareribs"))


def test_a_composite_merge_covers_only_short_cuts_ending_in_and() -> None:
    merged = (
        "Pork, fresh, composite of trimmed leg, loin, shoulder, and spareribs,"
        " (includes cuts to be cured), separable lean and fat, raw"
    )
    assert display_name(merged) == "pork (composite, (includes cuts to be cured), raw)"
    unmerged = "Pork, fresh, composite of separable fat, with added solution, cooked"
    assert display_name(unmerged) == "pork (composite, with added solution, cooked)"


def test_composite_is_kept_at_every_limit_even_as_the_last_qualifier() -> None:
    assert display_name("Soup, alpha, composite of x") == "soup (alpha, composite)"
    assert display_name("Soup, alpha, composite of x", limit=10) == "soup (composite)"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tomatoes", {"tomato"}),
        ("peaches", {"peach"}),
        ("dishes", {"dish"}),
        ("potatoes", {"potato"}),
        ("beans, kidney 2%", {"bean", "kidney"}),
        ("oats", {"oat"}),
        ("glass bass", {"glass", "bass"}),
        ("gas yes", {"gas", "yes"}),
        ("cheese", {"cheese"}),
        ("123 !!", set()),
    ],
)
def test_word_tokens(text: str, expected: set[str]) -> None:
    assert word_tokens(text) == frozenset(expected)


def test_each_row_becomes_an_unpriced_gram_ingredient_with_facts() -> None:
    [food] = parse_bundle(bundle([[100, "Tofu, fried", 16, 1, 2, 3, 4, 5]]))
    ingredient = food.ingredient
    assert (ingredient.id, ingredient.name) == ("usda_100", "tofu (fried)")
    assert (ingredient.unit, ingredient.package_quantity) == ("g", 454)
    assert ingredient.price_cents is None and ingredient.is_pantry is False
    assert food.facts == NutritionFacts(100, 1, 2, 3, 4, 5)


@pytest.mark.parametrize("category", _CATEGORIES)
def test_diet_flags_follow_the_category(category: int) -> None:
    [food] = parse_bundle(bundle([row(1, "Thing, x", category)]))
    assert food.ingredient.vegan is (category in _VEGAN)
    assert food.ingredient.vegetarian is (category in _VEGETARIAN)


def test_meat_fish_fats_and_spices_are_neither_vegetarian_nor_vegan() -> None:
    for category in (2, 4, 5, 7, 10, 13, 15, 17):
        [food] = parse_bundle(bundle([row(1, "Thing, x", category)]))
        assert not food.ingredient.vegetarian and not food.ingredient.vegan


def _mutated(mutate: Mutation) -> dict[str, Any]:
    payload = bundle([row(1, "Tofu, fried", 16), row(2, "Tempeh", 16)])
    mutate(payload)
    return payload


def _row_field(index: int, value: object) -> Mutation:
    def mutate(payload: dict[str, Any]) -> None:
        payload["rows"][1][index] = value

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(version="usda-sr-legacy-2018-04-v2"),
        lambda p: p.update(columns=COLUMNS[::-1]),
        lambda p: p.update(columns=COLUMNS[:-1]),
        lambda p: p.update(extra=1),
        lambda p: p.pop("source"),
        lambda p: p.update(source=5),
        lambda p: p.update(source_sha256="AB" * 32),
        lambda p: p.update(source_sha256="ab" * 31),
        lambda p: p.update(source_sha256=None),
        lambda p: p.update(rows={}),
        lambda p: p["rows"].append([3, "short"]),
        lambda p: p["rows"].append([*row(3, "x"), 1]),
        lambda p: p["rows"].append("row"),
        lambda p: p["rows"].append(row(1, "Duplicate id")),
        lambda p: p["rows"].insert(0, row(9, "Unsorted")),
        _row_field(0, "2"),
        _row_field(0, 0),
        _row_field(0, True),
        _row_field(1, ""),
        _row_field(1, 5),
        _row_field(2, 1.5),
        _row_field(2, 0),
        _row_field(2, 3),
        _row_field(2, 14),
        _row_field(2, 21),
        _row_field(3, -1),
        _row_field(4, 2.0),
        _row_field(5, True),
        _row_field(7, None),
    ],
)
def test_parse_rejects_bad_headers_and_rows(mutate: Mutation) -> None:
    with pytest.raises(ValueError, match=_INVALID):
        parse_bundle(_mutated(mutate))


@pytest.mark.parametrize("payload", [None, [], "x", 5])
def test_parse_rejects_a_payload_that_is_not_an_object(payload: object) -> None:
    with pytest.raises(ValueError, match=_INVALID):
        parse_bundle(payload)


def test_parse_accepts_a_valid_bundle() -> None:
    assert len(parse_bundle(_mutated(lambda payload: None))) == 2


def test_an_absent_bundle_means_zero_foods(tmp_path: Path) -> None:
    assert load_bundle(tmp_path / "missing.json.gz") == []


def test_load_bundle_reads_a_gzip_file(tmp_path: Path) -> None:
    path = tmp_path / "ok.json.gz"
    text = json.dumps(bundle([row(1, "Tempeh", 16)]))
    path.write_bytes(gzip.compress(text.encode()))
    assert [food.ingredient.id for food in load_bundle(path)] == ["usda_1"]


@pytest.mark.parametrize(
    "content",
    [
        b"not gzip",
        gzip.compress(b"{not json"),
        gzip.compress(b"\xff\xfe"),
        b"\x1f\x8b\x08",
    ],
)
def test_load_bundle_rejects_unreadable_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.json.gz"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="^USDA foods are invalid: could not load"):
        load_bundle(path)


def write_defaults(path: Path, defaults: dict[str, object], **extra: object) -> Path:
    payload = {"version": "usda-defaults-v1", "defaults": defaults, **extra}
    path.write_text(json.dumps(payload))
    return path


def test_the_shipped_defaults_are_exactly_the_agreed_terms() -> None:
    assert USDA_DEFAULTS == _EXPECTED_DEFAULTS
    shipped = json.loads(usda_foods.DEFAULTS_PATH.read_text())
    assert shipped["version"] == "usda-defaults-v1"
    assert shipped["defaults"] == _EXPECTED_DEFAULTS
    assert all(term == term.lower() for term in USDA_DEFAULTS)
    assert not set(USDA_DEFAULTS) & FOOD_TERMS


def test_defaults_load_when_every_id_is_bundled(tmp_path: Path) -> None:
    path = write_defaults(tmp_path / "d.json", {"tofu": 1, "tempeh": 2})
    assert load_defaults(FOOD_TERMS, {1, 2, 3}, path) == {"tofu": 1, "tempeh": 2}
    assert load_defaults(FOOD_TERMS, None, path) == {"tofu": 1, "tempeh": 2}


def test_a_default_whose_fdc_id_is_not_bundled_is_rejected(tmp_path: Path) -> None:
    path = write_defaults(tmp_path / "d.json", {"tofu": 1, "tempeh": 99})
    with pytest.raises(ValueError, match=_INVALID):
        load_defaults(FOOD_TERMS, {1, 2}, path)


def test_the_shipped_defaults_need_their_foods_in_the_bundle() -> None:
    with pytest.raises(ValueError, match=_INVALID):
        load_defaults(FOOD_TERMS, {1, 2})


@pytest.mark.parametrize(
    "term",
    [
        "rice",
        "white rice",
        "black_beans",
        "black beans",
        "ground_beef_80",
        "ground beef (80% lean)",
        "beef",
        "hamburger",
        "salmon",
        "pork",
        "pork chop",
    ],
)
def test_a_default_term_may_not_shadow_a_catalog_or_curated_name(
    tmp_path: Path, term: str
) -> None:
    path = write_defaults(tmp_path / "d.json", {term: 1})
    with pytest.raises(ValueError, match=_INVALID):
        load_defaults(FOOD_TERMS, {1}, path)


@pytest.mark.parametrize(
    "defaults",
    [
        {"Tofu": 1},
        {"": 1},
        {"tofu  firm": 1},
        {"tofu": "1"},
        {"tofu": True},
        {"tofu": 1.0},
    ],
)
def test_malformed_defaults_are_rejected(
    tmp_path: Path, defaults: dict[str, object]
) -> None:
    path = write_defaults(tmp_path / "d.json", defaults)
    with pytest.raises(ValueError, match=_INVALID):
        load_defaults(FOOD_TERMS, None, path)


def test_malformed_defaults_files_are_rejected(tmp_path: Path) -> None:
    extra = write_defaults(tmp_path / "a.json", {"tofu": 1}, extra=1)
    wrong = tmp_path / "b.json"
    wrong.write_text(json.dumps({"version": "v0", "defaults": {"tofu": 1}}))
    broken = tmp_path / "c.json"
    broken.write_text("{not json")
    for path in (extra, wrong, broken, tmp_path / "missing.json"):
        with pytest.raises(ValueError, match=_INVALID):
            load_defaults(FOOD_TERMS, None, path)


def test_all_maps_end_with_the_usda_foods_after_catalog_and_curated() -> None:
    usda = list(usda_foods.USDA_INGREDIENTS)
    assert list(ALL_INGREDIENTS)[len(ALL_INGREDIENTS) - len(usda) :] == usda
    assert list(ALL_NUTRITION)[len(ALL_NUTRITION) - len(usda) :] == usda
    for key, ingredient in usda_foods.USDA_INGREDIENTS.items():
        assert ALL_INGREDIENTS[key] is ingredient
        assert ALL_NUTRITION[key] is usda_foods.USDA_NUTRITION[key]


# --- the resolver over the fixture foods ---------------------------------------------


def fixture_index() -> UsdaIndex:
    defaults = {"tofu": 100001, "cheese": 100004, "ghost": 999999}
    return UsdaIndex(fixture_foods(), defaults)


def test_a_default_term_picks_its_food() -> None:
    assert fixture_index().lookup("tofu") == ["usda_100001"]
    assert fixture_index().lookup("cheese") == ["usda_100004"]


def test_without_the_default_the_same_term_is_ambiguous() -> None:
    plain = UsdaIndex(fixture_foods(), {})
    assert plain.lookup("tofu") == ["usda_100001", "usda_100002"]


def test_a_default_pointing_outside_the_bundle_is_ignored() -> None:
    assert fixture_index().lookup("ghost") == []


def test_exact_display_names_and_descriptions_pick_one_food() -> None:
    index = fixture_index()
    description = "tofu, raw, firm, prepared with calcium sulfate"
    assert index.lookup(f"tofu ({description[6:]})") == ["usda_100001"]
    assert index.lookup(description) == ["usda_100001"]
    assert index.lookup("tempeh") == ["usda_100003"]
    assert index.lookup("beans (kidney, raw)") == ["usda_100007"]
    full = "beans, kidney, raw (includes foods for usda's food distribution program)"
    assert index.lookup(full) == ["usda_100007"]


def test_a_single_token_match_picks_that_food() -> None:
    index = fixture_index()
    assert index.lookup("feta") == ["usda_100006"]
    assert index.lookup("pinto beans") == ["usda_100008"]
    assert index.lookup("peppers") == ["usda_100021"]


def test_an_exact_token_set_wins_over_longer_matches() -> None:
    assert fixture_index().lookup("kidney beans") == ["usda_100017"]
    assert fixture_index().lookup("beans kidney") == ["usda_100017"]


def test_several_matches_without_an_exact_set_are_ranked_and_not_picked() -> None:
    index = fixture_index()
    assert index.lookup("chicken thigh") == ["usda_100014", "usda_100015"]
    assert index.lookup("milk") == ["usda_100019", "usda_100005"]
    assert index.lookup("beans") == ["usda_100008", "usda_100007", "usda_100017"]
    assert index.lookup("mozzarella") == ["usda_100020", "usda_100005"]


def test_ambiguous_results_list_at_most_three_candidates() -> None:
    cheese = UsdaIndex(fixture_foods(), {}).lookup("cheese")
    assert cheese == ["usda_100004", "usda_100006", "usda_100018"]


def test_ranking_prefers_head_segment_then_raw_then_fewer_tokens_then_id() -> None:
    by_head = index_of("Pizza, cheese", "Cheese sauce, mix", "Cheese, curd")
    assert by_head.lookup("cheese") == ["usda_3", "usda_2", "usda_1"]
    by_raw = index_of("Soup, cheese", "Stew, cheese, raw")
    assert by_raw.lookup("cheese") == ["usda_2", "usda_1"]
    by_count = index_of("Soup, cheese, a", "Stew, cheese")
    assert by_count.lookup("cheese") == ["usda_2", "usda_1"]
    by_id = index_of("Soup, cheese", "Stew, cheese")
    assert by_id.lookup("cheese") == ["usda_1", "usda_2"]
    five = index_of(*(f"Item{'x' * n}, cheese" for n in range(1, 6)))
    assert five.lookup("cheese") == ["usda_1", "usda_2", "usda_3"]


def test_plural_words_match_their_singular_descriptions() -> None:
    index = index_of("Tomatoes, red, ripe, raw", "Peaches, canned")
    assert index.lookup("tomato") == ["usda_1"]
    assert index.lookup("peach") == ["usda_2"]


@pytest.mark.parametrize("query", ["paneer", "seitan", "123", "!!", "tofu paneer", ""])
def test_no_match_returns_nothing(query: str) -> None:
    assert fixture_index().lookup(query) == []


def test_an_index_over_no_foods_resolves_nothing() -> None:
    assert UsdaIndex([], {"tofu": 172475}).lookup("tofu") == []


def test_fixture_foods_do_not_include_any_curated_fdc_id() -> None:
    ids = {food.facts.fdc_id for food in fixture_foods()}
    assert not ids & _CURATED_FDC_IDS


# --- the real bundle ----------------------------------------------------------------

needs_bundle = pytest.mark.skipif(not usda_foods.USDA_FOODS, reason="no USDA bundle")


@needs_bundle
def test_the_real_bundle_is_valid_and_excludes_curated_foods() -> None:
    assert len(usda_foods.USDA_FOODS) > 3000
    ids = {food.facts.fdc_id for food in usda_foods.USDA_FOODS}
    assert not ids & _CURATED_FDC_IDS
    assert load_bundle() == usda_foods.USDA_FOODS


@needs_bundle
def test_every_default_points_to_a_bundled_food() -> None:
    for term, fdc_id in USDA_DEFAULTS.items():
        assert ALL_NUTRITION[f"usda_{fdc_id}"].fdc_id == fdc_id, term


@needs_bundle
def test_every_real_display_name_resolves_back_to_its_food() -> None:
    from app.agent.ingredient_tool import resolve_food
    from app.domain.catalog import INGREDIENTS
    from app.domain.curated_foods import CURATED_INGREDIENTS, CURATED_SYNONYMS
    from app.domain.meal_tags import normalize_term

    shadowed = 0
    for food in usda_foods.USDA_FOODS:
        found = resolve_food(food.ingredient.name)
        query = normalize_term(food.ingredient.name)
        owners = [
            item
            for pool in (INGREDIENTS, CURATED_INGREDIENTS)
            for item in pool
            if query in (item, ALL_INGREDIENTS[item].name.lower())
        ] or [item for item, terms in CURATED_SYNONYMS.items() if query in terms]
        if owners:
            shadowed += 1
            assert (found.status, found.ids) == ("found", (owners[0],)), (
                food.ingredient.id
            )
            continue
        assert (found.status, found.ids) == ("found", (food.ingredient.id,)), (
            food.ingredient.id
        )
    assert shadowed <= 25, f"{shadowed} USDA names are shadowed by catalog or curated"


@needs_bundle
def test_chicken_thigh_resolves_to_the_meat_only_raw_food() -> None:
    from app.agent.ingredient_tool import resolve_food

    for query in ("chicken thigh", "chicken thighs"):
        found = resolve_food(query)
        assert (found.status, found.ids) == ("found", ("usda_173627",)), query


@needs_bundle
def test_chicken_thigh_foods_have_distinct_names() -> None:
    ids = (172385, 172855, 172859, 172863, 173627, 174502)
    names = {
        food.facts.fdc_id: food.ingredient.name
        for food in usda_foods.USDA_FOODS
        if food.facts.fdc_id in ids
    }
    assert len(names) == 6
    assert len(set(names.values())) == 6
    assert "with added solution" in names[172859]
    assert "with added solution" in names[172863]


@needs_bundle
def test_real_display_names_are_unique() -> None:
    names = [food.ingredient.name for food in usda_foods.USDA_FOODS]
    assert len(set(names)) == len(names)


@needs_bundle
def test_real_display_names_have_balanced_parentheses() -> None:
    for food in usda_foods.USDA_FOODS:
        depth = 0
        for char in food.ingredient.name:
            depth += {"(": 1, ")": -1}.get(char, 0)
            assert depth >= 0, food.ingredient.name
        assert depth == 0, food.ingredient.name


@needs_bundle
def test_nearly_all_real_display_names_are_short() -> None:
    names = [food.ingredient.name for food in usda_foods.USDA_FOODS]
    short = sum(len(name) <= 64 for name in names)
    assert short / len(names) >= 0.80


def test_colliding_short_names_fall_back_to_full_names() -> None:
    foods = parse_bundle(
        bundle(
            [
                row(1, "Pork, fresh, raw"),
                row(2, "Pork, raw"),
                row(3, "Pork, cooked"),
            ]
        )
    )
    assert [food.ingredient.name for food in foods] == [
        "pork (fresh, raw)",
        "pork (raw)",
        "pork (cooked)",
    ]


@needs_bundle
def test_real_ingredient_ids_are_prefixed_and_unique() -> None:
    ids = [food.ingredient.id for food in usda_foods.USDA_FOODS]
    assert len(set(ids)) == len(ids)
    assert all(item.startswith("usda_") for item in ids)
