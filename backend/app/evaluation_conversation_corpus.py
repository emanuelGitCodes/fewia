"""Strict loader for the conversation-eval-v1 corpus.

This suite is separate from the frozen grocery-eval-v1 matrix. It holds data and
validation only; no runner lives here.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.agent.budget_tool import TOOL_NAME as BUDGET_TOOL_NAME
from app.agent.catalog_tool import TOOL_NAME as CATALOG_TOOL_NAME
from app.agent.ingredient_tool import INGREDIENT_TOOL
from app.agent.plan_tools import GET_MEAL_TOOL, GET_PLAN_TOOL
from app.agent.planning_tool import TOOL_NAME as PLANNER_TOOL_NAME
from app.agent.price_tool import PRICE_TOOL
from app.agent.proposal_tool import PROPOSAL_TOOL
from app.agent.substitute_tool import SUBSTITUTE_TOOL
from app.domain.catalog import CATALOG_VERSION
from app.domain.plan_revision import PlanSnapshot

CORPUS_ERROR = "corpus MUST match the conversation-eval-v1 contract"
# The tools run_chat registers when a plan revision and a propose callable exist.
TOOL_NAMES = frozenset(
    {
        PLANNER_TOOL_NAME,
        BUDGET_TOOL_NAME,
        CATALOG_TOOL_NAME,
        GET_PLAN_TOOL,
        GET_MEAL_TOOL,
        SUBSTITUTE_TOOL,
        PRICE_TOOL,
        INGREDIENT_TOOL,
        PROPOSAL_TOOL,
    }
)
SCENARIO_IDS = tuple(f"C{number:02}" for number in range(1, 13))


def _known_tool(name: str) -> str:
    if name not in TOOL_NAMES:
        raise ValueError(CORPUS_ERROR)
    return name


ToolName = Annotated[StrictStr, AfterValidator(_known_tool)]
Outcome = Literal["prose", "template", "clarification", "proposal"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Inputs(_Model):
    now: StrictStr
    budget_period: StrictStr
    monthly_limit_cents: StrictInt
    posted_cents: StrictInt
    pending_cents: StrictInt
    plan_cap_cents: StrictInt | None
    spending_refreshed_at: StrictStr
    user_id: StrictInt
    diet: StrictStr
    ingredient_exclusions: list[StrictStr]


class Gold(_Model):
    tool: ToolName
    input: dict[StrictStr, object]
    path: Annotated[StrictStr, Field(min_length=1)]
    value: StrictBool | StrictInt | StrictStr


class Expect(_Model):
    tools_any: list[ToolName]
    tools_forbidden: list[ToolName]
    outcomes: Annotated[list[Outcome], Field(min_length=1)]
    gold: list[Gold]

    @model_validator(mode="after")
    def _check(self) -> Self:
        required = set(self.tools_any) | {item.tool for item in self.gold}
        repeated = len(set(self.outcomes)) != len(self.outcomes)
        if repeated or required & set(self.tools_forbidden):
            raise ValueError(CORPUS_ERROR)
        return self


class Turn(_Model):
    user: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    apply_proposal_before: StrictBool
    expect: Expect


class Scenario(_Model):
    id: StrictStr
    title: Annotated[StrictStr, Field(min_length=1)]
    inputs: Inputs
    plan: PlanSnapshot
    turns: Annotated[list[Turn], Field(min_length=1)]

    @model_validator(mode="after")
    def _check(self) -> Self:
        proposed = False
        for turn in self.turns:
            if turn.apply_proposal_before and not proposed:
                raise ValueError(CORPUS_ERROR)
            proposed = proposed or "proposal" in turn.expect.outcomes
        return self


class ConversationCorpus(_Model):
    version: Literal["conversation-eval-v1"]
    repeats: Literal[3]
    catalog_version: StrictStr
    scenarios: list[Scenario]

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = tuple(scenario.id for scenario in self.scenarios)
        if self.catalog_version != CATALOG_VERSION or ids != SCENARIO_IDS:
            raise ValueError(CORPUS_ERROR)
        return self


def load_conversation_corpus(path: Path) -> ConversationCorpus:
    try:
        return ConversationCorpus.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(CORPUS_ERROR) from None
