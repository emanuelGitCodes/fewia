from typing import cast


def as_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    typed = cast(dict[object, object], value)
    if any(type(key) is not str for key in typed):
        return None
    return {str(key): item for key, item in typed.items()}


def typed_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        mapped_left = as_map(left)
        mapped_right = as_map(right)
        if mapped_left is None or mapped_right is None:
            return False
        if mapped_left.keys() != mapped_right.keys():
            return False
        return all(
            typed_equal(mapped_left[key], mapped_right[key]) for key in mapped_left
        )
    if type(left) is list and type(right) is list:
        left_items = cast(list[object], left)
        right_items = cast(list[object], right)
        if len(left_items) != len(right_items):
            return False
        return all(
            typed_equal(item, other)
            for item, other in zip(left_items, right_items, strict=True)
        )
    return left == right


def has_value(body: dict[str, object] | None, key: str, expected: object) -> bool:
    return body is not None and key in body and typed_equal(body[key], expected)


def id_lists_equal(body: dict[str, object] | None, key: str, expected: object) -> bool:
    raw = None if body is None or key not in body else body[key]
    if type(raw) is not list or type(expected) is not list:
        return False
    raw_items = cast(list[object], raw)
    expected_items = cast(list[object], expected)
    left = [item for item in raw_items if type(item) is str]
    right = [item for item in expected_items if type(item) is str]
    unique_left = set(left)
    unique_right = set(right)
    return (
        len(left) == len(raw_items) == len(unique_left)
        and len(right) == len(expected_items) == len(unique_right)
        and unique_left == unique_right
    )


def lines_by_id(value: object) -> dict[str, dict[str, object]] | None:
    if type(value) is not list:
        return None
    index: dict[str, dict[str, object]] = {}
    for item in cast(list[object], value):
        body = as_map(item)
        ingredient_id = None if body is None else body.get("ingredient_id")
        if body is None or type(ingredient_id) is not str or ingredient_id in index:
            return None
        index[ingredient_id] = body
    return index


def completed_results(
    turns: object, expected_count: int
) -> list[dict[str, object]] | None:
    if type(expected_count) is not int or expected_count < 1:
        return None
    if type(turns) is not list:
        return None
    items = cast(list[object], turns)
    if len(items) != expected_count:
        return None
    results: list[dict[str, object]] = []
    for item in items:
        body = as_map(item)
        result = None if body is None else as_map(body.get("result"))
        if not body or not result or body.get("status") != "completed":
            return None
        results.append(result)
    return results
