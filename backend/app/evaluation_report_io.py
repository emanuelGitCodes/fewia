from __future__ import annotations

from pathlib import Path
from typing import TextIO

from app.evaluation_io import (
    _drop,
    _exists,
    _install,
    _open_exclusive,
    _present,
    _unavailable,
)
from app.evaluation_report_values import INVALID


def write_markdown(output: Path, text: str) -> None:
    temp = output.with_name(output.name + ".tmp")
    if type(text) is not str or output.suffix.lower() != ".md" or not text.strip():
        raise ValueError(INVALID) from None
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise ValueError(INVALID) from None
    if _present(output) or _present(temp):
        _exists()
    handle: TextIO | None = None
    owned = False
    try:
        handle = _open_exclusive(temp)
        owned = True
        try:
            handle.write(text)
            handle.flush()
        except OSError:
            _unavailable()
        try:
            handle.close()
        except OSError:
            handle = None
            _unavailable()
        handle = None
        _install(temp, output)
    except BaseException:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if owned:
            _drop(temp)
        raise
    _drop(temp)
