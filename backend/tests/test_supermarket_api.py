"""Tests for the on-demand Spoonacular estimate HTTP route."""

import copy
import json
from collections.abc import Callable, Iterator
from typing import cast
from uuid import uuid4

import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session
from test_evidence_contract import genuine_planning

from app.api import supermarket as supermarket_api
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.spoonacular_catalog import SPOONACULAR_IDS
from app.domain.supermarket_estimate import SPOONACULAR_COST_NOTICE
from app.job_models import Job
from app.main import app
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
from app.providers.spoonacular import SpoonacularUnavailable

SECRET = "sk-test-not-for-models"
REV = "ab" * 32
NUTRITION: dict[str, object] = {
    "energy_kcal": 12,
    "protein_g": 1,
    "carb_g": 2,
    "fat_g": 3,
}
BUDGET: dict[str, object] = {
    "available_cents": 10000,
    "pending_cents": 400,
    "stale": False,
    "warnings": [],
}
CHAT_EXTRA: dict[str, object] = {
    "status": "planned",
    "answer": "Here is an estimated plan.",
    "tool_trace": [{"marker": SECRET}],
    "model_turns": 2,
}


class FakeProvider:
    def __init__(
        self,
        cents: int | None = 10,
        error: type[BaseException] | None = None,
    ) -> None:
        self.cents = cents
        self.error = error
        self.calls: list[tuple[int, int, str]] = []
        self.closed = 0

    def close(self) -> None:
        self.closed += 1

    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        self.calls.append((ingredient_id, amount, unit))
        if self.error is not None:
            raise self.error()
        return self.cents


@pytest.fixture(autouse=True)
def unconfigured_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    app.dependency_overrides[supermarket_api.get_provider_settings] = lambda: (
        GroceryProviderSettings()
    )
    monkeypatch.setattr(supermarket_api, "build_spoonacular", lambda _settings: None)
    try:
        yield
    finally:
        app.dependency_overrides.pop(supermarket_api.get_provider_settings, None)


def estimate_url(job_id: str) -> str:
    return f"/grocery/jobs/{job_id}/supermarket-estimate"


def assert_no_store(response: Response) -> None:
    assert response.headers.get("cache-control") == "no-store"


def assert_secret_absent(response: Response) -> None:
    rendered = json.dumps(response.json()) + str(dict(response.headers))
    assert SECRET not in rendered
    assert "api_key" not in rendered.lower()
    assert ProviderConfigurationError.__name__ not in rendered


def shopping(
    ingredient_id: str,
    quantity: int,
    *,
    from_pantry: bool = False,
    unit: str | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    ingredient = INGREDIENTS[ingredient_id]
    line: dict[str, object] = {
        "ingredient_id": ingredient_id,
        "name": "untrusted-name",
        "unit": ingredient.unit if unit is None else unit,
        "quantity": quantity,
        "packages": 0 if from_pantry else 1,
        "cost_cents": 0 if from_pantry else 1,
        "from_pantry": from_pantry,
    }
    if extra is not None:
        line.update(extra)
    return line


def plan_body(
    *lines: dict[str, object], extra: dict[str, object] | None = None
) -> dict[str, object]:
    plan: dict[str, object] = {
        "lines": list(lines),
        "total_cents": 100,
        "accepted": True,
        "warnings": [],
        "catalog_version": CATALOG_VERSION,
        "notice": SAMPLE_ESTIMATE_NOTICE,
    }
    if extra is not None:
        plan.update(extra)
    return plan


def job_result(
    plan: dict[str, object], extra: dict[str, object] | None = None
) -> dict[str, object]:
    result: dict[str, object] = {
        "request": {"meals": [{"recipe_id": "bean_tacos", "servings": 2}]},
        "plan": plan,
        "budget": copy.deepcopy(BUDGET),
        "nutrition": copy.deepcopy(NUTRITION),
        "spending_source": "fixture",
        "evidence_id": "grocery-evidence",
        "evidence_revision_id": REV,
    }
    if extra is not None:
        result.update(extra)
    return result


def add_job(
    session: Session,
    *,
    result: dict[str, object] | None,
    user_id: int = 1,
    kind: str = "agent",
    status: str = "succeeded",
) -> Job:
    job = Job(
        user_id=user_id,
        kind=kind,
        request_key=str(uuid4()),
        status=status,
        payload={"marker": SECRET},
        result=result,
    )
    session.add(job)
    session.flush()
    return job


def install_providers(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[], FakeProvider],
) -> list[FakeProvider]:
    providers: list[FakeProvider] = []

    def build(settings: GroceryProviderSettings) -> FakeProvider:
        del settings
        provider = factory()
        providers.append(provider)
        return provider

    monkeypatch.setattr(supermarket_api, "build_spoonacular", build)
    return providers


def error_body(status: int, message: str) -> dict[str, object]:
    codes = {404: "not_found", 409: "conflict", 503: "service_unavailable"}
    return {"error": {"code": codes[status], "message": message}}


