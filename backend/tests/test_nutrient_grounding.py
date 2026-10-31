from decimal import Decimal
from itertools import permutations

import pytest

from app.agent.grounding import FactSet, facts_from_payloads, validate
from app.agent.ingredient_tool import INGREDIENT_TOOL, execute_ingredient_facts


def _facts(**payload: object) -> FactSet:
    return facts_from_payloads([("tool", payload)])


def _macros(protein: int, carbs: int, fat: int) -> dict[str, int]:
    return {"protein_mg": protein, "carbohydrate_mg": carbs, "fat_mg": fat}


def test_real_chicken_protein_cannot_ground_fat() -> None:
    payload = execute_ingredient_facts({"name": "chicken breast"})
    macros = payload["per_100g"]
    assert isinstance(macros, dict)
    assert macros["protein_mg"] == 22_500
    assert macros["fat_mg"] == 2_620
    facts = facts_from_payloads([(INGREDIENT_TOOL, payload)])
    assert not validate("It has 23 g fat.", facts).ok
    assert validate("It has 23 g protein and 2.6 g fat.", facts).ok


@pytest.mark.parametrize(
    "reply",
    [
        "14 g protein",
        "14 grams of protein",
        "Protein: 14 g",
        "Protein is 14 g",
        "PROTEINS: 14 G",
        "**Protein**: **14 g**",
        "_Protein_: _14 g_",
        "_14 g_ _protein_",
        "Protein:\n- 14 g",
        "14000 mg protein",
        "0.014 kg protein",
        "14 g total protein",
        "Total protein: 14 g",
    ],
)
def test_common_labels_bind_to_their_macro(reply: str) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000))
    assert validate(reply, facts).ok


@pytest.mark.parametrize(
    "claim",
    [
        "Protein is 14 g of flour",
        "Protein 14 g flour",
        "Protein 14 g of chicken",
        "Protein 14 g of ingredient",
        "Protein 14 g, flour",
        "Protein 14 g (flour)",
        "Protein 14 g of finely milled flour",
        "Protein 14 g the ingredient",
        "Protein 14 g: flour",
        "Protein 14 g, of flour",
        "Protein 14 g (of flour)",
        "Protein 14 g **flour**",
        "Protein **14 g of flour**",
        "**Protein 14 g**, **flour**",
        "Protein 14 g (_flour_)",
        "Protein 14 g of zorbium",
        "Protein 14 g zorbium",
        "Protein 14 g, zorbium",
        "Protein 14 g (zorbium)",
        "Protein 14 g (finely ground zorbium)",
        "Protein 14 g apparently",
        "Protein 14 g of protein powder",
        "Protein 14 g of protein (flour)",
        "Protein 14 g and 14 g of flour",
        "Protein 14 g (14000 mg of flour)",
        "Protein 14 g (14000 mg) flour",
        "Protein 14 g (14000 mg) of zorbium",
    ],
)
@pytest.mark.parametrize(
    "pattern",
    [
        "{claim}.",
        "{claim}, fat 9 g and carbohydrate 43 g.",
        "Fat 9 g, {claim}, carbohydrate 43 g.",
    ],
)
def test_prefix_amounts_reject_noun_qualified_tails(claim: str, pattern: str) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000), quantity_g=14)
    verdict = validate(pattern.format(claim=claim), facts)
    assert verdict.reasons == ("unmatched_number",), (claim, pattern, verdict)


@pytest.mark.parametrize(
    "reply",
    [
        "Protein: 14 g.",
        "14 g of protein.",
        "Protein 14 g of protein.",
        "Protein 14 g protein.",
        "Protein 14 g and fat 9 g.",
        "Protein 14 g, fat 9 g and carbohydrate 43 g.",
        "Fat 9 g, protein 14 g, carbohydrate 43 g.",
        "Protein 14 g. Add 14 g flour.",
        "Protein **14 g**. Add **14 g flour**.",
        "Protein 14 g (14000 mg).",
        "Protein 14 g (0.014 kg).",
        "Protein 14000 mg (14 g).",
        "Protein 0.014 kg (14 g).",
        "Protein 14 g (14000 mg), fat 9 g.",
        "Protein 14 g per serving.",
        "Protein 14 g per 100 g.",
        "Protein 14 g per serving, fat 9 g per serving.",
        "Protein 14 g per 100 g, fat 9 g per 100 g.",
        "Protein 14 g for 3 servings.",
    ],
)
def test_structural_claim_tails_keep_supported_grammar(reply: str) -> None:
    facts = _facts(
        **_macros(14_000, 43_000, 9_000),
        quantity_g=14,
        basis={"quantity_g": 100},
        servings=3,
    )
    assert validate(reply, facts).ok


