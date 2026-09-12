"""Project job results without a stored root supermarket estimate."""

_SUPERMARKET_ESTIMATE = "supermarket_estimate"


def without_supermarket_estimate(
    result: dict[str, object] | None,
) -> dict[str, object] | None:
    """Return a new mapping that omits the root supermarket_estimate key."""
    if result is None:
        return None
    return {key: value for key, value in result.items() if key != _SUPERMARKET_ESTIMATE}