def test_manual_plan_returns_sum_and_does_not_store(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    planning = genuine_planning()
    plan = cast(dict[str, object], planning["plan"])
    job = add_job(session, result=job_result(plan))
    before = copy.deepcopy(job.result)
    commits: list[str] = []
    monkeypatch.setattr(session, "commit", lambda: commits.append("commit"))

    response = client.get(estimate_url(job.id))
    stored = session.get(Job, job.id)

    assert response.status_code == 200
    assert_no_store(response)
    assert_secret_absent(response)
    body = response.json()
    assert set(body) == {"total_cents", "notice"}
    assert type(body["total_cents"]) is int
    assert body["total_cents"] > 0
    assert body["notice"] == SPOONACULAR_COST_NOTICE
    assert len(providers) == 1
    assert providers[0].closed == 1
    assert providers[0].calls
    assert commits == []
    assert stored is not None
    assert stored.result == before
    assert stored.result is not None
    assert stored.result["nutrition"] == NUTRITION
    assert stored.result["budget"] == BUDGET
    assert stored.result["evidence_id"] == "grocery-evidence"
    assert stored.result["evidence_revision_id"] == REV
    assert "supermarket_estimate" not in stored.result


def test_planned_chat_result_is_supported(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    planning = genuine_planning()
    job = add_job(
        session,
        result=job_result(cast(dict[str, object], planning["plan"]), CHAT_EXTRA),
    )
    before = copy.deepcopy(job.result)

    response = client.get(estimate_url(job.id))
    stored = session.get(Job, job.id)

    assert response.status_code == 200
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json()["notice"] == SPOONACULAR_COST_NOTICE
    assert stored is not None
    assert stored.result == before
    assert stored.result is not None
    assert stored.result["status"] == "planned"
    assert stored.result["nutrition"] == NUTRITION
    assert stored.result["budget"] == BUDGET
    assert len(providers) == 1
    assert providers[0].closed == 1


def test_fresh_provider_and_calls_on_each_request(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    job = add_job(
        session,
        result=job_result(
            plan_body(shopping("eggs", 2), shopping("chicken_breast", 100))
        ),
    )

    first = client.get(estimate_url(job.id))
    second = client.get(estimate_url(job.id))

    assert first.status_code == 200
    assert second.status_code == 200
    assert_no_store(first)
    assert_no_store(second)
    assert len(providers) == 2
    assert providers[0] is not providers[1]
    assert providers[0].calls == [
        (SPOONACULAR_IDS["eggs"], 2, "piece"),
        (SPOONACULAR_IDS["chicken_breast"], 100, "g"),
    ]
    assert providers[1].calls == providers[0].calls
    assert providers[0].closed == 1
    assert providers[1].closed == 1
    assert first.json()["total_cents"] == 20


def test_repeated_recipe_eight_servings_three_times_is_accepted(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    meal = {"recipe_id": "breakfast_burritos", "servings": 8}
    planning = genuine_planning(meals=[meal, meal, meal])
    job = add_job(session, result=job_result(cast(dict[str, object], planning["plan"])))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 200
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json()["notice"] == SPOONACULAR_COST_NOTICE
    assert len(providers) == 1
    assert providers[0].closed == 1
    assert providers[0].calls


def test_quantity_above_repeated_recipe_bound_returns_409(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    meal = {"recipe_id": "breakfast_burritos", "servings": 8}
    planning = genuine_planning(meals=[meal, meal, meal])
    plan = cast(dict[str, object], copy.deepcopy(planning["plan"]))
    lines = cast(list[dict[str, object]], plan["lines"])
    egg_line = next(line for line in lines if line["ingredient_id"] == "eggs")
    quantity = egg_line["quantity"]
    assert type(quantity) is int
    egg_line["quantity"] = quantity + 1
    job = add_job(session, result=job_result(plan))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 409
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(409, supermarket_api._PLAN_UNREADY)
    assert providers == []


def test_pantry_skipped_and_quantities_passed(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    job = add_job(
        session,
        result=job_result(
            plan_body(
                shopping("chicken_breast", 100, from_pantry=True),
                shopping("eggs", 3),
            )
        ),
    )

    response = client.get(estimate_url(job.id))

    assert response.status_code == 200
    assert_no_store(response)
    assert response.json() == {
        "total_cents": 10,
        "notice": SPOONACULAR_COST_NOTICE,
    }
    assert providers[0].calls == [(SPOONACULAR_IDS["eggs"], 3, "piece")]
    assert providers[0].closed == 1


def test_incomplete_estimate_returns_null_total(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, lambda: FakeProvider(cents=None))
    job = add_job(session, result=job_result(plan_body(shopping("eggs", 2))))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 200
    assert_no_store(response)
    assert response.json() == {
        "total_cents": None,
        "notice": SPOONACULAR_COST_NOTICE,
    }
    assert providers[0].closed == 1


def test_provider_failure_returns_null_total_and_closes(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(
        monkeypatch, lambda: FakeProvider(error=SpoonacularUnavailable)
    )
    job = add_job(session, result=job_result(plan_body(shopping("eggs", 2))))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 200
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == {
        "total_cents": None,
        "notice": SPOONACULAR_COST_NOTICE,
    }
    assert len(providers[0].calls) == 1
    assert providers[0].closed == 1


def test_missing_config_returns_503(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    job = add_job(session, result=job_result(plan_body(shopping("eggs", 2))))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 503
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(503, supermarket_api._UNAVAILABLE)


def test_misconfigured_provider_returns_503(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    job = add_job(session, result=job_result(plan_body(shopping("eggs", 2))))

    def boom(settings: GroceryProviderSettings) -> None:
        del settings
        raise ProviderConfigurationError()

    monkeypatch.setattr(supermarket_api, "build_spoonacular", boom)
    response = client.get(estimate_url(job.id))

    assert response.status_code == 503
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(503, supermarket_api._UNAVAILABLE)


@pytest.mark.parametrize(
    ("user_id", "kind", "status_code"),
    [(2, "agent", 404), (1, "sync", 404)],
)
def test_foreign_owner_and_wrong_kind_return_404(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    user_id: int,
    kind: str,
    status_code: int,
) -> None:
    seed_user(1)
    seed_user(2)
    job = add_job(
        session,
        result=job_result(plan_body(shopping("eggs", 2))),
        user_id=user_id,
        kind=kind,
    )

    response = client.get(estimate_url(job.id))

    assert response.status_code == status_code
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(404, supermarket_api._JOB_MISSING)


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_unfinished_job_returns_409(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    status: str,
) -> None:
    seed_user()
    job = add_job(
        session,
        result=job_result(plan_body(shopping("eggs", 2))),
        status=status,
    )

    response = client.get(estimate_url(job.id))

    assert response.status_code == 409
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(409, supermarket_api._PLAN_UNREADY)


def test_missing_job_and_invalid_uuid_return_no_store_404(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    missing = client.get(estimate_url(str(uuid4())))
    invalid = client.get(estimate_url("not-a-uuid"))

    for response in (missing, invalid):
        assert response.status_code == 404
        assert_no_store(response)
        assert_secret_absent(response)
        assert response.json() == error_body(404, supermarket_api._JOB_MISSING)


@pytest.mark.parametrize(
    "plan",
    [
        None,
        [],
        plan_body(),
        plan_body(shopping("eggs", 2), extra={"unexpected": True}),
        plan_body(shopping("eggs", 2, extra={"unexpected": True})),
        plan_body(shopping("eggs", 2, unit="ml")),
        plan_body({**shopping("eggs", 2), "ingredient_id": "unknown_item"}),
        plan_body(shopping("eggs", 0)),
        plan_body(shopping("eggs", 49)),
        plan_body(shopping("eggs", 2), shopping("eggs", 1)),
        plan_body(
            *[shopping(item_id, 1) for item_id in INGREDIENTS],
            shopping("salt", 1),
        ),
        "MISSING_RESULT",
    ],
)
def test_invalid_or_missing_plan_returns_409(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    plan: object,
) -> None:
    seed_user()
    result: dict[str, object] | None
    if plan == "MISSING_RESULT":
        result = None
    elif plan is None:
        result = job_result(plan_body(shopping("eggs", 2)))
        result.pop("plan")
    elif isinstance(plan, dict):
        result = job_result(cast(dict[str, object], plan))
    else:
        result = {
            "plan": plan,
            "budget": copy.deepcopy(BUDGET),
            "nutrition": copy.deepcopy(NUTRITION),
            "evidence_id": "grocery-evidence",
        }
    job = add_job(session, result=result)
    before = copy.deepcopy(job.result)

    response = client.get(estimate_url(job.id))
    stored = session.get(Job, job.id)

    assert response.status_code == 409
    assert_no_store(response)
    assert_secret_absent(response)
    assert response.json() == error_body(409, supermarket_api._PLAN_UNREADY)
    assert stored is not None
    assert stored.result == before


def test_deadline_prevents_later_calls(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    providers = install_providers(monkeypatch, FakeProvider)
    job = add_job(
        session,
        result=job_result(
            plan_body(shopping("eggs", 2), shopping("chicken_breast", 100))
        ),
    )
    times = iter([100.0, 100.0, 120.0])
    monkeypatch.setattr(supermarket_api, "monotonic", lambda: next(times))

    response = client.get(estimate_url(job.id))

    assert response.status_code == 200
    assert_no_store(response)
    assert response.json() == {
        "total_cents": None,
        "notice": SPOONACULAR_COST_NOTICE,
    }
    assert providers[0].calls == [(SPOONACULAR_IDS["eggs"], 2, "piece")]
    assert providers[0].closed == 1