@pytest.mark.parametrize(("fat_g", "fdc_id"), [(20, 174036), (25, 11)])
@pytest.mark.parametrize(
    "pattern",
    [
        "{fat_g} g fat (USDA FDC {fdc_id}).",
        "Protein 14 g, carbs 43 g, {fat_g} g fat (USDA FDC {fdc_id}).",
    ],
)
def test_structural_fdc_citations_require_independent_numeric_evidence(
    fat_g: int, fdc_id: int, pattern: str
) -> None:
    reply = pattern.format(fat_g=fat_g, fdc_id=fdc_id)
    macros = _macros(14_000, 43_000, fat_g * 1000)
    assert validate(reply, _facts(**macros, fdc_id=fdc_id)).ok
    missing = validate(reply, _facts(**macros))
    assert missing.reasons == ("unmatched_number",)
    assert missing.unmatched == (str(fdc_id),)
    wrong = validate(reply, _facts(**macros, fdc_id=fdc_id + 1))
    assert wrong.unmatched == (str(fdc_id),)


@pytest.mark.parametrize(
    "tail",
    [
        "(USDA FDC 174036 flour)",
        "(flour 174036)",
        "(USDA 174036)",
        "(USDA FDC 174036) of flour",
        "(USDA FDC 174036) flour",
        "(USDA FDC 174036) (flour)",
        "(USDA FDC 174036) of zorbium",
        "of flour (USDA FDC 174036)",
        "(flour)",
    ],
)
def test_fdc_citations_do_not_authorize_noun_qualifications(tail: str) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000), fdc_id=174036, quantity_g=14)
    verdict = validate(f"Protein 14 g {tail}.", facts)
    assert verdict.reasons == ("unmatched_number",)
    assert "14" in verdict.unmatched


def test_fdc_citations_do_not_change_the_bound_nutrient() -> None:
    facts = _facts(protein_mg=20_000, fdc_id=174036)
    assert not validate("20 g fat (USDA FDC 174036).", facts).ok


@pytest.mark.parametrize(
    "reply",
    [
        "gains 2.5 g fat but 38 kcal",
        "gains 2.5 g fat while protein and 38 kcal",
        "gains 2.5 g fat while 38 kcal",
    ],
)
def test_energy_clause_transitions_require_independent_energy(reply: str) -> None:
    facts = _facts(delta={"fat_mg": 2_500}, energy_kcal=38)
    assert validate(reply, facts).ok
    assert not validate(reply, FactSet(nutrition=facts.nutrition)).ok
    delta_only = _facts(delta={"fat_mg": 2_500, "energy_kcal": 38})
    assert not validate(reply, delta_only).ok


def test_prefix_nutrient_claim_can_end_before_an_energy_clause() -> None:
    reply = "Protein is 14 g but 38 kcal"
    assert validate(reply, _facts(protein_mg=14_000, energy_kcal=38)).ok
    assert not validate(reply, _facts(protein_mg=14_000)).ok


@pytest.mark.parametrize(
    ("reply", "amount"),
    [
        ("Protein 14 g of flour but 38 kcal", "14"),
        ("Protein is 14 g while flour and 38 kcal", "14"),
        ("Protein 14 g of zorbium while protein and 38 kcal", "14"),
        ("Protein 14 g (flour) but 38 kcal", "14"),
        ("gains 2.5 g fat of flour but 38 kcal", "2.5"),
        ("gains 2.5 g fat while flour and 38 kcal", "2.5"),
        ("gains 2.5 g fat while protein of flour and 38 kcal", "2.5"),
        ("Protein 14 g but 38 g", "14"),
    ],
)
def test_energy_transitions_reject_nouns_and_nonenergy_tokens(
    reply: str, amount: str
) -> None:
    facts = _facts(
        protein_mg=14_000,
        delta={"fat_mg": 2_500},
        energy_kcal=38,
        quantity_g=38,
    )
    verdict = validate(reply, facts)
    assert verdict.reasons == ("unmatched_number",)
    assert any(value.lstrip("+-") == amount for value in verdict.unmatched)


