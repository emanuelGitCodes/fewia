import json
import os
from pathlib import Path
from typing import NoReturn, TextIO, cast

from app.evaluation_batch import INVALID, _corpus_ok, _snapshot

FILE_UNAVAILABLE = "evaluation files are unavailable"
OUTPUT_EXISTS = "evaluation output already exists"


def _invalid() -> NoReturn:
    raise ValueError(INVALID) from None


def _unavailable() -> NoReturn:
    raise OSError(FILE_UNAVAILABLE) from None


def _exists() -> NoReturn:
    raise OSError(OUTPUT_EXISTS) from None


def _present(path: Path) -> bool:
    return path.is_symlink() or path.exists()


def _journal(output: Path) -> Path:
    if output.suffix.lower() == ".jsonl":
        _invalid()
    journal = output.with_suffix(".jsonl")
    if journal == output:
        _invalid()
    return journal


def _dumps(payload: dict[str, object]) -> str:
    try:
        return json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError):
        _invalid()


def _open_exclusive(path: Path) -> TextIO:
    try:
        return path.open("x", encoding="utf-8")
    except FileExistsError:
        _exists()
    except OSError:
        _unavailable()


def _emit(handle: TextIO, line: str) -> None:
    try:
        handle.write(line + "\n")
        handle.flush()
    except OSError:
        _unavailable()


def _drop(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


def _install(temp: Path, output: Path) -> None:
    try:
        # os.replace overwrites a preexisting output path.
        os.link(temp, output)
    except FileExistsError:
        _exists()
    except OSError:
        _unavailable()


def load_corpus(path: Path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        _unavailable()
    except UnicodeError:
        _invalid()
    try:
        payload: object = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        _invalid()
    if not _corpus_ok(payload):
        _invalid()
    try:
        _, working = _snapshot(cast(dict[str, object], payload))
    except ValueError:
        _invalid()
    return working


def open_journal(output: Path, manifest: dict[str, object]) -> TextIO:
    journal = _journal(output)
    if _present(output) or _present(journal):
        _exists()
    line = _dumps(manifest)
    handle = _open_exclusive(journal)
    try:
        _emit(handle, line)
    except OSError:
        try:
            handle.close()
        except OSError:
            pass
        raise
    return handle


def write_record(handle: TextIO, payload: dict[str, object]) -> None:
    _emit(handle, _dumps(payload))


def write_result(output: Path, result: dict[str, object]) -> None:
    body = _dumps(result)
    _journal(output)
    if _present(output):
        _exists()
    temp = output.with_name(output.name + ".tmp")
    handle: TextIO | None = None
    owned = False
    try:
        handle = _open_exclusive(temp)
        owned = True
        _emit(handle, body)
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
