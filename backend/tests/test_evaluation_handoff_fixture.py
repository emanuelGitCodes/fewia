from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError, ResourceClosedError

from app.evaluation_handoff_fixture import (
    FakeUncertainHandoffProvider,
    HandoffFixture,
    fixture,
)
from app.evaluation_plan_inputs import fixture_plan
from app.handoff_models import ShoppingHandoff
from app.models import User
from app.providers.instacart import InstacartUncertain
from app.services.shopping_payload import build_shopping_payload

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
BEAN_TOTAL_CENTS = 1703
NOTICE = (
    "Estimated from the demo price catalog. Instacart prices, availability, "
    "taxes, delivery fees, and tips are not verified."
)


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _m01_inputs() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        row = _mapping(item, "scenario")
        if row.get("id") == "M01":
            return dict(_mapping(row["inputs"], "inputs"))
    raise AssertionError("M01 is missing")


def _accepted_inputs() -> dict[str, object]:
    payload = _m01_inputs()
    payload["plan_accepted"] = True
    return payload


def _table_names(handoff: HandoffFixture) -> set[str]:
    bind = handoff.factory.kw["bind"]
    assert bind is not None
    return set(inspect(bind).get_table_names())


def test_accepted_bean_plan_total_is_1703() -> None:
    inputs = _accepted_inputs()
    with fixture(inputs) as handoff:
        assert handoff.user_id == 1
        assert handoff.clock == datetime.fromisoformat("2026-09-06T16:00:00+00:00")
        assert handoff.plan.accepted is True
        assert handoff.plan.total_cents == BEAN_TOTAL_CENTS
        assert handoff.plan.notice == NOTICE
        assert len(handoff.plan.lines) == 7
        assert handoff.payload == build_shopping_payload(handoff.plan)
        with handoff.factory.begin() as session:
            owner = session.get(User, 1)
            assert owner is not None
            assert owner.display_name == "Owner"


def test_wrong_inputs_total_is_ignored() -> None:
    inputs = _accepted_inputs()
    inputs["total_cents"] = 1
    inputs["gold"] = {"total_cents": 1}
    planned = fixture_plan(inputs)
    with fixture(inputs) as handoff:
        assert planned.total_cents == BEAN_TOTAL_CENTS
        assert handoff.plan.total_cents == BEAN_TOTAL_CENTS
        assert handoff.plan.accepted is True
        assert handoff.payload == build_shopping_payload(planned)


def test_overbudget_rejected_and_no_consent_fail() -> None:
    overbudget = _accepted_inputs()
    overbudget["plan_cap_cents"] = 100
    with pytest.raises(ValueError, match="plan MUST be accepted"):
        with fixture(overbudget):
            raise AssertionError("overbudget opened")

    rejected = _accepted_inputs()
    rejected["monthly_limit_cents"] = 0
    with pytest.raises(ValueError, match="plan MUST be accepted"):
        with fixture(rejected):
            raise AssertionError("rejected opened")

    denied = _accepted_inputs()
    denied["plan_accepted"] = False
    with pytest.raises(ValueError, match="plan_accepted MUST be True"):
        with fixture(denied):
            raise AssertionError("false consent opened")

    missing = _m01_inputs()
    with pytest.raises(ValueError, match="plan_accepted MUST be True"):
        with fixture(missing):
            raise AssertionError("missing consent opened")


@pytest.mark.parametrize("user_id", [0, -1, 1.0, "1", True, None])
def test_invalid_user_fails(user_id: object) -> None:
    inputs = _accepted_inputs()
    inputs["user_id"] = user_id
    with pytest.raises(ValueError, match="user_id MUST be a positive integer"):
        with fixture(inputs):
            raise AssertionError("invalid user opened")


def test_foreign_key_and_isolation() -> None:
    with fixture(_accepted_inputs()) as first:
        assert _table_names(first) == {"users", "shopping_handoffs"}
        with pytest.raises(IntegrityError):
            with first.factory.begin() as session:
                session.add(
                    ShoppingHandoff(
                        user_id=2,
                        request_hash="orphan",
                        request_payload={"k": "v"},
                    )
                )
        other_inputs = _accepted_inputs()
        other_inputs["user_id"] = 2
        with fixture(other_inputs) as second:
            assert first.factory.kw["bind"] is not second.factory.kw["bind"]
            assert _table_names(second) == {"users", "shopping_handoffs"}
            with second.factory.begin() as session:
                session.add(
                    ShoppingHandoff(
                        user_id=2,
                        request_hash="ok",
                        request_payload=dict(second.payload),
                    )
                )
            with first.factory.begin() as session:
                assert session.get(User, 2) is None
                assert session.scalars(select(ShoppingHandoff)).all() == []
            with second.factory.begin() as session:
                assert session.get(User, 1) is None
                stored = session.scalars(select(ShoppingHandoff)).all()
                assert len(stored) == 1
                assert stored[0].user_id == 2


def test_fake_failure_counter() -> None:
    provider = FakeUncertainHandoffProvider()
    raw = {"line_items": ["secret-payload"]}
    with pytest.raises(InstacartUncertain):
        provider.create_link(raw)
    with pytest.raises(InstacartUncertain):
        provider.create_link(raw)
    assert provider.calls == 2
    stored = vars(provider)
    assert raw not in stored.values()
    assert "secret-payload" not in repr(stored)
    assert list(stored) == ["calls"]


def test_cleanup() -> None:
    with fixture(_accepted_inputs()) as handoff:
        factory = handoff.factory
        assert _table_names(handoff) == {"users", "shopping_handoffs"}
    with pytest.raises((OperationalError, ResourceClosedError)):
        with factory() as session:
            session.get(User, 1)

    with pytest.raises(RuntimeError, match="forced"):
        with fixture(_accepted_inputs()) as handoff:
            factory = handoff.factory
            raise RuntimeError("forced")
    with pytest.raises((OperationalError, ResourceClosedError)):
        with factory() as session:
            session.get(User, 1)
