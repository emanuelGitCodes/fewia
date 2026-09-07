from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite
from typing import NoReturn, cast

_MIN_CENTS, _MAX_CENTS = -(2**63), 2**63 - 1


class InvalidPlaidResponse(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TransactionData:
    transaction_id: str
    account_id: str
    amount_cents: int
    currency: str
    transaction_date: date
    pending: bool
    pending_transaction_id: str | None
    is_grocery: bool
    classification_version: str


@dataclass(frozen=True, slots=True)
class SyncPage:
    added: tuple[TransactionData, ...]
    modified: tuple[TransactionData, ...]
    removed_ids: tuple[str, ...]
    next_cursor: str
    has_more: bool


def _invalid() -> NoReturn:
    raise InvalidPlaidResponse("Invalid Plaid sync response") from None


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid()
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _invalid()
    return cast(list[object], value)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _transaction_date(value: object) -> date:
    if not isinstance(value, str) or len(value) != 10 or value[4::3] != "--":
        _invalid()
    return date.fromisoformat(value)


def _amount_cents(value: object) -> int:
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, str) or type(value) is int:
        amount = Decimal(value)
    elif type(value) is float:
        if not isfinite(value):
            _invalid()
        amount = Decimal(str(value))
    else:
        _invalid()
    if not amount.is_finite():
        _invalid()
    sign, digits, exponent = amount.as_tuple()
    if not isinstance(exponent, int):
        _invalid()
    if not any(digits):
        return 0
    first_nonzero = next(index for index, digit in enumerate(digits) if digit)
    digits = digits[first_nonzero:]
    if exponent < -2:
        decimal_places = -2 - exponent
        if decimal_places > len(digits) or any(
            digit for digit in digits[-decimal_places:]
        ):
            _invalid()
        cents_digits = digits[:-decimal_places]
    else:
        appended_zeros = exponent + 2
        if appended_zeros > 19 - len(digits):
            _invalid()
        cents_digits = digits + (0,) * appended_zeros
    if len(cents_digits) > 19:
        _invalid()
    cents = int("".join(str(digit) for digit in cents_digits))
    if cents > (_MAX_CENTS if sign == 0 else -_MIN_CENTS):
        _invalid()
    return -cents if sign else cents


def _transaction(value: object) -> TransactionData:
    record = _object(value)
    currency = _string(record["iso_currency_code"])
    if currency != "USD":
        _invalid()
    pending_transaction_id = record.get("pending_transaction_id")
    if pending_transaction_id is not None:
        pending_transaction_id = _string(pending_transaction_id)
    category = record.get("personal_finance_category")
    is_grocery = isinstance(category, Mapping) and (
        category.get("detailed") == "FOOD_AND_DRINK_GROCERIES"
    )
    return TransactionData(
        transaction_id=_string(record["transaction_id"]),
        account_id=_string(record["account_id"]),
        amount_cents=_amount_cents(record["amount"]),
        currency=currency,
        transaction_date=_transaction_date(record["date"]),
        pending=_boolean(record["pending"]),
        pending_transaction_id=pending_transaction_id,
        is_grocery=is_grocery,
        classification_version="plaid-pfc-v1",
    )


def parse_sync_page(payload: object) -> SyncPage:
    try:
        response = _object(payload)
        added = tuple(_transaction(item) for item in _list(response["added"]))
        modified = tuple(_transaction(item) for item in _list(response["modified"]))
        removed_ids = tuple(
            _string(_object(item)["transaction_id"])
            for item in _list(response["removed"])
        )
        next_cursor = _string(response["next_cursor"])
        has_more = _boolean(response["has_more"])
        return SyncPage(added, modified, removed_ids, next_cursor, has_more)
    except Exception:
        pass
    _invalid()
