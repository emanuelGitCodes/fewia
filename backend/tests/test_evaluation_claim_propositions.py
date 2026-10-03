from dataclasses import FrozenInstanceError, fields

import pytest

from app.evaluation_claim_propositions import (
    ClaimParse,
    PublicProposition,
    parse_public_claims,
)


@pytest.mark.parametrize(
    ("answer", "propositions"),
    [
        ("The plan is accepted.", (PublicProposition("accepted", True),)),
        ("The plan is over budget.", (PublicProposition("over_budget", True),)),
        (
            "The estimate exceeds the available budget.",
            (PublicProposition("over_budget", True),),
        ),
        (
            "The estimate exceeds the available budget of USD $17.03.",
            (
                PublicProposition("over_budget", True),
                PublicProposition("available_cents", 1703),
            ),
        ),
        (
            "A purchase price is missing, so this estimate is incomplete.",
            (PublicProposition("missing_price", True),),
        ),
        (
            "Estimated from the demo price catalog. Instacart prices, availability, "
            "taxes, delivery fees, and tips are not verified.",
            (PublicProposition("sample_estimate_notice", True),),
        ),
        (
            "Spending snapshot is stale; available budget uses the explicit "
            "temporary cap.",
            (PublicProposition("stale_budget_warning", True),),
        ),
        ("Source: Your entered budget.", (PublicProposition("source", "manual"),)),
        ("Source: Demo spending.", (PublicProposition("source", "fixture"),)),
        ("Source: Plaid Sandbox.", (PublicProposition("source", "plaid_sandbox"),)),
    ],
)
def test_plan_and_budget_propositions(
    answer: str, propositions: tuple[PublicProposition, ...]
) -> None:
    result = parse_public_claims(answer, vegan=False)
    assert result == ClaimParse(propositions, 0)
    assert result is not None
    assert [type(item.value) for item in result.propositions] == [
        type(item.value) for item in propositions
    ]


@pytest.mark.parametrize(
    ("prefix", "kind"),
    [
        ("The estimate total is", "total_cents"),
        ("Available for this plan:", "available_cents"),
        ("Pending:", "pending_cents"),
    ],
)
@pytest.mark.parametrize(
    ("amount", "cents"),
    [("$17.03", 1703), ("-$17.03", -1703), ("$0.09", 9), ("-$0.09", -9)],
)
def test_money_is_integer_cents(
    prefix: str, kind: str, amount: str, cents: int
) -> None:
    result = parse_public_claims(f"{prefix} USD {amount}.", vegan=False)
    assert result == ClaimParse((PublicProposition(kind, cents),), 0)
    assert result is not None
    assert type(result.propositions[0].value) is int


def test_negative_over_budget_amount_preserves_sign() -> None:
    assert parse_public_claims(
        "The estimate exceeds the available budget of USD -$17.03.", vegan=False
    ) == ClaimParse(
        (
            PublicProposition("over_budget", True),
            PublicProposition("available_cents", -1703),
        ),
        0,
    )


def test_plan_answer_preserves_atomic_notices_and_order() -> None:
    answer = (
        "The plan is accepted. The estimate total is USD $17.03. "
        "Estimated from the demo price catalog. Instacart prices, availability, "
        "taxes, delivery fees, and tips are not verified. "
        "Spending snapshot is stale; available budget uses the explicit temporary cap. "
        "There is no cross-contact risk."
    )
    assert parse_public_claims(answer, vegan=False) == ClaimParse(
        (
            PublicProposition("accepted", True),
            PublicProposition("total_cents", 1703),
            PublicProposition("sample_estimate_notice", True),
            PublicProposition("stale_budget_warning", True),
        ),
        1,
    )


def test_budget_answer_has_separate_money_and_source_propositions() -> None:
    assert parse_public_claims(
        "Available for this plan: USD $17.03. Pending: USD -$0.09. "
        "Source: Demo spending.",
        vegan=False,
    ) == ClaimParse(
        (
            PublicProposition("available_cents", 1703),
            PublicProposition("pending_cents", -9),
            PublicProposition("source", "fixture"),
        ),
        0,
    )


@pytest.mark.parametrize(
    ("answer", "kind", "vegan"),
    [
        ("Examples: bean tacos, vegetable pasta, lentil soup.", "choice", True),
        ("Supported choices: chicken tacos.", "choice", False),
        ("Would you like bean tacos instead?", "choice_question", True),
    ],
)
def test_catalog_choices(answer: str, kind: str, vegan: bool) -> None:
    assert parse_public_claims(answer, vegan=vegan) == ClaimParse(
        (PublicProposition(kind, True),), 0
    )


@pytest.mark.parametrize(
    "answer",
    [
        "Supported choices: chicken tacos.",
        "Examples: salmon tacos.",
        "The plan is accepted because everything is allergy safe.",
        "The estimate total is USD $17.3.",
        "The estimate total is USD $17.030.",
        "The estimate total is USD $17.03.45.",
        "The estimate total is USD $17.03 and all meals are allergy safe.",
        "Source: live retailer quotes.",
    ],
)
def test_unsupported_wording_is_not_inferred(answer: str) -> None:
    assert parse_public_claims(answer, vegan=True) == ClaimParse((), 1)


