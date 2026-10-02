import json
from typing import Any

_MAX_CHARS = 256
_ANSWERS = {
    "secrets": (
        "I cannot provide credentials or raw bank records. "
        "I can help plan meals using the budget summary."
    ),
    "purchase": (
        "I cannot buy items or place orders. I can help prepare a grocery plan."
    ),
    "external_url": (
        "I cannot open external links or place orders. "
        "I can help prepare a grocery plan."
    ),
}


def _one_pair(pairs: list[tuple[Any, Any]]) -> dict[str, object]:
    if len(pairs) != 1:
        raise ValueError("object")
    key, value = pairs[0]
    if type(key) is not str:
        raise ValueError("key")
    return {key: value}


def _reject_constant(_value: str) -> object:
    raise ValueError("constant")


def parse_refusal(text: object) -> str | None:
    if not isinstance(text, str) or len(text) > _MAX_CHARS:
        return None
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_one_pair,
            parse_constant=_reject_constant,
        )
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    reason = payload.get("refusal")
    if not isinstance(reason, str):
        return None
    return _ANSWERS.get(reason)
