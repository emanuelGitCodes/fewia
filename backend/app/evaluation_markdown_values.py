from re import fullmatch
from typing import cast

_ERROR = "Invalid evaluation report input"


def require(valid: bool) -> None:
    if not valid:
        raise ValueError(_ERROR) from None


def as_map(value: object) -> dict[str, object]:
    require(type(value) is dict)
    return cast(dict[str, object], value)


def text(value: object, pattern: str) -> str:
    require(type(value) is str and fullmatch(pattern, value) is not None)
    return cast(str, value)


def slots(value: object) -> list[dict[str, object]]:
    require(type(value) is list)
    return [as_map(item) for item in cast(list[object], value)]


def pick(source: dict[str, object], fields: str) -> dict[str, object]:
    return {key: source[key] for key in fields.split() if key in source}
