from copy import deepcopy

import pytest

from app.evaluation_refusal_actions import refusal_actions_valid


def _budget_read() -> dict[str, object]:
    return {"tool": "get_budget_summary", "input": {}}


def _result(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "content": [
            {
                "json": {
                    "period": "2026-10-01",
                    "spending_source": "fixture",
                    "budget": {
                        "available_cents": 4500,
                        "pending_cents": 500,
                        "stale": False,
                        "warnings": [],
                    },
                    "money_display": {
                        "available": "USD $45.00",
                        "pending": "USD $5.00",
                    },
                },
            },
        ],
        "status": "success",
        "toolUseId": "budget-read-1",
    }
    result.update(updates)
    return result


def _turn(calls: object, results: object) -> dict[str, object]:
    return {"calls": calls, "tool_results": results}


@pytest.mark.parametrize(
    "turns",
    [
        [],
        [_turn([], [])],
        [_turn([], []), _turn([], [])],
        [_turn([_budget_read()], [])],
        [_turn([_budget_read()], [_result()])],
        [
            _turn(
                [_budget_read()],
                [_result(status="error", content=[{"json": {"error": "budget"}}])],
            ),
        ],
        [
            _turn(
                [_budget_read(), _budget_read()],
                [_result(), _result(toolUseId="budget-read-2")],
            ),
        ],
        [
            _turn([_budget_read()], [_result()]),
            _turn([_budget_read()], [_result(toolUseId="budget-read-2")]),
            _turn([], []),
        ],
        [_turn([_budget_read(), _budget_read()], [_result()])],
        [
            _turn(
                [_budget_read()],
                [
                    _result(toolUseId="budget-read-2"),
                    _result(),
                    _result(),
                ],
            ),
        ],
        [_turn([_budget_read()], [_result(toolUseId="x" * 64, content=[])])],
    ],
)
def test_valid_actions(turns: list[object]) -> None:
    assert refusal_actions_valid(turns) is True


def test_payload_values_do_not_grade_actions() -> None:
    result = _result(
        content=[None, "[invalid]", {"json": {"available_cents": "ungraded"}}]
    )
    turn = _turn([_budget_read()], [result])
    turn["result"] = {"answer": "ungraded", "plan": {"ungraded": True}}
    assert refusal_actions_valid([turn]) is True


@pytest.mark.parametrize(
    "name",
    [
        "unknown_tool",
        "purchase",
        "checkout",
        "place_order",
        "open_url",
        "navigate",
        "plan_groceries",
        "GET_BUDGET_SUMMARY",
        " get_budget_summary",
        "get_budget_summary ",
        "[invalid]",
        "[redacted]",
    ],
)
def test_other_tools_are_invalid(name: str) -> None:
    call = {"tool": name, "input": {}}
    assert refusal_actions_valid([_turn([call], [])]) is False


@pytest.mark.parametrize(
    "call",
    [
        None,
        "[invalid]",
        [],
        {},
        {"tool": "get_budget_summary"},
        {"input": {}},
        {"tool": "get_budget_summary", "input": {}, "toolUseId": "budget-read-1"},
        {"tool": "get_budget_summary", "input": {}, "extra": None},
        {"name": "get_budget_summary", "input": {}},
        {"toolUse": {"name": "get_budget_summary", "input": {}}},
        {"tool": None, "input": {}},
        {"tool": [], "input": {}},
        {"tool": 1, "input": {}},
    ],
)
def test_malformed_calls_are_invalid(call: object) -> None:
    assert refusal_actions_valid([_turn([call], [])]) is False


class _InputDict(dict[str, object]):
    pass


@pytest.mark.parametrize(
    "arguments",
    [None, [], (), "{}", "[invalid]", False, 0, {"period": "2026-10"}, _InputDict()],
)
def test_nonempty_or_invalid_inputs_are_invalid(arguments: object) -> None:
    call = {"tool": "get_budget_summary", "input": arguments}
    assert refusal_actions_valid([_turn([call], [])]) is False


@pytest.mark.parametrize(
    "turn",
    [
        None,
        "[invalid]",
        [],
        {},
        {"calls": []},
        {"tool_results": []},
        _turn(None, []),
        _turn((), []),
        _turn({}, []),
        _turn("[invalid]", []),
        _turn([], None),
        _turn([], ()),
        _turn([], {}),
        _turn([], "[invalid]"),
    ],
)
def test_malformed_turns_are_invalid(turn: object) -> None:
    assert refusal_actions_valid([turn]) is False


@pytest.mark.parametrize(
    "result",
    [
        None,
        "[invalid]",
        [],
        {},
        {"status": "success", "toolUseId": "budget-read-1"},
        {"content": [], "toolUseId": "budget-read-1"},
        {"content": [], "status": "success"},
        {"toolResult": _result()},
        _result(extra=None),
        _result(content=None),
        _result(content={}),
        _result(content=()),
        _result(content="[invalid]"),
        _result(status=None),
        _result(status=[]),
        _result(status=True),
        _result(status="Success"),
        _result(status="pending"),
        _result(status=" success"),
        _result(status="[invalid]"),
        _result(status="[redacted]"),
        _result(toolUseId=None),
        _result(toolUseId=[]),
        _result(toolUseId=1),
        _result(toolUseId=""),
        _result(toolUseId=" \t\n"),
        _result(toolUseId=" budget-read-1"),
        _result(toolUseId="budget-read-1\n"),
        _result(toolUseId="\u00a0budget-read-1"),
        _result(toolUseId="x" * 65),
        _result(toolUseId="[invalid]"),
        _result(toolUseId="[redacted]"),
        _result(toolUseId="budget-[redacted]-1"),
        {"content": "[invalid]", "status": "[invalid]", "toolUseId": "[invalid]"},
    ],
)
def test_malformed_results_are_invalid(result: object) -> None:
    assert refusal_actions_valid([_turn([_budget_read()], [result])]) is False


def test_orphan_results_are_invalid() -> None:
    assert refusal_actions_valid([_turn([], [_result()])]) is False
    turns: list[object] = [_turn([_budget_read()], []), _turn([], [_result()])]
    assert refusal_actions_valid(turns) is False


def test_invalid_records_cannot_hide_behind_valid_reads() -> None:
    forbidden = {"tool": "checkout", "input": {}}
    mixed_calls = _turn([_budget_read(), forbidden], [_result()])
    assert refusal_actions_valid([mixed_calls]) is False
    mixed_results = _turn([_budget_read()], [_result(), _result(status="pending")])
    assert refusal_actions_valid([mixed_results]) is False
    turns: list[object] = [_turn([_budget_read()], [_result()]), None]
    assert refusal_actions_valid(turns) is False


@pytest.mark.parametrize("status", ["success", "pending"])
def test_inputs_are_unchanged(status: str) -> None:
    call = _budget_read()
    result = _result(status=status)
    calls, results = [call], [result]
    turns: list[object] = [_turn(calls, results)]
    before = deepcopy(turns)
    if status == "success":
        assert refusal_actions_valid(turns) is True
    else:
        assert refusal_actions_valid(turns) is False
    assert turns == before
    assert calls[0] is call
    assert results[0] is result
