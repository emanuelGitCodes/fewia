import math
import re
from typing import NoReturn, cast

INVALID = "evaluation report is invalid"

_REVISION = re.compile(r"^[0-9a-f]{40}$")
_LABEL = re.compile(r"^[A-Za-z0-9._: /\-]{1,256}$")


def _reject() -> NoReturn:
    raise ValueError(INVALID)


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _reject()
    typed = cast(dict[object, object], value)
    for key in typed:
        if type(key) is not str:
            _reject()
    return {str(key): item for key, item in typed.items()}


def count(value: object) -> str:
    if type(value) is not int or value < 0:
        _reject()
    return str(value)


def optional_count(value: object) -> str:
    if value is None:
        return "unknown"
    return count(value)


def seconds(value: object) -> str:
    if value is None:
        return "unknown"
    if type(value) is bool:
        _reject()
    amount: float
    if type(value) is int:
        try:
            amount = float(value)
        except OverflowError:
            raise ValueError(INVALID) from None
    elif type(value) is float:
        amount = value
    else:
        _reject()
    if not math.isfinite(amount) or amount < 0.0:
        _reject()
    if amount == 0.0:
        amount = 0.0
    return f"{amount:.3f} s"


def revision(value: object) -> str:
    if type(value) is not str:
        _reject()
    if _REVISION.fullmatch(value) is None:
        _reject()
    return value


def label(value: object) -> str:
    if value is None:
        return "not recorded"
    if type(value) is not str:
        _reject()
    text = value.strip()
    if text != value or _LABEL.fullmatch(text) is None:
        _reject()
    return f"`{text}`"


def group(value: object, keys: tuple[str, ...]) -> dict[str, str]:
    mapped = _as_map(value)
    result: dict[str, str] = {}
    for key in keys:
        if key not in mapped:
            _reject()
        result[key] = count(mapped[key])
    return result
