import argparse
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from app.evaluation_cost_rates import parse_rates
from app.evaluation_database import _validated_url
from app.evaluation_io import load_json
from app.evaluation_manifest import build_manifest
from app.evaluation_matrix import prepare_matrix
from app.providers.local_sqs import ALLOWED_ENDPOINTS

_INVALID = "Invalid evaluation CLI input"
_MODEL_ID = "us.amazon.nova-2-lite-v1:0"


@dataclass(frozen=True)
class EvaluationOptions:
    corpus: dict[str, object] = field(repr=False)
    rates: dict[str, object] | None
    output_dir: Path
    revision: str
    model_id: str
    region: str
    model_config: dict[str, object]
    profile_name: str | None = field(repr=False)
    database_url: str | None = field(repr=False)
    endpoint: str | None = field(repr=False)
    live_bedrock: bool


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(_INVALID) from None


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = _Parser(prog="fewia-evaluation", allow_abbrev=False)
    parser.add_argument("--corpus", required=True, metavar="PATH")
    parser.add_argument("--output-dir", required=True, metavar="NEWDIR")
    parser.add_argument("--revision", required=True, metavar="40HEX")
    parser.add_argument("--model-id", default=_MODEL_ID)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--rates", metavar="PATH")
    parser.add_argument("--live-bedrock", action="store_true")
    parser.add_argument("--local-services", action="store_true")
    return parser.parse_args(argv)


def load_options(
    argv: list[str] | None = None, *, fixture: bool = False
) -> EvaluationOptions:
    try:
        args = _arguments(argv)
        if (
            type(fixture) is not bool
            or (fixture and args.live_bedrock)
            or (not fixture and not args.live_bedrock)
        ):
            raise ValueError(_INVALID)
        if (
            args.model_id != _MODEL_ID
            or args.region not in {"us-east-1", "us-west-2"}
            or re.fullmatch(r"[0-9a-f]{40}", args.revision) is None
            or not args.output_dir
            or "\0" in args.output_dir
        ):
            raise ValueError(_INVALID)
        model_config: dict[str, object] = {
            "max_tokens": 4096,
            "temperature": 0,
            "reasoning_effort": "low",
        }
        corpus = load_json(Path(args.corpus))
        prepare_matrix(corpus)
        build_manifest(
            corpus,
            model_id=args.model_id,
            region=args.region,
            model_config=model_config,
        )
        rates = load_json(Path(args.rates)) if args.rates is not None else None
        if rates is not None:
            parse_rates(rates, model_id=args.model_id, region=args.region)
        database_url = None
        endpoint = None
        if args.local_services:
            database_url = os.environ.get("FEWIA_EVALUATION_DATABASE_URL")
            endpoint = os.environ.get("FEWIA_EVALUATION_FLOCI_ENDPOINT")
            if not database_url or endpoint not in ALLOWED_ENDPOINTS:
                raise ValueError(_INVALID)
            _validated_url(database_url)
        return EvaluationOptions(
            corpus=corpus,
            rates=rates,
            output_dir=Path(args.output_dir),
            revision=args.revision,
            model_id=args.model_id,
            region=args.region,
            model_config=model_config,
            profile_name=os.environ.get("AWS_PROFILE"),
            database_url=database_url,
            endpoint=endpoint,
            live_bedrock=args.live_bedrock,
        )
    except Exception:  # noqa: BLE001
        raise ValueError(_INVALID) from None