@pytest.mark.parametrize("protein_mg", [14_480, 14_484])
@pytest.mark.parametrize("amount", ["14", "14.5"])
def test_structural_claim_tails_keep_rounded_grams(
    protein_mg: int, amount: str
) -> None:
    assert validate(f"Protein {amount} g.", _facts(protein_mg=protein_mg)).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Protein 14 g per zorbium.",
        "Protein 14 g per serving of flour.",
        "Protein 14 g per 100 g flour.",
        "Protein 14 g for 3 servings of flour.",
    ],
)
def test_basis_phrases_reject_unparsed_noun_tails(reply: str) -> None:
    facts = _facts(
        **_macros(14_000, 43_000, 9_000), quantity_g=14, basis_g=100, servings=3
    )
    assert not validate(reply, facts).ok


def test_reference_mass_still_requires_its_own_fact() -> None:
    reply = "Protein 14 g per 100 g."
    assert not validate(reply, _facts(protein_mg=14_000)).ok
    assert validate(reply, _facts(protein_mg=14_000, quantity_g=100)).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Protein 14 g (15000 mg).",
        "Protein 14 g (0.015 kg).",
        "Protein 14 g (15000 mg), fat 9 g.",
    ],
)
def test_parenthesized_units_still_require_matching_nutrient_facts(reply: str) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000), quantity_mg=15_000)
    assert not validate(reply, facts).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Protein 26 to 15 g (-11 g).",
        "Protein 26 to 15 g (-11 g), fat 9 g.",
        "26 to 15 g protein (-11 g).",
    ],
)
def test_structural_claim_tails_keep_numeric_range_parentheses(reply: str) -> None:
    facts = _facts(
        before=_macros(26_000, 43_000, 9_000),
        after=_macros(15_000, 43_000, 9_000),
    )
    assert validate(reply, facts).ok


def test_structural_claim_tails_keep_directional_parentheses() -> None:
    facts = _facts(
        before=_macros(31_200, 43_000, 9_000),
        after=_macros(28_400, 43_000, 9_000),
    )
    assert validate("Protein drops by 2.8 g (from 31.2 g to 28.4 g).", facts).ok


@pytest.mark.parametrize("values", list(permutations((14, 43, 9))))
@pytest.mark.parametrize(
    "pattern",
    [
        "{0} g protein, {1} g carbs, and {2} g fat.",
        "Protein: {0} g, carbs: {1} g, fat: {2} g.",
        "Protein is {0} g and carbohydrate is {1} g and fat is {2} g.",
        "**{0} g proteins**, **{1} g carbohydrates**, **{2} g fats**.",
    ],
)
def test_coordinated_macro_permutations(
    values: tuple[int, int, int], pattern: str
) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000))
    assert validate(pattern.format(*values), facts).ok == (values == (14, 43, 9))


@pytest.mark.parametrize(
    "reply",
    [
        "Protein and fat: 14 g and 9 g.",
        "Protein/carbs: 14 g/43 g.",
        "14 g protein and fat.",
        "14 g of protein or carbs.",
        "Protein 14 g fat.",
        "Protein and carbs are 14 g and 43 g respectively.",
        "Protein has exactly 14 g.",
        "14 g in protein.",
        "Protein in grams: 14.",
        "14 of protein.",
        "Protein changes by - 14 g.",
    ],
)
def test_ambiguous_nutrition_grammar_fails_closed(reply: str) -> None:
    facts = _facts(**_macros(14_000, 43_000, 9_000), note="14 43 9")
    assert not validate(reply, facts).ok


def test_comma_nutrient_claim_cannot_use_an_ingredient_quantity() -> None:
    verdict = validate("14 g, protein", _facts(quantity_g=14))
    assert verdict.reasons == ("unmatched_number",)
    assert verdict.unmatched == ("14",)


