from pathlib import Path

import pytest

from dev_supervisor.policy import MODELS, command, order


def test_order_and_explicit_only() -> None:
    assert order(None, False, MODELS) == list(MODELS)[:3]
    assert order("gpt-5.6-sol", False, MODELS)[0] == "gpt-5.6-sol"
    assert order("gpt-5.6-sol", True, MODELS) == ["gpt-5.6-sol"]
    with pytest.raises(ValueError):
        order("unknown", False, MODELS)
    with pytest.raises(ValueError):
        order(None, True, MODELS)


def test_supported_commands() -> None:
    for name, spec in MODELS.items():
        args = command(name, spec, Path.cwd(), Path("task.txt"))
        assert name in args
        assert not any("bypass" in arg for arg in args)
    spark = command(
        "gpt-5.3-codex-spark", MODELS["gpt-5.3-codex-spark"], Path.cwd(), Path("p")
    )
    assert not any("model_reasoning_effort" in arg for arg in spark)
