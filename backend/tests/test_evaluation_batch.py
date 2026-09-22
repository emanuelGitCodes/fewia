from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

import pytest

from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.provider import LLMProvider
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_batch import INVALID, run_observed_evaluation
from app.evaluation_model import SUPPORTED_IDS
from app.evaluation_runner import run_evaluation

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
MODEL_ID = "eval-fake-v1"
SECRET = "do-not-echo-raw-input"
EVIDENCE: Literal["deterministic_fake_provider", "real_bedrock"] = (
    "deterministic_fake_provider"
)
UNSUPPORTED_IDS = frozenset({"P01", "P02", "P04", "P05", "A02", "A03", "A04"})
SCORED_COUNT = 45
OBSERVED_COUNT = 24
UNASSESSED_COUNT = 21


class ScriptedProvider:
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Choose a supported meal."}],
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }


def load_corpus() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _slots(result: dict[str, object]) -> list[dict[str, object]]:
    rows = result["slots"]
    assert isinstance(rows, list)
    return [_mapping(item, "slot") for item in rows]


def _hexdigest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run(
    corpus: dict[str, object],
    factory: Callable[[], LLMProvider],
    *,
    model_id: str = MODEL_ID,
    evidence_class: str = EVIDENCE,
    on_slot: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    labeled = cast(
        Literal["deterministic_fake_provider", "real_bedrock"],
        evidence_class,
    )
    return run_observed_evaluation(
        corpus,
        factory,
        model_id=model_id,
        evidence_class=labeled,
        on_slot=on_slot,
    )


def _factory() -> tuple[list[ScriptedProvider], Callable[[], LLMProvider]]:
    providers: list[ScriptedProvider] = []

    def make() -> LLMProvider:
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    return providers, make


def test_observed_batch_counts_and_fresh_providers() -> None:
    corpus = load_corpus()
    providers, factory = _factory()
    result = _run(corpus, factory)
    slots = _slots(result)
    scored = [slot for slot in slots if slot["status"] == "scored"]
    observed = [slot for slot in slots if slot["status"] == "observed"]
    unassessed = [slot for slot in slots if slot["status"] == "unassessed"]
    assert result["slot_count"] == 90
    assert len(slots) == 90
    assert len(scored) == SCORED_COUNT
    assert len(observed) == OBSERVED_COUNT
    assert len(unassessed) == UNASSESSED_COUNT
    assert len(providers) == OBSERVED_COUNT
    assert len({id(item) for item in providers}) == OBSERVED_COUNT
    repeats: dict[str, set[int]] = defaultdict(set)
    for slot in observed:
        case_id = slot["case_id"]
        assert type(case_id) is str
        assert case_id in SUPPORTED_IDS
        repeat = slot["repeat"]
        assert type(repeat) is int
        repeats[case_id].add(repeat)
        observation = _mapping(slot["observation"], "observation")
        assert observation["status"] == "completed"
        assert slot["report"] is None
    assert set(repeats) == set(SUPPORTED_IDS)
    for values in repeats.values():
        assert values == {1, 2, 3}
    for slot in unassessed:
        assert slot["case_id"] in UNSUPPORTED_IDS
        assert slot["reason"] == "unsupported_scenario"
        assert slot["report"] is None
        assert "observation" not in slot
    assert result["mode"] == "mixed_fixture_model"
    assert result["model_id"] == MODEL_ID
    assert result["catalog_version"] == CATALOG_VERSION
    assert result["prompt_hash"] == _hexdigest(SYSTEM_PROMPT)
    assert result["metrics_status"] == "unassessed"
    payload = json.dumps(corpus, sort_keys=True, allow_nan=False)
    assert result["corpus_hash"] == _hexdigest(payload)


def test_invalid_corpus_makes_zero_factory_calls() -> None:
    providers, factory = _factory()
    corpus = load_corpus()
    corpus["catalog_version"] = "not-the-catalog"
    with pytest.raises(ValueError, match="^evaluation input is invalid$") as err:
        _run(corpus, factory)
    assert str(err.value) == INVALID
    assert SECRET not in str(err.value)
    assert providers == []


def test_invalid_repeats_and_blank_ids_make_zero_calls() -> None:
    providers, factory = _factory()
    repeats = load_corpus()
    repeats["repeats"] = 2
    with pytest.raises(ValueError, match="^evaluation input is invalid$"):
        _run(repeats, factory)
    blank = load_corpus()
    rows = blank["scenarios"]
    assert isinstance(rows, list)
    first = _mapping(rows[0], "case")
    first["id"] = "   "
    with pytest.raises(ValueError, match="^evaluation input is invalid$"):
        _run(blank, factory)
    duplicate = load_corpus()
    rows = duplicate["scenarios"]
    assert isinstance(rows, list)
    second = _mapping(rows[1], "case")
    second["id"] = _mapping(rows[0], "first")["id"]
    with pytest.raises(ValueError, match="^evaluation input is invalid$"):
        _run(duplicate, factory)
    assert providers == []


def test_nan_corpus_is_invalid_without_factory_calls() -> None:
    providers, factory = _factory()
    corpus = load_corpus()
    corpus["metrics"] = [float("nan")]
    with pytest.raises(ValueError, match="^evaluation input is invalid$"):
        _run(corpus, factory)
    assert providers == []


def test_invalid_metadata_makes_zero_calls_and_does_not_echo() -> None:
    providers, factory = _factory()
    corpus = load_corpus()
    with pytest.raises(ValueError, match="^evaluation input is invalid$") as err:
        _run(corpus, factory, model_id=f"  {SECRET}  ")
    assert SECRET not in str(err.value)
    with pytest.raises(ValueError, match="^evaluation input is invalid$"):
        _run(corpus, factory, evidence_class="deployed_aws")
    assert providers == []


def test_factory_failure_isolates_other_cases() -> None:
    providers: list[ScriptedProvider] = []
    calls = 0

    def make() -> LLMProvider:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(SECRET)
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    result = _run(load_corpus(), make)
    slots = _slots(result)
    assert calls == OBSERVED_COUNT
    assert len(providers) == OBSERVED_COUNT - 1
    failed = [slot for slot in slots if slot["status"] == "failed"]
    observed = [slot for slot in slots if slot["status"] == "observed"]
    assert len(failed) == 1
    assert len(observed) == OBSERVED_COUNT - 1
    first = failed[0]
    assert first["case_id"] == "F01"
    assert first["repeat"] == 1
    observation = _mapping(first["observation"], "observation")
    assert observation["status"] == "failed"
    assert observation["reason"] == "provider_initialization_failed"
    blob = json.dumps(result, default=str)
    assert SECRET not in blob
    assert len([slot for slot in slots if slot["status"] == "scored"]) == SCORED_COUNT
    assert len([slot for slot in slots if slot["status"] == "unassessed"]) == (
        UNASSESSED_COUNT
    )


def test_corpus_is_unchanged_and_hash_tracks_content() -> None:
    corpus = load_corpus()
    original = copy.deepcopy(corpus)
    providers, factory = _factory()
    first = _run(corpus, factory)
    assert corpus == original
    changed = copy.deepcopy(corpus)
    changed["mode_note"] = "altered-note"
    more, second_factory = _factory()
    second = _run(changed, second_factory)
    assert first["corpus_hash"] != second["corpus_hash"]
    payload = json.dumps(changed, sort_keys=True, allow_nan=False)
    assert second["corpus_hash"] == _hexdigest(payload)
    assert len(providers) == OBSERVED_COUNT
    assert len(more) == OBSERVED_COUNT


def test_fixture_gold_reports_are_unchanged() -> None:
    corpus = load_corpus()
    baseline = run_evaluation(copy.deepcopy(corpus))
    _providers, factory = _factory()
    mixed = _run(corpus, factory)
    base_slots = _slots(baseline)
    mixed_slots = _slots(mixed)
    assert len(base_slots) == len(mixed_slots)
    for left, right in zip(base_slots, mixed_slots, strict=True):
        if left["status"] != "scored":
            continue
        assert right["status"] == "scored"
        assert right["case_id"] == left["case_id"]
        assert right["repeat"] == left["repeat"]
        assert right["report"] == left["report"]
        assert "observation" not in right


def test_on_slot_emits_ninety_unique_events_and_fresh_providers() -> None:
    corpus = load_corpus()
    providers, factory = _factory()
    events: list[dict[str, object]] = []
    result = _run(corpus, factory, on_slot=events.append)
    keys = {(item["case_id"], item["repeat"]) for item in events}
    scored = [item for item in events if item["status"] == "scored"]
    observed = [item for item in events if item["status"] == "observed"]
    unassessed = [item for item in events if item["status"] == "unassessed"]
    assert len(_slots(result)) == 90
    assert len(events) == 90
    assert len(keys) == 90
    assert len(scored) == SCORED_COUNT
    assert len(observed) == OBSERVED_COUNT
    assert len(unassessed) == UNASSESSED_COUNT
    assert len(providers) == OBSERVED_COUNT
    assert len({id(item) for item in providers}) == OBSERVED_COUNT


def test_factory_failure_emits_failed_callback() -> None:
    providers: list[ScriptedProvider] = []
    calls = 0
    events: list[dict[str, object]] = []

    def make() -> LLMProvider:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(SECRET)
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    result = _run(load_corpus(), make, on_slot=events.append)
    failed = [item for item in events if item["status"] == "failed"]
    observed = [item for item in events if item["status"] == "observed"]
    assert len(events) == 90
    assert calls == OBSERVED_COUNT
    assert len(providers) == OBSERVED_COUNT - 1
    assert len(failed) == 1
    assert len(observed) == OBSERVED_COUNT - 1
    first = failed[0]
    assert first["case_id"] == "F01"
    assert first["repeat"] == 1
    observation = _mapping(first["observation"], "observation")
    assert observation["reason"] == "provider_initialization_failed"
    blob = json.dumps(result, default=str)
    assert SECRET not in blob


def test_callback_error_at_first_observed_stops_provider_calls() -> None:
    providers, factory = _factory()
    events: list[dict[str, object]] = []

    def on_slot(slot: dict[str, object]) -> None:
        events.append(slot)
        if slot["status"] == "observed":
            raise RuntimeError(SECRET)

    with pytest.raises(RuntimeError, match=f"^{SECRET}$"):
        _run(load_corpus(), factory, on_slot=on_slot)
    observed = [item for item in events if item["status"] == "observed"]
    assert len(providers) == 1
    assert len(observed) == 1
    assert observed[0]["case_id"] == "F01"
    assert observed[0]["repeat"] == 1
