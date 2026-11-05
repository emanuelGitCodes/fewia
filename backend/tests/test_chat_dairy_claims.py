import json
from datetime import date

import pytest

from app.agent.budget_tool import TOOL_NAME as BUDGET_TOOL_NAME
from app.agent.budget_tool import budget_summary_answer
from app.agent.chat_loop import run_chat
from app.domain.budget import BudgetResult


class FakeProvider:
    def __init__(self, replies: list[dict[str, object]]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.requests.append(
            {"system": system_prompt, "messages": messages, "tools": tools}
        )
        return self.replies.pop(0)


def _tool_reply() -> dict[str, object]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "budget-call",
                            "name": BUDGET_TOOL_NAME,
                            "input": {},
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def _text_reply(text: str) -> dict[str, object]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            },
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


@pytest.mark.parametrize(
    "claim",
    [
        "This meal contains no dairy.",
        "This meal has **no dairy**.",
        "This meal has n.o d.a.i.r.y.",
        "This meal has n o d a i r y.",
        "This meal contains no_dairy.",
        "This meal has _no dairy_.",
        "No dairy.",
        "NO-DAIRY.",
        "**No** **dairy**.",
        "_No_ _dairy_.",
        "N o d a i r y.",
        "n-o-d-a-i-r-y.",
        "n_o_d_a_i_r_y.",
        "**n** **o** **d** **a** **i** **r** **y**.",
        "This recipe uses non-dairy yogurt.",
        "This recipe uses **non** **dairy** yogurt.",
        "This recipe uses _non_dairy_ yogurt.",
        "This recipe uses n.o.n d.a.i.r.y yogurt.",
        "This recipe uses n o n d a i r y yogurt.",
        "This meal is milk-free.",
        "This meal is _milk-free_.",
        "This meal is __milk-free__.",
        "_milk-free_.",
        "__milk-free__.",
        "This meal is _milk_ _free_.",
        "This meal is _milk_-_free_.",
        "This meal is __milk__-__free__.",
        "This meal is _m_ _i_ _l_ _k_ _f_ _r_ _e_ _e_.",
        "This meal is __m__ __i__ __l__ __k__ __f__ __r__ __e__ __e__.",
        "This meal is milk_free.",
        "milk_free.",
        "This meal is m_i_l_k_f_r_e_e.",
        "This meal is m.i.l.k.f.r.e.e.",
        "This meal is m i l k f r e e.",
        "This meal is **milk-free**.",
        "This meal is (milk-free).",
        "This meal is [milk-free]!",
        'This meal is "milk-free".',
        "This meal is milk/free.",
        "Chicken tacos don't contain dairy.",
        "Chicken tacos do not contain dairy.",
        "Chicken tacos are free from all dairy.",
        "This meal doesn't include any dairy.",
        "Chicken tacos do not include dairy.",
        "This meal does not have dairy.",
        "Chicken tacos don't have any dairy.",
        "This meal doesn't use dairy.",
        "Chicken tacos do not use any dairy.",
        "This meal hasn't got any dairy.",
        "Chicken tacos haven't got dairy.",
        "This meal has not got any dairy.",
        "Chicken tacos have not got any dairy.",
        "This meal is free of all dairy.",
        "Chicken tacos are without any dairy.",
        "Chicken tacos are without dairy.",
        "This meal is not made with dairy.",
        "Chicken tacos are not made from dairy.",
        "This meal isn't prepared with any dairy.",
        "Chicken tacos aren't cooked from any dairy.",
        "This meal isn’t cooked with dairy.",
        "Chicken tacos aren’t prepared from dairy.",
        "This meal **is not made with dairy**.",
        "Chicken tacos ARE-NOT-PREPARED-FROM-ANY-DAIRY.",
        "This garlic knot is not made with dairy.",
        "This garlic knot is not prepared with dairy.",
        "This garlic knot is not cooked with dairy.",
        "This garlic knot is **not made with dairy**.",
        "This garlic knot is n.o.t m.a.d.e w.i.t.h d.a.i.r.y.",
        "This garlic knot is n o t p r e p a r e d w i t h d a i r y.",
        "This garlic knot is NOT-COOKED-WITH-DAIRY.",
    ],
)
def test_budget_then_dairy_claim_returns_the_template_answer(claim: str) -> None:
    _assert_budget_claim_rejected(claim)


