from __future__ import annotations

from typing import cast


def as_map(value: object) -> dict[str, object]:
    if type(value) is not dict:
        return {}
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return {}
    return cast(dict[str, object], mapping.copy())


def typed_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        left_map = cast(dict[object, object], left)
        right_map = cast(dict[object, object], right)
        if len(left_map) != len(right_map):
            return False
        unmatched = list(right_map.items())
        for left_key, left_value in left_map.items():
            for index, (right_key, right_value) in enumerate(unmatched):
                if typed_equal(left_key, right_key) and typed_equal(
                    left_value, right_value
                ):
                    unmatched.pop(index)
                    break
            else:
                return False
        return True
    if isinstance(left, list):
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            typed_equal(left_item, right_item)
            for left_item, right_item in zip(left_list, right_list, strict=True)
        )
    return bool(left == right)


def valid_public_result(value: object) -> bool:
    if type(value) is not dict:
        return False
    result = cast(dict[object, object], value)
    if not {"status", "answer", "request", "plan", "budget"}.issubset(result):
        return False
    status = result["status"]
    if not isinstance(status, str) or status not in (
        "planned",
        "needs_revision",
        "clarification",
        "limit",
        "incomplete",
    ):
        return False
    answer = result["answer"]
    if not isinstance(answer, str) or not 1 <= len(answer) <= 4096:
        return False
    payloads = (result["request"], result["plan"], result["budget"])
    all_null = all(payload is None for payload in payloads)
    if status in ("limit", "incomplete"):
        return all_null
    if all_null:
        return status == "clarification"
    if not all(type(payload) is dict for payload in payloads):
        return False
    plan = cast(dict[object, object], result["plan"])
    if status == "planned":
        return plan.get("accepted") is True
    if status == "needs_revision":
        return plan.get("accepted") is False
    return (
        plan.get("accepted") is False
        and "total_cents" in plan
        and plan["total_cents"] is None
    )