@pytest.mark.parametrize(
    "reply",
    [
        "14 g, protein",
        "14 g, of protein",
        "14 g, and protein",
        "14 g, or protein",
        "14 g,, protein",
        "14 g, , of protein",
        "14 g, , and protein",
        "14 g, , or protein",
        "14 g, protein; 5 g fat",
        "14 g, or 9 g protein",
        "14 g, and 9 g protein",
        "14 g, , or 9 g protein",
        "14 g, of 9 g protein",
        "14 g, or 9 g, or 9 g protein",
        "14 g, or 9 g protein and 5 g fat",
        "14 g flour, protein",
        "14 g flour, and protein",
        "14 g salt, of fat",
        "14 g, sodium",
        "14 g, and more protein",
        "14 g, and protein later",
    ],
)
def test_comma_attribution_cannot_use_unrelated_mass(reply: str) -> None:
    facts = _facts(quantity_g=14, protein_mg=9_000, fat_mg=5_000, ingredient_g=5)
    verdict = validate(reply, facts)
    assert verdict.reasons == ("unmatched_number",), (reply, verdict)
    assert verdict.unmatched == ("14",), (reply, verdict)


@pytest.mark.parametrize(
    "reply",
    [
        "14 g flour",
        "14 g salt",
        "5 g flour",
        "14 g flour, and 9 g protein",
        "14 g salt, and 5 g fat",
        "Use 14 g\n9 g protein",
        "Use 14 g; 9 g protein",
        "9 g protein",
        "9 g protein for 3 servings",
        "9 g, or 9 g protein",
        "5 g fat",
    ],
)
def test_clear_ingredient_clauses_keep_independent_nutrients(reply: str) -> None:
    facts = _facts(
        quantity_g=14,
        protein_mg=9_000,
        fat_mg=5_000,
        ingredient_g=5,
        servings=3,
    )
    assert validate(reply, facts).ok


def test_deferred_fat_addition_keeps_the_generic_mass() -> None:
    facts = FactSet(mass={Decimal(5)})
    assert validate("Add 5 g, and more fat later.", facts).ok


@pytest.mark.parametrize(
    "label",
    [
        "saturated fat",
        "trans fat",
        "unsaturated fat",
        "monounsaturated fat",
        "polyunsaturated fat",
        "saturated total fat",
        "total trans fat",
        "net carbs",
        "fiber",
        "fibre",
        "sugars",
        "sodium",
        "potassium",
    ],
)
@pytest.mark.parametrize("pattern", ["{label}: 14 g", "14 g of {label}"])
def test_unsupported_nutrients_cannot_use_macro_or_generic_values(
    label: str, pattern: str
) -> None:
    facts = _facts(**_macros(14_000, 14_000, 14_000), note="14", sodium_mg=14_000)
    assert not validate(pattern.format(label=label), facts).ok


@pytest.mark.parametrize(
    "payload",
    [
        {"quantity_g": 67},
        {"quantity_mg": 67_000},
        {"note": "Option 67 has 67 g protein"},
        {"servings": 67},
        {"energy_kcal": 67},
        {"fat_mg": 67_000},
        {"protein_mg": "67000"},
        {"protein_mg": 67.0},
        {"protein_mg": [67_000]},
        {"total_protein_mg": 67_000},
        {"PROTEIN_MG": 67_000},
        {"protein_g": 67},
    ],
)
def test_only_exact_integer_macro_leaves_ground_nutrition(
    payload: dict[str, object],
) -> None:
    assert not validate("Protein: 67 g", _facts(**payload)).ok
    assert validate("Protein: 67 g", _facts(protein_mg=67_000)).ok


@pytest.mark.parametrize("reply", ["14 g", "14000 mg", "0.014 kg", "+14 g"])
def test_unlabelled_mass_cannot_use_macro_values(reply: str) -> None:
    facts = _facts(protein_mg=14_000, delta={"fat_mg": 14_000})
    assert not validate(reply, facts).ok
    assert validate(reply, _facts(quantity_mg=14_000, delta={"quantity_mg": 14_000})).ok


def test_plain_factset_mass_does_not_imply_a_nutrient() -> None:
    facts = FactSet(mass={Decimal(14)}, generic={Decimal(14)})
    assert not validate("14 g protein", facts).ok
    assert validate("14 g flour", facts).ok