@pytest.mark.parametrize(
    ("answer", "unknown_count"),
    [
        ("Estimated from the demo price catalog.", 1),
        (
            "Estimated from the demo price catalog. Instacart prices, availability, "
            "taxes, delivery fees, and tips are verified.",
            2,
        ),
        (
            "Spending snapshot is stale; available budget uses a temporary cap.",
            2,
        ),
        (
            "Someone says Estimated from the demo price catalog. Instacart prices, "
            "availability, taxes, delivery fees, and tips are not verified.",
            2,
        ),
    ],
)
def test_notice_wording_must_be_exact(answer: str, unknown_count: int) -> None:
    assert parse_public_claims(answer, vegan=False) == ClaimParse((), unknown_count)


def test_unknown_clauses_around_notices_are_retained_as_counts() -> None:
    assert parse_public_claims(
        "Unknown wording. Estimated from the demo price catalog. Instacart prices, "
        "availability, taxes, delivery fees, and tips are not verified. "
        "More unknown wording.",
        vegan=False,
    ) == ClaimParse((PublicProposition("sample_estimate_notice", True),), 2)


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        ("I cannot provide credentials or raw bank records.", "secret_refusal"),
        ("I cannot buy items or place orders.", "reject_purchase"),
        ("I cannot open external links or place orders.", "reject_url"),
        ("That recipe is not in the catalog.", "unsupported"),
        ("Salmon tacos are not supported.", "unsupported"),
        ("Eggs are not vegan.", "egg_conflict"),
        ("Chicken tacos are not vegan.", "diet_conflict"),
        (
            "I cannot map mystery spice or nightshades to catalog ingredients.",
            "unknown",
        ),
        ("Which catalog ingredients should I exclude?", "restriction_question"),
        ("I can help prepare a grocery plan.", "help"),
        ("Change the recipe or the restriction.", "change"),
        (
            "Which meal should I plan, and what servings, restrictions, "
            "and pantry items apply?",
            "question",
        ),
    ],
)
def test_refusal_propositions(answer: str, kind: str) -> None:
    assert parse_public_claims(answer, vegan=True) == ClaimParse(
        (PublicProposition(kind, True),), 0
    )


def test_unknown_clauses_preserve_recognized_propositions() -> None:
    answer = "I cannot buy items or place orders. The moon is made of cheese."
    assert parse_public_claims(answer, vegan=False) == ClaimParse(
        (PublicProposition("reject_purchase", True),), 1
    )
    assert answer == "I cannot buy items or place orders. The moon is made of cheese."


def test_known_plan_clause_followed_by_unknown_wording() -> None:
    assert parse_public_claims(
        "The plan is accepted. All meals are allergy safe.", vegan=True
    ) == ClaimParse((PublicProposition("accepted", True),), 1)


def test_conflicting_claims_are_preserved_without_scoring() -> None:
    assert parse_public_claims(
        "The plan is accepted. The plan is over budget.", vegan=False
    ) == ClaimParse(
        (PublicProposition("accepted", True), PublicProposition("over_budget", True)),
        0,
    )


def test_clause_separators_preserve_decimal_amounts() -> None:
    assert parse_public_claims(
        "\tThe plan is accepted!\nPending: USD -$17.03;Unknown wording?\r",
        vegan=False,
    ) == ClaimParse(
        (
            PublicProposition("accepted", True),
            PublicProposition("pending_cents", -1703),
        ),
        1,
    )


def test_allergy_and_cross_contact_assertions_stay_unknown() -> None:
    answer = "All meals are allergy safe. There is no cross-contact risk."
    assert parse_public_claims(answer, vegan=True) == ClaimParse((), 2)


def test_unknown_money_clause_keeps_its_decimal_point() -> None:
    assert parse_public_claims("An unknown claim costs USD $17.03.", vegan=False) == (
        ClaimParse((), 1)
    )


@pytest.mark.parametrize(
    "answer",
    [
        None,
        17,
        True,
        {},
        [],
        b"Accepted.",
        "",
        " \n\t",
        "...!?;",
        "\x00",
        "The plan is accepted.\x01",
        "\ud800",
        "The plan is accepted.\udfff",
        "a" * 4097,
    ],
)
def test_invalid_input_returns_none(answer: object) -> None:
    assert parse_public_claims(answer, vegan=False) is None


def test_mutable_input_is_unchanged() -> None:
    answer: dict[str, object] = {"answer": "I cannot buy items or place orders."}
    assert parse_public_claims(answer, vegan=False) is None
    assert answer == {"answer": "I cannot buy items or place orders."}


def test_length_limit_is_inclusive() -> None:
    assert parse_public_claims("a" * 4096, vegan=False) == ClaimParse((), 1)


def test_contracts_have_only_observable_fields() -> None:
    proposition = PublicProposition("reject_purchase", True)
    result = ClaimParse((proposition,), 0)
    assert [field.name for field in fields(proposition)] == ["kind", "value"]
    assert [field.name for field in fields(result)] == ["propositions", "unknown_count"]
    assert not hasattr(proposition, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        proposition.kind = "changed"
    with pytest.raises(FrozenInstanceError):
        result.unknown_count = 7


def test_unknown_text_is_not_returned() -> None:
    answer = "The hidden unsupported sentence contains personal details."
    result = parse_public_claims(answer, vegan=False)
    assert result == ClaimParse((), 1)
    assert answer not in repr(result)
