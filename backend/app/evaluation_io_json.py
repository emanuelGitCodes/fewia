import json
import math
import os
import stat
from pathlib import Path
from typing import NoReturn, cast

_INVALID = "evaluation JSON is invalid"
_UNAVAILABLE = "evaluation files are unavailable"


def _invalid() -> NoReturn:
    raise ValueError(_INVALID) from None


def _validate(value: object, ancestors: set[int]) -> None:
    kind = type(value)
    if kind in (dict, list):
        ident = id(value)
        if ident in ancestors:
            _invalid()
        ancestors.add(ident)
        if kind is dict:
            for key, child in cast(dict[object, object], value).items():
                if type(key) is not str or key == "reasoningContent":
                    _invalid()
                _validate(child, ancestors)
        else:
            for child in cast(list[object], value):
                _validate(child, ancestors)
        ancestors.remove(ident)
    elif kind is float:
        if not math.isfinite(cast(float, value)):
            _invalid()
    elif kind not in (str, int, bool, type(None)):
        _invalid()


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    _validate(value, set())
    return cast(dict[str, object], value)


def canonical_json_bytes(value: object) -> bytes:
    try:
        report = _object(value)
        return json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        _invalid()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _constant(_value: str) -> NoReturn:
    _invalid()


def _read(path: Path, max_bytes: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError(_UNAVAILABLE)
            if info.st_size > max_bytes:
                _invalid()
            data = bytearray()
            while len(data) <= max_bytes:
                chunk = os.read(fd, min(65_536, max_bytes + 1 - len(data)))
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
            _invalid()
        finally:
            os.close(fd)
    except (OSError, ValueError) as error:
        if isinstance(error, OSError):
            raise OSError(_UNAVAILABLE) from None
        _invalid()


def load_json(path: Path, *, max_bytes: int = 16_777_216) -> dict[str, object]:
    if type(max_bytes) is not int or max_bytes <= 0:
        _invalid()
    raw = _read(path, max_bytes)
    try:
        payload: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
        return _object(payload)
    except (TypeError, ValueError, RecursionError):
        _invalid()