def test_number_words_keep_the_nutrient() -> None:
    facts = _facts(**_macros(12_000, 9_000, 2_000))
    assert validate("Twelve grams protein and two grams fat.", facts).ok
    assert not validate("Two grams protein and twelve grams fat.", facts).ok


@pytest.mark.parametrize("values", list(permutations((14, 43, 9))))
@pytest.mark.parametrize("unit", ["g", "%"])
def test_delta_permutations_keep_nutrient_and_unit(
    values: tuple[int, int, int], unit: str
) -> None:
    facts = _facts(
        delta=_macros(14_000, 43_000, 9_000),
        delta_percent=_macros(14, 43, 9),
    )
    reply = (
        f"Protein changes by +{values[0]} {unit}, "
        f"carbs changes by +{values[1]} {unit}, fat changes by +{values[2]} {unit}."
    )
    assert validate(reply, facts).ok == (values == (14, 43, 9))
    assert not validate(reply.replace("+", "-"), facts).ok


def test_delta_percent_cannot_ground_mass_or_an_absolute_percent() -> None:
    facts = _facts(delta_percent=_macros(14, 43, 9))
    assert validate("Protein increases by 14%.", facts).ok
    assert validate("14 percent more protein.", facts).ok
    assert not validate("Fat increases by 14%.", facts).ok
    assert not validate("Protein: 14%.", facts).ok
    assert not validate("Protein changes by +14 mg.", facts).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Protein 26 to 15 g (-11 g).",
        "26 to 15 g protein (-11 g).",
        "Protein drops by 10.2 g.",
        "Protein drops by 10200 mg.",
        "Protein drops by 0.0102 kg.",
        "Protein drops by **10.2 g** (from 25.6 g to 15.4 g).",
        "Protein changes by -10 g.",
    ],
)
def test_ranges_and_display_deltas_keep_the_nutrient(reply: str) -> None:
    facts = _facts(
        before=_macros(25_600, 40_000, 9_000),
        after=_macros(15_400, 43_000, 8_000),
    )
    assert validate(reply, facts).ok
    switched = reply.replace("Protein", "Fat").replace("protein", "fat")
    assert not validate(switched, facts).ok


@pytest.mark.parametrize("values", list(permutations((14, 43, 9))))
def test_rounded_macro_permutations(values: tuple[int, int, int]) -> None:
    facts = _facts(**_macros(14_484, 43_200, 9_020))
    reply = f"{values[0]} g protein, {values[1]} g carbs, {values[2]} g fat"
    assert validate(reply, facts).ok == (values == (14, 43, 9))
    assert validate("14.5 g protein, 43.2 g carbs, 9.0 g fat", facts).ok


def test_fat_delta_cannot_ground_a_protein_change() -> None:
    facts = _facts(
        before=_macros(14_000, 43_000, 9_000),
        after=_macros(14_000, 43_000, 11_500),
    )
    assert validate("2.5 g more fat", facts).ok
    assert not validate("2.5 g more protein", facts).ok
    assert not validate("Protein gains 2.5 g", facts).ok
    assert not validate("Protein 14 to 14 g (+2.5 g)", facts).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Protein 9 g",
        "fat 14 g",
        "14 g of protein and 43 g of fat",
        "Protein 14 g (fat 14 g)",
        "Protein and fat: 14 g and 9 g",
        "Protein 9 to 14 g",
        "Protein: 14 g, or 67 g",
        "Protein is 14 g and 67 g",
        "Protein: 14 g plus 67 g",
        "14 g protein and 67 g",
        "Protein content is 67, or 67 g",
        "Protein content: 67 and 67 g",
        "Protein content is 67, or 67, or 67 g",
        "Protein content is 67 servings and 67 g.",
        "Protein content is 67 servings and 67 meals and 67 g.",
        "Protein 50 g",
        "Protein 67 g",
        "67 g sodium",
        "67 g of sodium",
    ],
)
def test_nutrition_continuations_cannot_use_unrelated_facts(reply: str) -> None:
    facts = _facts(
        **_macros(14_000, 43_000, 9_000),
        note="Option 67",
        quantity_mg=67_000,
        quantity_g=50,
        servings=67,
    )
    verdict = validate(reply, facts)
    assert verdict.reasons == ("unmatched_number",), (reply, verdict)


