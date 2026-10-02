from datetime import UTC, date, datetime

import pytest

from app.agent.budget_tool import (
    TOOL_NAME,
    budget_summary_answer,
    budget_tool_spec,
    execute_budget_summary,
)
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult

PERIOD = date(2026, 9, 1)
FRESH = BudgetResult(7500, 400, False, ())
ZERO = BudgetResult(0, 0, False, ())
NEGATIVE_PENDING = BudgetResult(2000, -300, True, (STALE_SPENDING_WARNING,))
SENTINEL = "ATTACKER_SECRET_VALUE"


class _AllowedSourceStr(str):
    pass


class _EmptyDictSubclass(dict):
    def __repr__(self) -> str:
        return SENTINEL

    def __str__(self) -> str:
        return SENTINEL


def test_schema_forbids_caller_properties() -> None:
    spec = budget_tool_spec()
    tool = spec["toolSpec"]
    assert isinstance(tool, dict)
    schema = tool["inputSchema"]
    assert isinstance(schema, dict)
    json_schema = schema["json"]
    assert isinstance(json_schema, dict)
    assert tool["name"] == TOOL_NAME
    assert json_schema["type"] == "object"
    assert json_schema["properties"] == {}
    assert json_schema["additionalProperties"] is False


def test_empty_exact_dict_succeeds() -> None:
    result = execute_budget_summary({}, FRESH, PERIOD, spending_source="fixture")

    assert result["period"] == "2026-09-01"
    assert result["spending_source"] == "fixture"
    assert result["budget"] == {
        "available_cents": 7500,
        "pending_cents": 400,
        "stale": False,
        "warnings": [],
    }
    assert result["money_display"] == {
        "available": "USD $75.00",
        "pending": "USD $4.00",
    }


def test_empty_dict_subclass_is_rejected_without_echo() -> None:
    arguments = _EmptyDictSubclass()
    with pytest.raises(ValueError) as error:
        execute_budget_summary(arguments, FRESH, PERIOD, spending_source="fixture")

    message = str(error.value)
    assert message == "arguments are invalid"
    assert SENTINEL not in message


@pytest.mark.parametrize(
    "arguments",
    [
        {"identity": SENTINEL},
        {"source": SENTINEL},
        {"cap": SENTINEL},
        {"spending": SENTINEL},
        {"transaction": SENTINEL},
        {"available_cents": 1},
        [SENTINEL],
        True,
        False,
        None,
        SENTINEL,
        0,
    ],
)
def test_malicious_and_non_dict_arguments_fail_without_echoing_sentinels(
    arguments: object,
) -> None:
    with pytest.raises(ValueError) as error:
        execute_budget_summary(arguments, FRESH, PERIOD, spending_source="fixture")

    message = str(error.value)
    assert message == "arguments are invalid"
    assert SENTINEL not in message


@pytest.mark.parametrize(
    "budget",
    [
        BudgetResult(True, 0, False, ()),  # type: ignore[arg-type]
        BudgetResult(-1, 0, False, ()),
        BudgetResult(1.5, 0, False, ()),  # type: ignore[arg-type]
        BudgetResult(0, True, False, ()),  # type: ignore[arg-type]
        BudgetResult(0, 1.5, False, ()),  # type: ignore[arg-type]
        BudgetResult(0, 0, 1, ()),  # type: ignore[arg-type]
        BudgetResult(0, 0, False, ["warn"]),  # type: ignore[arg-type]
        BudgetResult(0, 0, False, ("ok", 1)),  # type: ignore[arg-type]
        {"available_cents": 0, "pending_cents": 0, "stale": False, "warnings": ()},
        None,
    ],
)
def test_invalid_budget_fields_fail_with_static_value_error(budget: object) -> None:
    with pytest.raises(ValueError) as error:
        execute_budget_summary(
            {},
            budget,  # type: ignore[arg-type]
            PERIOD,
            spending_source="fixture",
        )

    assert str(error.value) == "budget is invalid"
    assert SENTINEL not in str(error.value)
    with pytest.raises(ValueError) as answer_error:
        budget_summary_answer(
            budget,  # type: ignore[arg-type]
            PERIOD,
            spending_source="fixture",
        )
    assert str(answer_error.value) == "budget is invalid"


@pytest.mark.parametrize(
    "period",
    [date(2026, 9, 2), datetime(2026, 9, 1, 0, 0, tzinfo=UTC), "2026-09-01"],
)
def test_invalid_period_fails_with_static_value_error(period: object) -> None:
    with pytest.raises(ValueError) as error:
        execute_budget_summary(
            {},
            FRESH,
            period,  # type: ignore[arg-type]
            spending_source="fixture",
        )

    assert str(error.value) == "period is invalid"
    with pytest.raises(ValueError) as answer_error:
        budget_summary_answer(
            FRESH,
            period,  # type: ignore[arg-type]
            spending_source="fixture",
        )
    assert str(answer_error.value) == "period is invalid"


