from pathlib import Path

import pytest

from dev_supervisor.policy import (
    ADVISORS,
    COMPLEXITY,
    MODELS,
    Model,
    command,
    environment,
    load_registry,
    order,
    resolve_effort,
    writes,
)


def test_load_registry_rejects_builtin_override() -> None:
    for name in MODELS:
        with pytest.raises(
            ValueError, match="Registry MUST NOT replace a built-in model ID"
        ):
            load_registry({name: {"provider": "codex", "ceiling": "max"}})


def test_load_registry_rejects_legacy_effort() -> None:
    with pytest.raises(ValueError, match="use ceiling instead of effort"):
        load_registry({"custom-model": {"provider": "codex", "effort": "high"}})


def test_load_registry_rejects_invalid_ceiling() -> None:
    with pytest.raises(ValueError, match="Unknown model ceiling"):
        load_registry({"custom-model": {"provider": "codex", "ceiling": "ultra"}})


def test_load_registry_accepts_new_model() -> None:
    models = load_registry({"custom-model": {"provider": "codex", "ceiling": "high"}})
    assert models["custom-model"] == Model("codex", "high")
    for name, spec in MODELS.items():
        assert models[name] == spec
    assert order(None, False, models) == list(MODELS)[:3]


def test_registered_model_explicit_effort_keeps_fallbacks() -> None:
    models = load_registry({"custom-model": {"provider": "codex", "ceiling": "high"}})
    effort = "medium"
    ranked = order("custom-model", False, models, effort)
    assert ranked[0] == "custom-model"
    assert ranked == ["custom-model", "grok-4.6", "gpt-6-luna"]
    assert "gpt-5.3-codex-spark" not in ranked
    assert effort == "medium"


def test_order_and_explicit_only() -> None:
    assert order(None, False, MODELS) == list(MODELS)[:3]
    assert order("gpt-6.1-sol", False, MODELS)[0] == "gpt-6.1-sol"
    assert order("gpt-6.1-sol", True, MODELS) == ["gpt-6.1-sol"]
    with pytest.raises(ValueError):
        order("unknown", False, MODELS)
    with pytest.raises(ValueError):
        order(None, True, MODELS)


def test_default_order_explicit_medium_skips_spark() -> None:
    assert order(None, False, MODELS, "medium") == ["grok-4.6", "gpt-6-luna"]


def test_explicit_luna_high_keeps_only_luna() -> None:
    assert order("gpt-6-luna", False, MODELS, "high") == ["gpt-6-luna"]


def test_explicit_luna_low_keeps_luna_then_grok() -> None:
    assert order("gpt-6-luna", False, MODELS, "low") == [
        "gpt-6-luna",
        "grok-4.6",
    ]


def test_explicit_spark_medium_rejects_before_fallback() -> None:
    with pytest.raises(
        ValueError, match="Explicit effort requires a model effort ceiling"
    ):
        order("gpt-5.3-codex-spark", False, MODELS, "medium")


def test_automatic_selection_preserves_default_order() -> None:
    assert order(None, False, MODELS) == [
        "grok-4.6",
        "gpt-5.3-codex-spark",
        "gpt-6-luna",
    ]
    assert order(None, False, MODELS) == list(MODELS)[:3]


def test_supported_commands() -> None:
    for name, spec in MODELS.items():
        args = command(
            name,
            spec,
            Path.cwd(),
            Path("task.txt"),
            effort=resolve_effort("standard", spec),
        )
        assert name in args
        assert not any("bypass" in arg for arg in args)
    spark = command(
        "gpt-5.3-codex-spark",
        MODELS["gpt-5.3-codex-spark"],
        Path.cwd(),
        Path("p"),
        effort=resolve_effort("maximum", MODELS["gpt-5.3-codex-spark"]),
    )
    assert not any("model_reasoning_effort" in arg for arg in spark)


