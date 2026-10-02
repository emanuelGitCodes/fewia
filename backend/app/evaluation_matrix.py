import json
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from app.domain.catalog import CATALOG_VERSION

MODEL_CASE_IDS = frozenset("F01 F02 F04 F05 X02 X03 X04 A01 A02 A03 A04".split())
REFERENCE_CASE_IDS = frozenset("F01 F02 F05 X04 A01".split())
_GROUPS = {
    f"{prefix}{number:02}": group
    for prefix, group, count in (
        ("B", "budget", 5),
        ("M", "meals", 7),
        ("F", "followup", 5),
        ("X", "missing", 4),
        ("P", "provider", 5),
        ("A", "adversarial", 4),
    )
    for number in range(1, count + 1)
}
_PROVIDER_DRIVERS = {
    "P01": "refresh",
    "P02": "handoff",
    "P03": "protocol",
    "P04": "protocol",
    "P05": "duplicate",
}
_ERROR = "corpus MUST match the finite JSON grocery-eval-v1 matrix contract"


@dataclass(frozen=True)
class EvaluationSlot:
    case_id: str
    repeat: int
    condition: str
    driver: str
    case: dict[str, object]


def _validate_json(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _validate_json(item)
        return
    if type(value) is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError(_ERROR)
            _validate_json(item)
        return
    raise ValueError(_ERROR)


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict or not value:
        raise ValueError(_ERROR)
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(_ERROR)
    return value


def _list(value: object, *, nonempty: bool = False) -> list[object]:
    if type(value) is not list or (nonempty and not value):
        raise ValueError(_ERROR)
    return cast(list[object], value)


def _validate_case(case: dict[str, object]) -> str:
    case_id = _text(case.get("id"))
    if case_id not in _GROUPS or case.get("group") != _GROUPS[case_id]:
        raise ValueError(_ERROR)
    requires_model = case.get("requires_model")
    model_required = case_id in MODEL_CASE_IDS or case_id == "P04"
    if type(requires_model) is not bool or requires_model != model_required:
        raise ValueError(_ERROR)
    _text(case.get("prompt"))
    for value in _list(case.get("messages"), nonempty=True):
        message = _object(value)
        if message.get("role") not in ("user", "assistant"):
            raise ValueError(_ERROR)
        _text(message.get("content"))
    _object(case.get("inputs"))
    expected = _object(case.get("expected"))
    for key, payload in (("domain_calls", "expectation"), ("model_tools", "arguments")):
        for value in _list(expected.get(key)):
            call = _object(value)
            _text(call.get("name"))
            if type(call.get(payload)) is not dict:
                raise ValueError(_ERROR)
    outcomes = _list(expected.get("allowed_outcomes"), nonempty=True)
    for value in outcomes + _list(expected.get("unnecessary_model_tools")):
        _text(value)
    fixture = _object(case.get("fixture_behavior"))
    _text(fixture.get("kind"))
    _text(fixture.get("provider"))
    return case_id


def prepare_matrix(corpus: dict[str, object]) -> list[EvaluationSlot]:
    """Return isolated execution slots. Gold remains scorer input in each case."""
    try:
        _validate_json(corpus)
        frozen = _object(json.loads(json.dumps(corpus, allow_nan=False)))
        version = frozen.get("version")
        catalog_version = frozen.get("catalog_version")
        if version != "grocery-eval-v1" or catalog_version != CATALOG_VERSION:
            raise ValueError(_ERROR)
        if type(frozen.get("repeats")) is not int or frozen["repeats"] != 3:
            raise ValueError(_ERROR)
        cases = [_object(value) for value in _list(frozen.get("scenarios"))]
        ids = [_validate_case(case) for case in cases]
        if len(ids) != len(_GROUPS) or set(ids) != set(_GROUPS):
            raise ValueError(_ERROR)
        slots: list[EvaluationSlot] = []
        for condition, scope in (
            ("", frozenset(ids)),
            ("no_tool", MODEL_CASE_IDS),
            ("deterministic", REFERENCE_CASE_IDS),
        ):
            for case_id, case in zip(ids, cases, strict=True):
                if case_id not in scope:
                    continue
                primary = "deterministic_fixture"
                driver = _PROVIDER_DRIVERS.get(case_id, _GROUPS[case_id])
                if case_id in MODEL_CASE_IDS:
                    primary, driver = "tool_enabled", "model"
                elif case_id in _PROVIDER_DRIVERS:
                    primary = "controlled_fixture"
                if condition:
                    driver = "no_tool" if condition == "no_tool" else "reference"
                slots.extend(
                    EvaluationSlot(
                        case_id, repeat, condition or primary, driver, deepcopy(case)
                    )
                    for repeat in range(1, 4)
                )
        return slots
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValueError(_ERROR) from None
