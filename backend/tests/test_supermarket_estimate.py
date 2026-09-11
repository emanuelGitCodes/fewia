from dataclasses import FrozenInstanceError

import pytest

from app.domain.supermarket_estimate import (
    SPOONACULAR_COST_NOTICE,
    SupermarketEstimate,
)


def estimate(total_cents: int | None = 1299) -> SupermarketEstimate:
    return SupermarketEstimate(
        total_cents=total_cents,
        notice=SPOONACULAR_COST_NOTICE,
    )


def test_constructs_integer_cent_estimate() -> None:
    result = estimate(0)
    assert result.total_cents == 0
    assert result.notice == SPOONACULAR_COST_NOTICE


def test_none_total_is_valid() -> None:
    result = estimate(None)
    assert result.total_cents is None
    assert result.notice == SPOONACULAR_COST_NOTICE


def test_notice_matches_spoonacular_export() -> None:
    assert SPOONACULAR_COST_NOTICE == (
        "Average supermarket estimate from Spoonacular. Not a store price. "
        "Instacart prices, availability, taxes, delivery fees, and tips "
        "are not verified."
    )


def test_rejects_negative_total_cents() -> None:
    with pytest.raises(
        ValueError, match="total_cents MUST be a non-negative integer or None"
    ) as caught:
        estimate(-1)
    assert "-1" not in str(caught.value)


def test_rejects_mismatched_notice() -> None:
    with pytest.raises(
        ValueError, match="notice MUST equal SPOONACULAR_COST_NOTICE"
    ) as caught:
        SupermarketEstimate(total_cents=100, notice="store price")
    assert "store price" not in str(caught.value)


def test_supermarket_estimate_is_frozen() -> None:
    result = estimate()
    with pytest.raises(FrozenInstanceError):
        result.total_cents = 1  # type: ignore[misc]