def test_complexity_maps_ceilings_and_rejects_explicit_over_ceiling() -> None:
    grok = MODELS["grok-4.6"]
    spark = MODELS["gpt-5.3-codex-spark"]
    luna = MODELS["gpt-6-luna"]
    sol = MODELS["gpt-6.1-sol"]
    for complexity, effort in COMPLEXITY.items():
        assert resolve_effort(complexity, luna) == effort
        assert resolve_effort(complexity, sol) == effort
        grok_effort = "low" if complexity == "simple" else "medium"
        assert resolve_effort(complexity, grok) == grok_effort
        assert resolve_effort(complexity, spark) is None
        spark_cmd = command(
            "gpt-5.3-codex-spark", spark, Path.cwd(), Path("p"), effort=None
        )
        assert not any("model_reasoning_effort" in arg for arg in spark_cmd)
    luna_max = command("gpt-6-luna", luna, Path.cwd(), Path("p"), effort="max")
    assert any('model_reasoning_effort="max"' in arg for arg in luna_max)
    grok_cmd = command("grok-4.6", grok, Path.cwd(), Path("p"), effort="medium")
    assert grok_cmd[grok_cmd.index("--reasoning-effort") + 1] == "medium"
    grok_low = command("grok-4.6", grok, Path.cwd(), Path("p"), effort="low")
    assert grok_low[grok_low.index("--reasoning-effort") + 1] == "low"
    for blocked in ("high", "xhigh", "max"):
        with pytest.raises(ValueError):
            resolve_effort("standard", grok, blocked)
    assert resolve_effort("maximum", luna, "max") == "max"


def test_explicit_effort_rejects_spark() -> None:
    spark = MODELS["gpt-5.3-codex-spark"]
    assert spark.ceiling is None
    with pytest.raises(ValueError):
        resolve_effort("standard", spark, "medium")
    assert resolve_effort("standard", spark) is None


def test_roles_do_not_pin_reasoning_effort() -> None:
    root = Path(__file__).resolve().parents[2] / ".codex/agents"
    files = list(root.glob("*.toml"))
    assert files
    for path in files:
        text = path.read_text()
        assert "model_reasoning_effort" not in text
        assert 'model = "gpt-6-luna"' in text