@pytest.mark.parametrize(
    "reply",
    [
        "This recipe contains oregano, dairy, and rice.",
        "This recipe contains oregano dairy and rice.",
        "This recipe contains oregano; dairy; rice.",
        "The ingredients are oregano/dairy/rice.",
        "This recipe contains oregano. Dairy is listed as an ingredient.",
        "This recipe contains **oregano**, **dairy**, and rice.",
        "This recipe contains _oregano_, _dairy_, and rice.",
        "This recipe contains OREGANO, DAIRY, and rice.",
        "This recipe contains oregano,\ndairy, and rice.",
        "This recipe uses Dannon dairy yogurt.",
        "This recipe uses **Dannon** _dairy_ yogurt.",
        "A garlic knot made with dairy butter.",
        "A garlic knot prepared with dairy butter.",
        "A garlic knot cooked with dairy butter.",
        "A garlic **knot** made with **dairy** butter.",
        "This recipe contains Romano, dairy, and rice.",
        "This recipe contains poblano, dairy, and rice.",
        "This recipe contains jalapeño, dairy, and rice.",
        "No garlic. Dairy is listed as an ingredient.",
        "**No.** Dairy is listed as an ingredient.",
        "**Milk.** **Free** delivery is available.",
        "No : Dairy is listed as an ingredient.",
        "Milk : Free delivery is available.",
        "**No** . **Dairy** is listed as an ingredient.",
        "_Milk_ : _Free_ delivery is available.",
        "**No**. **Dairy** is listed as an ingredient.",
        "_Milk_. _Free_ delivery is available.",
        '"No". "Dairy" is listed as an ingredient.',
        "No?! Dairy is listed as an ingredient.",
        "No... Dairy is listed as an ingredient.",
        "Milk freezes when chilled.",
        "_Milk_ _freezes_ when chilled.",
        "__Milk__ __freezes__ when chilled.",
        "**Milk** **freezes** when chilled.",
        "Milk_freezes when chilled.",
        "Milk/freezes when chilled.",
        "_M_ _i_ _l_ _k_ freezes when chilled.",
        "M.i.l.k freezes when chilled.",
        "M i l k freezes when chilled.",
    ],
)
def test_budget_then_ingredient_text_returns_the_exact_model_answer(
    reply: str,
) -> None:
    period = date(2026, 9, 1)
    budget = BudgetResult(10_000, 250, False, ())
    provider = FakeProvider([_tool_reply(), _text_reply(reply)])

    result = run_chat(
        provider,
        "What is my remaining budget?",
        budget,
        period,
        model_prose=True,
    )

    assert len(provider.requests) == 2
    assert result["answer"] == reply.replace("ñ", "n")
    assert result["reply_source"] == "model"
    assert result["reply_check"] == {
        "ok": True,
        "reasons": [],
        "unmatched": [],
        "gate": "clean",
    }
    assert result["tool_trace"] == [
        {
            "tool": BUDGET_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "budget-call",
            "sequence": 1,
            "revision_index": None,
        }
    ]


@pytest.mark.parametrize("punctuation", list(".,;:!?") + ["?!", "..."])
@pytest.mark.parametrize(
    ("whitespace", "normalized_whitespace"),
    [(" ", " "), ("  ", " "), ("\n", "\n"), ("\n\n", "\n\n"), ("\t", " ")],
)
@pytest.mark.parametrize(
    ("lead", "tail"),
    [
        ("No", "Dairy is listed as an ingredient."),
        ("**No**", "**Dairy** is listed as an ingredient."),
        ("_No_", "_Dairy_ is listed as an ingredient."),
        ('"No"', '"Dairy" is listed as an ingredient.'),
        ("Milk", "Free delivery is available."),
        ("Milk", "**Free** delivery is available."),
        ("It is not", "Made with dairy butter, the sauce contains milk."),
        ("Delivery is free", "From dairy ingredients, the recipe uses milk."),
        ("Delivery is free", "Of dairy ingredients, milk is listed."),
        ("This meal contains no", "Dairy is listed as an ingredient."),
        ("This meal does not contain", "Dairy is listed as an ingredient."),
        ("This meal has not got", "Dairy is listed as an ingredient."),
        ("This meal is without", "Dairy is listed as an ingredient."),
        ("This meal is not prepared", "From dairy ingredients, milk is listed."),
        ("This meal is not cooked", "With dairy butter, the sauce contains milk."),
    ],
)
def test_budget_then_separate_dairy_clauses_keeps_normalized_model_text(
    lead: str,
    tail: str,
    punctuation: str,
    whitespace: str,
    normalized_whitespace: str,
) -> None:
    period = date(2026, 9, 1)
    budget = BudgetResult(10_000, 250, False, ())
    reply = f"  {lead}{punctuation}{whitespace}{tail}  "
    provider = FakeProvider([_tool_reply(), _text_reply(reply)])

    result = run_chat(
        provider,
        "What is my remaining budget?",
        budget,
        period,
        model_prose=True,
    )

    assert len(provider.requests) == 2
    assert result["answer"] == f"{lead}{punctuation}{normalized_whitespace}{tail}"
    assert result["reply_source"] == "model"
    assert result["reply_check"] == {
        "ok": True,
        "reasons": [],
        "unmatched": [],
        "gate": "clean",
    }
    assert result["tool_trace"] == [
        {
            "tool": BUDGET_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "budget-call",
            "sequence": 1,
            "revision_index": None,
        }
    ]


