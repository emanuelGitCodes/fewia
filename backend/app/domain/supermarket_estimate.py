from dataclasses import dataclass

SPOONACULAR_COST_NOTICE = (
    "Average supermarket estimate from Spoonacular. Not a store price. "
    "Instacart prices, availability, taxes, delivery fees, and tips are not verified."
)

_TOTAL_CENTS_ERROR = "total_cents MUST be a non-negative integer or None."
_LINE_CENTS_ERROR = "cents MUST be a non-negative integer or None."
_NOTICE_ERROR = "notice MUST equal SPOONACULAR_COST_NOTICE."


def _require_total_cents(value: int | None) -> None:
    if value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError(_TOTAL_CENTS_ERROR)


def _require_line_cents(value: int | None) -> None:
    if value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError(_LINE_CENTS_ERROR)


def _require_notice(value: str) -> None:
    if value != SPOONACULAR_COST_NOTICE:
        raise ValueError(_NOTICE_ERROR)


@dataclass(frozen=True, slots=True)
class SupermarketLine:
    ingredient_id: str
    cents: int | None

    def __post_init__(self) -> None:
        _require_line_cents(self.cents)


@dataclass(frozen=True, slots=True)
class SupermarketEstimate:
    total_cents: int | None
    notice: str
    lines: tuple[SupermarketLine, ...] = ()

    def __post_init__(self) -> None:
        _require_total_cents(self.total_cents)
        _require_notice(self.notice)
