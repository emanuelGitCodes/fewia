import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Never

from deployment_config import DeploymentConfig, parse_deployment_config

_LIMIT = 16384
_ERROR = "deployment configuration is invalid"
_STACK = "FewiaHostedDemoDev"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_ERROR)
        result[key] = value
    return result


def _reject_constant(value: str) -> Never:
    raise ValueError(_ERROR)


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(_ERROR)
    return result


def load_deployment_config(path: Path) -> DeploymentConfig:
    try:
        with path.open("rb") as source:
            payload = source.read(_LIMIT + 1)
        if len(payload) > _LIMIT:
            raise ValueError(_ERROR)
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        return parse_deployment_config(raw)
    except Exception:
        pass
    raise ValueError(_ERROR)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError("arguments are invalid")


def _status(status: str, stage: str, code: int) -> int:
    print(json.dumps({"status": status, "stage": stage}))
    return code


def main(argv: Sequence[str] | None = None) -> int:
    stage = "arguments"
    try:
        parser = _Parser(prog="python hosted_app.py", allow_abbrev=False)
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--outdir", type=Path)
        try:
            args = parser.parse_args(argv)
        except SystemExit as error:
            if error.code == 0:
                return 0
            return _status("failed", stage, 1)
        stage = "configuration"
        config = load_deployment_config(args.config)
        stage = "synthesis"
        from aws_cdk import App

        from hosted_stack import HostedDemoStack

        app = App(outdir=str(args.outdir)) if args.outdir is not None else App()
        HostedDemoStack(app, _STACK, config=config)
        app.synth()
        print(
            json.dumps(
                {"status": "synthesized", "phase": config.phase, "stack": _STACK}
            )
        )
        return 0
    except KeyboardInterrupt:
        return _status("interrupted", stage, 130)
    except (Exception, SystemExit):
        return _status("failed", stage, 1)


if __name__ == "__main__":
    raise SystemExit(main())
