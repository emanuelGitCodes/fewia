from dataclasses import FrozenInstanceError, asdict
from datetime import date
from decimal import ROUND_UP, Decimal, localcontext

import pytest

from app.providers.plaid_contract import (
    InvalidPlaidResponse,
    SyncPage,
    TransactionData,
    parse_sync_page,
)


def transaction(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "transaction_id": "txn-1",
        "account_id": "acct-1",
        "amount": "12.34",
        "iso_currency_code": "USD",
        "date": "2026-09-06",
        "pending": False,
        "pending_transaction_id": None,
        "personal_finance_category": {
            "primary": "FOOD_AND_DRINK",
            "detailed": "FOOD_AND_DRINK_GROCERIES",
        },
        "merchant_name": "SECRET_MERCHANT_MARKER",
        "raw_response": "SECRET_RAW_MARKER",
    }
    value.update(overrides)
    return value


def sync_payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "added": [transaction()],
        "modified": [
            transaction(
                transaction_id="txn-2",
                amount=-5,
                pending=True,
                pending_transaction_id="txn-1",
                personal_finance_category={"detailed": "OTHER_FOOD"},
            )
        ],
        "removed": [{"transaction_id": "txn-removed", "extra": "ignored"}],
        "next_cursor": "cursor-2",
        "has_more": False,
    }
    value.update(overrides)
    return value


def test_parse_normalizes_rows_refunds_replacements_and_removals() -> None:
    page = parse_sync_page(sync_payload())

    assert isinstance(page, SyncPage)
    assert page.added[0] == TransactionData(
        transaction_id="txn-1",
        account_id="acct-1",
        amount_cents=1234,
        currency="USD",
        transaction_date=date(2026, 9, 6),
        pending=False,
        pending_transaction_id=None,
        is_grocery=True,
        classification_version="plaid-pfc-v1",
    )
    assert page.modified[0].amount_cents == -500
    assert page.modified[0].pending_transaction_id == "txn-1"
    assert page.modified[0].is_grocery is False
    assert page.removed_ids == ("txn-removed",)
    assert page.next_cursor == "cursor-2"
    assert page.has_more is False


def test_dtos_are_frozen_and_do_not_store_raw_fields() -> None:
    row = parse_sync_page(sync_payload()).added[0]
    with pytest.raises(FrozenInstanceError):
        row.amount_cents = 1  # type: ignore[misc]
    assert set(asdict(row)) == {
        "transaction_id",
        "account_id",
        "amount_cents",
        "currency",
        "transaction_date",
        "pending",
        "pending_transaction_id",
        "is_grocery",
        "classification_version",
    }
    assert "merchant_name" not in asdict(row)
    assert "raw_response" not in asdict(row)


@pytest.mark.parametrize(
    "amount",
    [
        True,
        False,
        "NaN",
        "Infinity",
        Decimal("-Infinity"),
        float("nan"),
        float("inf"),
        "1.001",
        Decimal("0.0001"),
        "1e-1000100",
        "-1e-1000100",
        "92233720368547758.08",
        "-92233720368547758.09",
    ],
)
def test_invalid_amounts_are_rejected_without_input_leaks(amount: object) -> None:
    marker = "SECRET_INPUT_MARKER"
    payload = sync_payload(added=[transaction(amount=amount, transaction_id=marker)])

    with pytest.raises(InvalidPlaidResponse) as raised:
        parse_sync_page(payload)
    assert str(raised.value) == "Invalid Plaid sync response"
    assert marker not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize(
    ("amount", "expected_cents"),
    [
        (Decimal("0E-1000100"), 0),
        ("-0.00", 0),
        ("1.2300", 123),
        (Decimal("100.000"), 10000),
        ("92233720368547758.07", 2**63 - 1),
        ("-92233720368547758.08", -(2**63)),
    ],
)
def test_exact_amounts_normalize_at_signed64_boundaries(
    amount: object, expected_cents: int
) -> None:
    page = parse_sync_page(sync_payload(added=[transaction(amount=amount)]))
    assert page.added[0].amount_cents == expected_cents


def test_amount_normalization_ignores_decimal_context() -> None:
    with localcontext() as context:
        context.prec = 1
        context.Emin = -1
        context.Emax = 1
        context.rounding = ROUND_UP
        page = parse_sync_page(sync_payload(added=[transaction(amount="123.4500")]))
    assert page.added[0].amount_cents == 12345


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iso_currency_code", "CAD"),
        ("date", "2026-02-30"),
        ("date", "20260906"),
        ("date", 20260906),
        ("transaction_id", ""),
        ("account_id", None),
        ("pending", 1),
        ("pending_transaction_id", ""),
        ("pending_transaction_id", 1),
    ],
)
def test_malformed_transaction_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(InvalidPlaidResponse):
        parse_sync_page(sync_payload(added=[transaction(**{field: value})]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("added", ()),
        ("modified", {}),
        ("removed", None),
        ("next_cursor", ""),
        ("has_more", 1),
        ("removed", [{"transaction_id": ""}]),
        ("removed", [{}]),
    ],
)
def test_sync_fields_are_strictly_validated(field: str, value: object) -> None:
    with pytest.raises(InvalidPlaidResponse):
        parse_sync_page(sync_payload(**{field: value}))


def test_missing_categories_are_not_grocery() -> None:
    page = parse_sync_page(
        sync_payload(
            added=[transaction(personal_finance_category=None)],
            modified=[transaction(personal_finance_category={})],
        )
    )
    assert page.added[0].is_grocery is False
    assert page.modified[0].is_grocery is False