@pytest.mark.parametrize(
    "spending_source",
    [
        "plaid",
        "MANUAL",
        "",
        True,
        None,
        _AllowedSourceStr("manual"),
        _AllowedSourceStr("fixture"),
        _AllowedSourceStr("plaid_sandbox"),
    ],
)
def test_invalid_spending_source_fails_with_static_value_error(
    spending_source: object,
) -> None:
    with pytest.raises(ValueError) as error:
        execute_budget_summary(
            {},
            FRESH,
            PERIOD,
            spending_source=spending_source,  # type: ignore[arg-type]
        )
    assert str(error.value) == "spending_source is invalid"
    with pytest.raises(ValueError) as answer_error:
        budget_summary_answer(
            FRESH,
            PERIOD,
            spending_source=spending_source,  # type: ignore[arg-type]
        )
    assert str(answer_error.value) == "spending_source is invalid"


def test_usd_formatting_for_zero_positive_and_negative_pending() -> None:
    zero = execute_budget_summary({}, ZERO, PERIOD, spending_source="manual")
    ordinary = execute_budget_summary({}, FRESH, PERIOD, spending_source="fixture")
    negative = execute_budget_summary(
        {}, NEGATIVE_PENDING, PERIOD, spending_source="plaid_sandbox"
    )

    assert zero["money_display"] == {"available": "USD $0.00", "pending": "USD $0.00"}
    assert ordinary["money_display"] == {
        "available": "USD $75.00",
        "pending": "USD $4.00",
    }
    assert negative["money_display"] == {
        "available": "USD $20.00",
        "pending": "USD -$3.00",
    }


def test_stale_warning_is_canonical_and_arbitrary_text_is_dropped() -> None:
    secret = BudgetResult(100, 0, False, (SENTINEL,))
    stale = BudgetResult(100, 0, True, (SENTINEL,))

    fresh_result = execute_budget_summary({}, secret, PERIOD, spending_source="fixture")
    stale_result = execute_budget_summary({}, stale, PERIOD, spending_source="fixture")
    fresh_answer = budget_summary_answer(secret, PERIOD, spending_source="fixture")
    stale_answer = budget_summary_answer(stale, PERIOD, spending_source="fixture")

    fresh_budget = fresh_result["budget"]
    stale_budget = stale_result["budget"]
    assert isinstance(fresh_budget, dict)
    assert isinstance(stale_budget, dict)
    assert fresh_budget["warnings"] == []
    assert stale_budget["warnings"] == [STALE_SPENDING_WARNING]
    assert SENTINEL not in str(fresh_result)
    assert SENTINEL not in str(stale_result)
    assert SENTINEL not in fresh_answer
    assert SENTINEL not in stale_answer
    assert STALE_SPENDING_WARNING not in fresh_answer
    assert stale_answer.endswith(STALE_SPENDING_WARNING)


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("manual", "Your entered budget"),
        ("fixture", "Demo spending"),
        ("plaid_sandbox", "Plaid Sandbox"),
    ],
)
def test_source_labels_and_fixed_reply_wording(source: str, label: str) -> None:
    answer = budget_summary_answer(FRESH, PERIOD, spending_source=source)  # type: ignore[arg-type]

    assert answer == (
        f"Available for this plan: USD $75.00. Pending: USD $4.00. Source: {label}."
    )
    assert "monthly limit" not in answer.lower()


def test_stale_reply_separates_pending_and_includes_canonical_warning() -> None:
    answer = budget_summary_answer(NEGATIVE_PENDING, PERIOD, spending_source="manual")

    assert answer == (
        "Available for this plan: USD $20.00. Pending: USD -$3.00. "
        f"Source: Your entered budget. {STALE_SPENDING_WARNING}"
    )


def test_json_keys_have_no_extra_or_raw_fields() -> None:
    result = execute_budget_summary({}, FRESH, PERIOD, spending_source="fixture")

    budget_payload = result["budget"]
    money_payload = result["money_display"]
    assert isinstance(budget_payload, dict)
    assert isinstance(money_payload, dict)
    assert set(result) == {"period", "spending_source", "budget", "money_display"}
    assert set(budget_payload) == {
        "available_cents",
        "pending_cents",
        "stale",
        "warnings",
    }
    assert set(money_payload) == {"available", "pending"}
    assert "user_id" not in result
    assert "identity" not in result
    assert "transactions" not in result
    assert "posted_cents" not in budget_payload
    assert "monthly_limit_cents" not in result


def test_valid_calls_leave_budget_result_unchanged() -> None:
    budget = BudgetResult(7500, 400, False, (SENTINEL,))
    before = BudgetResult(
        budget.available_cents,
        budget.pending_cents,
        budget.stale,
        budget.warnings,
    )

    execute_budget_summary({}, budget, PERIOD, spending_source="fixture")
    budget_summary_answer(budget, PERIOD, spending_source="fixture")

    assert budget == before
    assert budget.warnings == (SENTINEL,)