@pytest.mark.parametrize(
    "unit", ["servings", "meals", "oz", "ounces", "lb", "pounds", "packages"]
)
def test_unresolved_nutrition_reaches_mass_after_a_count(unit: str) -> None:
    facts = _facts(
        **_macros(14_000, 43_000, 9_000),
        servings=3,
        note="Option 3 67",
        quantity_mg=67_000,
    )
    verdict = validate(f"Protein content is 3 {unit} and 67 g.", facts)
    assert verdict.reasons == ("unmatched_number",)
    assert "67" in verdict.unmatched


@pytest.mark.parametrize(
    "continuation",
    [
        " servings. Use ",
        " servings; use ",
        " servings\nand ",
        "\nservings and ",
        " servings and flour weighs ",
    ],
)
def test_unresolved_counts_stop_at_clause_or_subject_boundaries(
    continuation: str,
) -> None:
    facts = _facts(protein_mg=14_000, servings=3, quantity_mg=67_000)
    verdict = validate(f"Protein content is 3{continuation}67 g flour.", facts)
    assert verdict.reasons == ("unmatched_number",)
    assert "3" in verdict.unmatched
    assert "67" not in verdict.unmatched


@pytest.mark.parametrize("reply", ["3 oz fat", "3 ounces protein", "3 servings of fat"])
def test_nutrient_counts_cannot_use_serving_facts(reply: str) -> None:
    facts = _facts(
        protein_mg=14_000,
        fat_mg=9_000,
        servings=3,
        quantity_mg=67_000,
        note="Option 67",
    )
    assert not validate(reply, facts).ok


def test_independent_servings_do_not_inherit_a_bound_nutrient() -> None:
    facts = _facts(protein_mg=14_000, servings=3)
    assert validate("14 g protein for 3 servings", facts).ok


@pytest.mark.parametrize(
    "payload", [{"quantity_mg": 67_000}, _macros(67_000, 67_000, 67_000)]
)
def test_sodium_cannot_use_generic_or_macro_mass(payload: dict[str, int]) -> None:
    assert not validate("67 g sodium", _facts(**payload)).ok


@pytest.mark.parametrize(
    "reply",
    [
        "14 g protein and 9 g fat",
        "Use 50 g",
        "67 g flour",
        "67 g of flour",
        "67 g salt",
        "67 g of salt",
    ],
)
def test_explicit_ingredient_quantities_remain_supported(reply: str) -> None:
    facts = _facts(
        **_macros(14_000, 43_000, 9_000),
        note="Option 67",
        quantity_mg=67_000,
        quantity_g=50,
        servings=67,
    )
    assert validate(reply, facts).ok


@pytest.mark.parametrize(
    "reply", ["Chicken breast has 23 g protein per 100 g", "23 g protein and 2.6 g fat"]
)
def test_chicken_protein_and_reference_mass_remain_supported(reply: str) -> None:
    payload = execute_ingredient_facts({"name": "chicken breast"})
    facts = facts_from_payloads([(INGREDIENT_TOOL, payload)])
    assert validate(reply, facts).ok


def test_a_range_delta_cannot_switch_to_fat() -> None:
    facts = _facts(
        before=_macros(26_000, 43_000, 10_000),
        after=_macros(15_000, 43_000, 15_000),
    )
    wrong = validate("Protein 26 to 15 g (-5 g)", facts)
    assert wrong.reasons == ("unmatched_number",)
    assert wrong.unmatched == ("-5",)
    assert validate("Protein 26 to 15 g (-11 g)", facts).ok


def test_fat_percent_changes_cannot_use_protein_percent() -> None:
    facts = _facts(delta_percent={"protein_mg": 43, "fat_mg": 12})
    wrong = validate("Fat changes by +43%", facts)
    assert wrong.reasons == ("unmatched_number",)
    assert wrong.unmatched == ("+43",)
    assert validate("Fat changes by +12%", facts).ok


def test_energy_and_fat_deltas_share_a_direction_verb() -> None:
    facts = _facts(delta={"energy_kcal": 38, "fat_mg": 2_500})
    assert validate("gains 38 kcal and 2.5 g fat", facts).ok
    assert not validate("gains 38 kcal and 2.5 g protein", facts).ok