def test_write_paths_authorize_exact_grok_rules(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    files = writes(tmp_path, ["app.py"])
    grok = command("grok-4.6", MODELS["grok-4.6"], tmp_path, tmp_path / "p", files)
    assert grok[grok.index("--permission-mode") + 1] == "default"
    assert f"Write({target.resolve()})" in grok
    assert f"Edit({target.resolve()})" in grok
    spark = command(
        "gpt-5.3-codex-spark",
        MODELS["gpt-5.3-codex-spark"],
        tmp_path,
        tmp_path / "p",
        files,
    )
    assert "--sandbox" in spark and "workspace-write" in spark
    assert not any(arg.startswith(("Write(", "Edit(")) for arg in spark)
    with pytest.raises(ValueError):
        writes(tmp_path, ["*.py"])
    with pytest.raises(ValueError):
        writes(tmp_path, ["/tmp/x"])
    with pytest.raises(ValueError):
        writes(tmp_path, ["Write(app.py)"])
    with pytest.raises(ValueError):
        writes(tmp_path, ["../escape.py"])
    outside = tmp_path / "outside.txt"
    outside.write_text("no")
    inner = tmp_path / "work"
    inner.mkdir()
    (inner / "escape").symlink_to(outside)
    with pytest.raises(ValueError):
        writes(inner, ["escape"])


CLAUDE = MODELS["claude-sonnet-5-5"]
CLAUDE_HEAD = [
    "claude",
    "-p",
    "--safe-mode",
    "--model",
    "claude-sonnet-5-5",
    "--effort",
    "medium",
    "--output-format",
    "stream-json",
    "--verbose",
    "--no-session-persistence",
    "--tools",
    "Read,Edit,Write,Glob,Grep",
    "--permission-mode",
    "default",
    "--permission-prompts",
    "none",
    "--max-turns",
    "30",
]


def test_claude_models_and_advisors() -> None:
    assert list(MODELS)[-2:] == ["claude-sonnet-5-5", "claude-opus-5-5"]
    assert MODELS["claude-sonnet-5-5"] == Model("claude", "max")
    assert MODELS["claude-opus-5-5"] == Model("claude", "max")
    assert order(None, False, MODELS) == [
        "grok-4.6",
        "gpt-5.3-codex-spark",
        "gpt-6-luna",
    ]
    assert ADVISORS == ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1")


def test_claude_argv_shape_and_rules(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    args = command(
        "claude-sonnet-5-5",
        CLAUDE,
        tmp_path,
        tmp_path / "p",
        writes(tmp_path, ["app.py"]),
    )
    assert args == [*CLAUDE_HEAD, "--allowedTools", f"Edit(/{target.resolve()})"]
    assert args[-1].startswith("Edit(//")
    prompt = tmp_path / "p"
    default = command("claude-sonnet-5-5", CLAUDE, tmp_path, prompt)
    assert default[default.index("--effort") + 1] == "medium"
    high = command("claude-sonnet-5-5", CLAUDE, tmp_path, prompt, effort="high")
    assert high[high.index("--effort") + 1] == "high"


def test_claude_rejects_path_with_space(tmp_path: Path) -> None:
    spaced = tmp_path / "has space" / "app.py"
    spaced.parent.mkdir()
    spaced.write_text("x = 1\n")
    with pytest.raises(ValueError, match="Write path MUST stay a relative"):
        command("claude-sonnet-5-5", CLAUDE, tmp_path, tmp_path / "p", [spaced])


def test_claude_advisor_and_budget(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    args = command(
        "claude-sonnet-5-5",
        CLAUDE,
        tmp_path,
        tmp_path / "p",
        [target],
        None,
        "claude-fable-5-1",
        3,
    )
    assert args == [
        *CLAUDE_HEAD,
        "--advisor",
        "claude-fable-5-1",
        "--max-budget-usd",
        "3.00",
        "--allowedTools",
        f"Edit(/{target.resolve()})",
    ]
    prompt = tmp_path / "p"
    with pytest.raises(ValueError, match="Unknown advisor"):
        command("claude-sonnet-5-5", CLAUDE, tmp_path, prompt, advisor="gpt-6-luna")


def test_advisor_and_budget_reject_other_providers(tmp_path: Path) -> None:
    for name in ("grok-4.6", "gpt-6-luna"):
        spec = MODELS[name]
        with pytest.raises(ValueError):
            command(name, spec, tmp_path, tmp_path / "p", advisor="claude-opus-5-5")
        with pytest.raises(ValueError):
            command(name, spec, tmp_path, tmp_path / "p", budget=1.0)


def test_environment_disables_advisor_tool_without_advisor() -> None:
    assert environment(CLAUDE, None) == {"CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1"}
    assert environment(CLAUDE, "claude-opus-5-5") == {}
    assert environment(MODELS["grok-4.6"], None) == {}
    assert environment(MODELS["gpt-6-luna"], None) == {}


def test_resolved_write_paths_reject_rule_metacharacters(tmp_path: Path) -> None:
    starred_root = tmp_path / "project*"
    starred_root.mkdir()
    (starred_root / "app.py").write_text("x = 1\n")
    with pytest.raises(ValueError):
        writes(starred_root, ["app.py"])
    wild = tmp_path / "wild*"
    wild.mkdir()
    (wild / "app.py").write_text("x = 1\n")
    (tmp_path / "alias").symlink_to(wild)
    with pytest.raises(ValueError):
        writes(tmp_path, ["alias/app.py"])
    (tmp_path / "src").mkdir()
    with pytest.raises(ValueError):
        writes(tmp_path, ["src"])
    (tmp_path / "app.py").write_text("x = 1\n")
    files = writes(tmp_path, ["app.py"])
    progress = tmp_path / "state*" / "progress.md"
    progress.parent.mkdir()
    progress.write_text("check")
    with pytest.raises(ValueError):
        command(
            "grok-4.6",
            MODELS["grok-4.6"],
            tmp_path,
            tmp_path / "p",
            [*files, progress],
        )
