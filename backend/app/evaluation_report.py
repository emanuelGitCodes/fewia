from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import NoReturn, cast

from app.evaluation_cost import token_rate_config
from app.evaluation_cost_markdown import render_cost_markdown
from app.evaluation_io import FILE_UNAVAILABLE, OUTPUT_EXISTS
from app.evaluation_markdown import render_evaluation_markdown
from app.evaluation_report_io import write_markdown
from app.evaluation_report_values import INVALID, label, revision
from app.evaluation_summary import summarize_evaluation
from app.evaluation_telemetry import summarize_telemetry

_MAX = 16 * 1024 * 1024
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FAIL = "evaluation report failed"
_INTERRUPT = "evaluation report interrupted"


def _invalid() -> NoReturn:
    raise ValueError(INVALID) from None


def _constant(_token: str) -> object:
    _invalid()


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        _invalid()


def _plain_map(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    typed = cast(dict[object, object], value)
    if any(type(key) is not str for key in typed):
        _invalid()
    return {str(key): item for key, item in typed.items()}


def _opt_label(body: dict[str, object], key: str) -> str | None:
    value = body[key] if key in body else None
    if value is None:
        return None
    label(value)
    return cast(str, value)


def _need_label(body: dict[str, object], key: str) -> str:
    value = _opt_label(body, key)
    if value is None:
        _invalid()
    return value


def _cost(
    body: dict[str, object],
    telemetry: dict[str, object],
    rates: dict[str, object],
) -> str:
    config = token_rate_config(rates)
    routing = _opt_label(body, "routing")
    service_tier = _opt_label(body, "service_tier")
    return render_cost_markdown(
        telemetry,
        config,
        model_id=_need_label(body, "model_id"),
        source_region=_need_label(body, "source_region"),
        routing=config.routing if routing is None else routing,
        service_tier=config.service_tier if service_tier is None else service_tier,
    )


def _load(path: Path) -> dict[str, object]:
    try:
        info = path.lstat()
    except OSError:
        raise OSError(FILE_UNAVAILABLE) from None
    if not stat.S_ISREG(info.st_mode):
        _invalid()
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX + 1)
    except OSError:
        raise OSError(FILE_UNAVAILABLE) from None
    if len(raw) > _MAX:
        _invalid()
    try:
        payload: object = json.loads(raw.decode("utf-8"), parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError, ValueError):
        _invalid()
    return _plain_map(payload)


def _render(
    body: dict[str, object],
    rates: dict[str, object] | None = None,
) -> tuple[str, int]:
    if body.get("metrics_status") != "unassessed":
        _invalid()
    if "revision" not in body:
        _invalid()
    raw_slots = body.get("slots")
    if type(raw_slots) is not list or len(raw_slots) > 90:
        _invalid()
    slots = [_plain_map(item) for item in cast(list[object], raw_slots)]
    extra: list[str] = []
    hashed = body.get("prompt_hash")
    if hashed is not None:
        if type(hashed) is not str or _HASH.fullmatch(hashed) is None:
            _invalid()
        extra.append(f"Prompt hash: {hashed}")
    catalog = _opt_label(body, "catalog_version")
    if catalog is not None:
        extra.append(f"Catalog version: {label(catalog)}")
    telemetry = summarize_telemetry(slots)
    text = render_evaluation_markdown(
        summarize_evaluation(slots),
        telemetry,
        revision=revision(body["revision"]),
        model_id=_opt_label(body, "model_id"),
        source_region=_opt_label(body, "source_region"),
    )
    if extra:
        text = text + "\n".join(extra) + "\n"
    if rates is not None:
        text = text + _cost(body, telemetry, rates)
    return text, len(slots)


def _diag(text: str) -> None:
    print(text, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(prog="evaluation_report")
        parser.add_argument("--input", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--rates")
        args = parser.parse_args(argv)
        body = _load(Path(str(args.input)))
        rates = None if args.rates is None else _load(Path(str(args.rates)))
        text, total = _render(body, rates)
        write_markdown(Path(str(args.output)), text)
        print("evaluation report written")
        print(f"slots: {total}")
        return 0
    except KeyboardInterrupt:
        _diag(_INTERRUPT)
        return 130
    except SystemExit as err:
        return 0 if err.code in {0, None} else 1
    except ValueError:
        _diag(INVALID)
        return 1
    except OSError as err:
        _diag(OUTPUT_EXISTS if str(err) == OUTPUT_EXISTS else FILE_UNAVAILABLE)
        return 1
    except Exception:
        _diag(_FAIL)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