@pytest.mark.parametrize("apostrophe", ["'", "’"])
@pytest.mark.parametrize(
    "layout",
    [
        "{lead}. {tail}",
        "{lead}, {tail}",
        "{lead}; {tail}",
        "{lead}: {tail}",
        "{lead}! {tail}",
        "{lead}? {tail}",
        "{lead}?! {tail}",
        "{lead}... {tail}",
        "{lead}  :\t{tail}",
        "{lead}.\n{tail}",
        "**{lead}.** **{tail}**",
        "**{lead}** . **{tail}**",
        "_{lead}_ : _{tail}_",
        '"{lead}." "{tail}"',
    ],
)
@pytest.mark.parametrize(
    ("lead", "tail"),
    [
        ("This meal doesn't", "Include dairy."),
        ("Chicken tacos don't", "Contain dairy."),
        ("This meal hasn't", "Got dairy butter."),
        ("Chicken tacos haven't", "Got dairy butter."),
        ("This meal isn't", "Made with dairy butter."),
        ("Chicken tacos aren't", "Cooked from dairy butter."),
    ],
)
def test_budget_contracted_dairy_clauses_keep_normalized_model_text(
    lead: str, tail: str, layout: str, apostrophe: str
) -> None:
    period = date(2026, 9, 1)
    budget = BudgetResult(10_000, 250, False, ())
    reply = layout.format(lead=lead.replace("'", apostrophe), tail=tail)
    expected = layout.format(lead=lead, tail=tail).replace("  ", " ").replace("\t", " ")
    provider = FakeProvider([_tool_reply(), _text_reply(reply)])

    result = run_chat(
        provider,
        "What is my remaining budget?",
        budget,
        period,
        model_prose=True,
    )

    assert len(provider.requests) == 2
    assert result["answer"] == expected
    assert result["reply_source"] == "model"
    assert result["reply_check"] == {
        "ok": True,
        "reasons": [],
        "unmatched": [],
        "gate": "clean",
    }
    assert result["tool_trace"] == [
        {
            "tool": BUDGET_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "budget-call",
            "sequence": 1,
            "revision_index": None,
        }
    ]


def _assert_budget_claim_rejected(claim: str) -> None:
    period = date(2026, 9, 1)
    budget = BudgetResult(10_000, 250, False, ())
    provider = FakeProvider([_tool_reply(), _text_reply(claim)])

    result = run_chat(
        provider,
        "What is my remaining budget?",
        budget,
        period,
        model_prose=True,
    )

    assert len(provider.requests) == 2
    assert result["reply_source"] == "template"
    assert result["answer"] == budget_summary_answer(
        budget, period, spending_source="fixture"
    )
    assert result["reply_check"] == {
        "ok": False,
        "reasons": ["forbidden_claim"],
        "unmatched": [],
        "gate": "clean",
    }
    assert result["tool_trace"] == [
        {
            "tool": BUDGET_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "budget-call",
            "sequence": 1,
            "revision_index": None,
        }
    ]
    assert claim not in json.dumps(result)


@pytest.mark.parametrize("apostrophe", ["'", "’"])
@pytest.mark.parametrize("separator", [" ", "\n", "-\n", "_", "/", ".", "** **"])
@pytest.mark.parametrize(
    ("lead", "tail"),
    [
        ("This meal doesn't", "include dairy."),
        ("Chicken tacos don't", "contain dairy."),
        ("This meal hasn't", "got dairy butter."),
        ("Chicken tacos haven't", "got dairy butter."),
        ("This meal isn't", "made with dairy butter."),
        ("Chicken tacos aren't", "cooked from dairy butter."),
    ],
)
def test_budget_contracted_dairy_claims_return_the_exact_template(
    lead: str, tail: str, separator: str, apostrophe: str
) -> None:
    lead = lead.replace("'", apostrophe)
    _assert_budget_claim_rejected(f"{lead}{separator}{tail}")


