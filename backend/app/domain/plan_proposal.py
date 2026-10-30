"""Plan proposals: validated catalog-only changes to a saved plan revision."""

from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy.orm import Session

from app.domain.plan_revision import PlanMeal, PlanSnapshot
from app.plan_models import PlanProposal, PlanRevision

INVALID_PROPOSAL_MESSAGE = "The proposed plan change is not valid."
BASE_NOT_FOUND_MESSAGE = "The base plan revision was not found."


class ProposalInvalid(ValueError):
    """Raised with a fixed message when operations cannot produce a valid plan."""


class AddMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add"]
    recipe_id: StrictStr
    servings: StrictInt


class RemoveMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove"]
    recipe_id: StrictStr


class SetServings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_servings"]
    recipe_id: StrictStr
    servings: StrictInt


class SetPantry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_pantry"]
    ingredient_id: StrictStr
    owned: StrictBool


Operation = Annotated[
    AddMeal | RemoveMeal | SetServings | SetPantry, Field(discriminator="op")
]
Operations = Annotated[list[Operation], Field(min_length=1, max_length=6)]
_OPERATIONS_ADAPTER: TypeAdapter[list[Operation]] = TypeAdapter(Operations)


def parse_operations(raw: object) -> list[Operation]:
    try:
        return _OPERATIONS_ADAPTER.validate_python(raw, strict=True)
    except ValidationError:
        raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE) from None


def apply_operations(snapshot: PlanSnapshot, ops: list[Operation]) -> PlanSnapshot:
    meals = [meal.model_copy() for meal in snapshot.meals]
    pantry = list(snapshot.pantry_ingredient_ids)
    for operation in ops:
        if isinstance(operation, SetPantry):
            if operation.owned and operation.ingredient_id not in pantry:
                pantry.append(operation.ingredient_id)
            elif not operation.owned and operation.ingredient_id in pantry:
                pantry.remove(operation.ingredient_id)
            continue
        recipe_ids = [meal.recipe_id for meal in meals]
        index = (
            recipe_ids.index(operation.recipe_id)
            if operation.recipe_id in recipe_ids
            else None
        )
        if isinstance(operation, AddMeal):
            if index is not None:
                raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE)
            try:
                meals.append(
                    PlanMeal(recipe_id=operation.recipe_id, servings=operation.servings)
                )
            except ValidationError:
                raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE) from None
        elif index is None:
            raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE)
        elif isinstance(operation, RemoveMeal):
            del meals[index]
        else:
            try:
                meals[index] = PlanMeal(
                    recipe_id=operation.recipe_id, servings=operation.servings
                )
            except ValidationError:
                raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE) from None
    try:
        return PlanSnapshot(
            meals=meals,
            pantry_ingredient_ids=pantry,
            plan_cap_cents=snapshot.plan_cap_cents,
        )
    except ValidationError:
        raise ProposalInvalid(INVALID_PROPOSAL_MESSAGE) from None


def load_base_snapshot(revision: PlanRevision) -> PlanSnapshot:
    return PlanSnapshot.model_validate(revision.snapshot)


def create_proposal(
    session: Session,
    user_id: int,
    base_plan_revision_id: UUID,
    operations: object,
) -> UUID:
    base = session.get(PlanRevision, base_plan_revision_id)
    if base is None or base.user_id != user_id:
        raise ProposalInvalid(BASE_NOT_FOUND_MESSAGE)
    ops = parse_operations(operations)
    apply_operations(load_base_snapshot(base), ops)
    proposal_id = uuid4()
    session.add(
        PlanProposal(
            id=proposal_id,
            user_id=user_id,
            base_plan_revision_id=base_plan_revision_id,
            operations=cast(
                list[dict[str, object]],
                [op.model_dump(mode="json") for op in ops],
            ),
            status="pending",
        )
    )
    session.flush()
    return proposal_id
