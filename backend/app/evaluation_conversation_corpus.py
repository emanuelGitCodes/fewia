"""Strict loader for the conversation-eval-v1 corpus.

This suite is separate from the frozen grocery-eval-v1 matrix. It holds data and
validation only; no runner lives here.
"""

from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self, cast
from uuid import UUID

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

from app.agent.chat_loop import ChatUnavailable, run_chat
from app.domain.catalog import CATALOG_VERSION
from app.domain.plan_revision import PlanRevisionInput, PlanSnapshot
from app.evaluation_budget_inputs import fixture_budget

CORPUS_ERROR = "corpus MUST match the conversation-eval-v1 contract"
MAX_MEALS = 3


class _ToolRecorder:
    """A provider that records the tool list run_chat offers, then fails."""

    def __init__(self) -> None:
        self.names: frozenset[str] | None = None

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.names = frozenset(
            cast(str, cast(dict[str, object], spec["toolSpec"])["name"])
            for spec in tools
        )
        raise RuntimeError("tool list recorded")


def _registered_tool_names() -> frozenset[str]:
    """Return the tools run_chat registers with a plan revision and propose."""
    recorder = _ToolRecorder()
    budget = fixture_budget(
        {
            "now": "2026-09-06T16:00:00Z",
            "budget_period": "2026-09-01",
            "monthly_limit_cents": 10000,
            "posted_cents": 0,
            "pending_cents": 0,
            "plan_cap_cents": None,
            "spending_refreshed_at": "2026-09-06T15:00:00Z",
        }
    )
    plan = PlanRevisionInput(
        id=UUID(int=1),
        snapshot=PlanSnapshot.model_validate(
            {
                "meals": [{"recipe_id": "bean_tacos", "servings": 1}],
                "pantry_ingredient_ids": [],
            }
        ),
    )
    with suppress(ChatUnavailable):
        run_chat(
            recorder,
            "What does my plan cost?",
            budget,
            date(2026, 9, 1),
            plan_revision=plan,
            propose=lambda operations: "proposal-fixture",
        )
    if recorder.names is None:
        raise RuntimeError("run_chat did not offer a tool list")
    return recorder.names


TOOL_NAMES = _registered_tool_names()
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
        if (
            not 1 <= len(self.plan.meals) <= MAX_MEALS
            or self.plan.plan_cap_cents != self.inputs.plan_cap_cents
        ):
            raise ValueError(CORPUS_ERROR)
        # Applying a proposal consumes it; the next apply needs a new proposal turn.
        proposed = False
        for turn in self.turns:
            if turn.apply_proposal_before:
                if not proposed:
                    raise ValueError(CORPUS_ERROR)
                proposed = False
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