@pytest.mark.parametrize("separator", [*".,;:!?", "\n", "-\n", "_", "/", "** **"])
@pytest.mark.parametrize(
    ("lead", "tail"),
    [
        ("No", "Dairy."),
        ("Milk", "Free."),
        ("This meal is free", "of dairy."),
        ("This meal does not", "contain dairy."),
        ("This meal hasn't got", "dairy."),
        ("This meal is without", "dairy."),
        ("This meal is not", "made with dairy."),
    ],
)
def test_budget_dairy_alias_formats_return_the_exact_template(
    lead: str, tail: str, separator: str
) -> None:
    _assert_budget_claim_rejected(f"{lead}{separator}{tail}")


@pytest.mark.parametrize(
    "claim",
    [
        "This meal is milk.free.",
        "This meal is free.of.dairy.",
        "n.o d.a.i.r.y.",
        "n.o. d.a.i.r.y.",
        "n.o.n. d.a.i.r.y.",
        "n'o. d.a.i.r.y.",
        "m'i'l'k. f.r.e.e.",
        "m.i.l.k f.r.e.e.",
        "m.i.l.k. f.r.e.e.",
        "This meal is n.o.t. m.a.d.e. w.i.t.h. d.a.i.r.y.",
        "This meal is i.s.n.t. p.r.e.p.a.r.e.d. f.r.o.m. a.n.y. d.a.i.r.y.",
        "This meal is a.r.e.n.t. c.o.o.k.e.d. w.i.t.h. d.a.i.r.y.",
        "This meal c.o.n.t.a.i.n.s. n.o. d.a.i.r.y.",
        "This meal d.o.e.s. n.o.t. c.o.n.t.a.i.n. d.a.i.r.y.",
        "This meal h.a.s. n.o.t. g.o.t. a.n.y. d.a.i.r.y.",
        "This meal is f.r.e.e. o.f. d.a.i.r.y.",
        "This meal is f.r.e.e. f.r.o.m. a.l.l. d.a.i.r.y.",
        "This meal is w.i.t.h.o.u.t. a.n.y. d.a.i.r.y.",
        "**n.o.** **d.a.i.r.y.**",
        "_m.i.l.k._ _f.r.e.e._",
        "This meal is **n.o.t.** **m.a.d.e.** **w.i.t.h.** **d.a.i.r.y.**",
        "This meal is n.o.t . m.a.d.e w.i.t.h d.a.i.r.y.",
        "_Milk_._Free_.",
        "**No.****Dairy**.",
    ],
)
def test_budget_dotted_dairy_aliases_return_the_exact_template(claim: str) -> None:
    _assert_budget_claim_rejected(claim)


@pytest.mark.parametrize("punctuation", list(".,;:!?"))
@pytest.mark.parametrize("whitespace", [" ", "\n", "\t"])
@pytest.mark.parametrize(
    ("lead", "claim"),
    [
        ("No", "This meal contains no dairy."),
        ("Milk", "This meal is milk-free."),
        ("No", "This meal does not contain dairy."),
        ("Milk", "This meal is not made with dairy."),
        ("Delivery is free", "This meal is free from all dairy."),
    ],
)
def test_budget_later_dairy_claims_return_the_exact_template(
    lead: str, claim: str, punctuation: str, whitespace: str
) -> None:
    _assert_budget_claim_rejected(f"{lead}{punctuation}{whitespace}{claim}")


@pytest.mark.parametrize(
    "claim",
    [
        "The order was. Placed.",
        "Your plan is. Now updated.",
        "This meal is gluten.free.",
        "No. This meal contains no dairy.",
        "Milk. _milk-free_.",
        "**No.** This meal contains no dairy.",
        "**Milk.** _milk-free_.",
        "**No** . This meal contains no dairy.",
        "_Milk_ : _milk-free_.",
        "This meal contains no dairy. Milk is listed as an ingredient.",
        "This meal is milk-free. Delivery is available.",
        "This meal doesn't include dairy. Milk is listed.",
        "Chicken tacos don't contain dairy. Milk is listed.",
        "This meal hasn't got dairy butter. Milk is listed.",
        "Chicken tacos haven't got dairy butter. Milk is listed.",
        "This meal isn't made with dairy butter. Milk is listed.",
        "Chicken tacos aren't cooked from dairy butter. Milk is listed.",
    ],
)
def test_budget_formatted_boundaries_keep_forbidden_claims(claim: str) -> None:
    _assert_budget_claim_rejected(claim)
