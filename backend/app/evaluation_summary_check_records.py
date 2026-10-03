from __future__ import annotations

import re
from typing import cast

_CHECK_NAME = re.compile(r"(?:[A-Z][0-9]{2}[a-z]?\.)?[a-z][a-z0-9_]{0,63}")
_CASE_ID = re.compile(r"[A-Z][0-9]{2}")
_ASSESSMENTS = frozenset({"tools", "plan", "outcome", "claims", "fixture"})
_ERROR = "invalid summary check record"


def _check_name(value: object) -> str:
    if type(value) is not str:
        raise ValueError(_ERROR)
    if len(value) > 69 or _CHECK_NAME.fullmatch(value) is None:
        raise ValueError(_ERROR)
    return value


def validate_checks(value: object) -> dict[str, bool]:
    if type(value) is not dict:
        raise ValueError(_ERROR)
    checks: dict[str, bool] = {}
    for name, passed in cast(dict[object, object], value).items():
        safe_name = _check_name(name)
        if type(passed) is not bool:
            raise ValueError(_ERROR)
        checks[safe_name] = passed
    return checks


def failure_record(
    case_id: str, repeat: int, assessment: str, checks: list[str]
) -> dict[str, object]:
    if type(case_id) is not str or _CASE_ID.fullmatch(case_id) is None:
        raise ValueError(_ERROR)
    if type(repeat) is not int or repeat <= 0:
        raise ValueError(_ERROR)
    if type(assessment) is not str or assessment not in _ASSESSMENTS:
        raise ValueError(_ERROR)
    if type(checks) is not list:
        raise ValueError(_ERROR)
    safe_checks: list[str] = []
    seen: set[str] = set()
    for name in checks:
        safe_name = _check_name(name)
        if safe_name in seen:
            raise ValueError(_ERROR)
        seen.add(safe_name)
        safe_checks.append(safe_name)
    return {
        "case_id": case_id,
        "repeat": repeat,
        "assessment": assessment,
        "checks": safe_checks,
    }
