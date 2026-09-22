from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

import pytest

from app.evaluation_io import FILE_UNAVAILABLE, OUTPUT_EXISTS
from app.evaluation_report_io import write_markdown
from app.evaluation_report_values import INVALID

SECRET = "do-not-echo-raw-input"
MARKER = "eval-md-marker-path-payload"
BODY = "# Report\nEstimated from the demo price catalog.\n"


def _static(err: BaseException, path: Path) -> None:
    text = str(err)
    assert err.__cause__ is None
    assert SECRET not in text
    assert MARKER not in text
    assert str(path) not in text
    assert path.name not in text


def _temp(output: Path) -> Path:
    return output.with_name(output.name + ".tmp")


def _break_exclusive(
    monkeypatch: pytest.MonkeyPatch,
    *,
    flush: bool,
    close: bool = False,
    interrupt: bool = False,
) -> None:
    orig = Path.open

    def wrapped(self: Path, mode: str = "r", *args: object, **kwargs: object) -> TextIO:
        handle = orig(self, mode, *args, **kwargs)
        if "x" not in mode:
            return handle

        def boom(*_a: object, **_k: object) -> None:
            if interrupt:
                raise KeyboardInterrupt
            raise OSError(28)

        if close:
            monkeypatch.setattr(handle, "close", boom)
        elif flush:
            monkeypatch.setattr(handle, "flush", boom)
        else:
            monkeypatch.setattr(handle, "write", boom)
        return handle

    monkeypatch.setattr(Path, "open", wrapped)


@pytest.mark.parametrize("name", ["out.md", "out.MD"])
def test_write_markdown_installs_exact_bytes(tmp_path: Path, name: str) -> None:
    output = tmp_path / name
    write_markdown(output, BODY)
    assert output.read_text(encoding="utf-8") == BODY
    assert not _temp(output).exists()


def test_existing_output_temp_and_symlinks_are_preserved(tmp_path: Path) -> None:
    output = tmp_path / "out.md"
    output.write_text("old\n", encoding="utf-8")
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$") as err:
        write_markdown(output, BODY)
    _static(err.value, output)
    assert output.read_text(encoding="utf-8") == "old\n"
    output.unlink()
    temp = _temp(output)
    temp.write_text("tmp\n", encoding="utf-8")
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        write_markdown(output, BODY)
    assert temp.read_text(encoding="utf-8") == "tmp\n"
    assert not output.exists()
    temp.unlink()
    target = tmp_path / "missing-target"
    output.symlink_to(target)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        write_markdown(output, BODY)
    assert output.is_symlink()
    output.unlink()
    temp.symlink_to(target)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        write_markdown(output, BODY)
    assert temp.is_symlink()
    assert not output.exists()


@pytest.mark.parametrize("kind", ["write", "flush", "close"])
def test_failed_emit_close_cleans_owned_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    output = tmp_path / f"{MARKER}.md"
    _break_exclusive(monkeypatch, flush=kind == "flush", close=kind == "close")
    with pytest.raises(OSError, match=f"^{FILE_UNAVAILABLE}$") as err:
        write_markdown(output, BODY)
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()


def test_failed_install_cleans_owned_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / f"{MARKER}.md"

    def boom(source: str | os.PathLike[str], dest: str | os.PathLike[str]) -> None:
        raise OSError(28)

    monkeypatch.setattr("app.evaluation_io.os.link", boom)
    with pytest.raises(OSError, match=f"^{FILE_UNAVAILABLE}$") as err:
        write_markdown(output, BODY)
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()


def test_write_markdown_refuses_existing_final_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / f"{MARKER}.md"
    real_link = os.link

    def raced(source: str | os.PathLike[str], dest: str | os.PathLike[str]) -> None:
        Path(dest).write_text("old\n", encoding="utf-8")
        real_link(source, dest)

    monkeypatch.setattr("app.evaluation_io.os.link", raced)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$") as err:
        write_markdown(output, BODY)
    _static(err.value, output)
    assert output.read_text(encoding="utf-8") == "old\n"
    assert not _temp(output).exists()


@pytest.mark.parametrize("name", ["out.json", "out.txt"])
def test_invalid_suffix_uses_static_valueerror(tmp_path: Path, name: str) -> None:
    output = tmp_path / name
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_markdown(output, BODY)
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()


def test_invalid_type_and_empty_text_use_static_valueerror(tmp_path: Path) -> None:
    output = tmp_path / f"{MARKER}.md"
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_markdown(output, "")
    _static(err.value, output)
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_markdown(output, 1)  # type: ignore[arg-type]
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()


@pytest.mark.parametrize("text", [" ", "\n", "\t"])
def test_whitespace_only_text_uses_static_valueerror(tmp_path: Path, text: str) -> None:
    output = tmp_path / f"{MARKER}.md"
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_markdown(output, text)
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()


def test_lone_surrogate_uses_static_valueerror(tmp_path: Path) -> None:
    output = tmp_path / f"{MARKER}.md"
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_markdown(output, "\ud800")
    _static(err.value, output)
    assert not output.exists()
    assert not _temp(output).exists()
