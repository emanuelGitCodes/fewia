import json
from typing import Final, NoReturn

_MAX_INPUT_LEN: Final[int] = 256
_REFUSAL_KEY: Final[str] = "refusal"
_REFUSAL_TEXT: Final[dict[str, str]] = {
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


def _reject_constant(_token: str) -> NoReturn:
    raise ValueError("nonfinite")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    decoded: dict[str, object] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("duplicate")
        decoded[key] = value
    return decoded


def parse_refusal(text: object) -> str | None:
    """Return fixed public prose for one complete refusal JSON object."""
    if not isinstance(text, str) or not text or len(text) > _MAX_INPUT_LEN:
        return None
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        return None
    if type(payload) is not dict or len(payload) != 1:
        return None
    reason = payload.get(_REFUSAL_KEY)
    if type(reason) is not str:
        return None
    return _REFUSAL_TEXT.get(reason)
