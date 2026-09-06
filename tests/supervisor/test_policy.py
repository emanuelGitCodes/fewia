from pathlib import Path

import pytest

from dev_supervisor.policy import MODELS, command, order, writes


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
