import builtins
import json
import os
import socket
import sys
import traceback
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import NoReturn, cast

import pytest

from app import evaluation_cli_config as cli
from app import evaluation_database
from app.evaluation_matrix import prepare_matrix
from app.providers import bedrock, local_sqs

CORPUS = Path(__file__).parent / "evaluation" / "scenarios.json"
REVISION = "40d41fdec79d7c24e964c570d3afe19328addb74"
MODEL_ID = "us.amazon.nova-2-lite-v1:0"
DATABASE_URL = "postgresql+psycopg://localhost/fewia_eval_cli"
ENDPOINT = "http://localhost:4566"


@pytest.fixture
def cli_args(tmp_path: Path) -> list[str]:
    return [
        "--corpus",
        str(CORPUS),
        "--output-dir",
        str(tmp_path / "output"),
        "--revision",
        REVISION,
    ]


@pytest.fixture
def rates() -> dict[str, object]:
    return {
        "model_id": MODEL_ID,
        "region": "us-east-1",
        "currency": "USD",
        "input_usd_per_1000": "0.0003300000",
        "output_usd_per_1000": "0.0027500000",
        "source_url": "https://pricing.us-east-1.amazonaws.com/index.json",
        "source_version": "test-rates-v1",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def _assert_invalid(argv: list[str], *, fixture: bool = True) -> None:
    with pytest.raises(ValueError, match="^Invalid evaluation CLI input$") as error:
        cli.load_options(argv, fixture=fixture)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    rendered = "".join(traceback.format_exception(error.value))
    assert "private-input-marker" not in rendered


def test_live_bedrock_requires_explicit_opt_in(cli_args: list[str]) -> None:
    _assert_invalid(cli_args, fixture=False)
    options = cli.load_options(cli_args + ["--live-bedrock"])
    assert options.live_bedrock is True


def test_fixture_mode_is_programmatic_and_honest(cli_args: list[str]) -> None:
    options = cli.load_options(cli_args, fixture=True)
    assert options.live_bedrock is False
    _assert_invalid(cli_args + ["--live-bedrock"])
    _assert_invalid(cli_args + ["--fixture"])


@pytest.mark.parametrize("fixture", [None, 0, 1, "fixture"])
def test_fixture_requires_a_boolean(cli_args: list[str], fixture: object) -> None:
    _assert_invalid(cli_args, fixture=cast(bool, fixture))


def test_defaults_validate_real_corpus_and_fixed_config(cli_args: list[str]) -> None:
    options = cli.load_options(cli_args, fixture=True)
    assert options.model_id == MODEL_ID
    assert options.region == "us-east-1"
    assert options.revision == REVISION
    assert options.output_dir == Path(cli_args[3])
    assert options.rates is None
    assert options.model_config == {
        "max_tokens": 4096,
        "temperature": 0,
        "reasoning_effort": "low",
    }
    assert type(options.model_config["max_tokens"]) is int
    assert type(options.model_config["temperature"]) is int
    assert options.corpus["version"] == "grocery-eval-v1"
    assert len(prepare_matrix(options.corpus)) == 138
    assert not options.output_dir.exists()
    with pytest.raises(FrozenInstanceError):
        options.revision = "0" * 40  # type: ignore[misc]


def test_config_and_corpus_are_fresh_for_each_load(cli_args: list[str]) -> None:
    first = cli.load_options(cli_args, fixture=True)
    first.model_config["max_tokens"] = 1
    first.corpus.clear()
    second = cli.load_options(cli_args, fixture=True)
    assert second.model_config["max_tokens"] == 4096
    assert second.corpus["version"] == "grocery-eval-v1"


def test_explicit_supported_model_and_west_region(cli_args: list[str]) -> None:
    options = cli.load_options(
        cli_args + ["--model-id", MODEL_ID, "--region", "us-west-2"], fixture=True
    )
    assert options.model_id == MODEL_ID
    assert options.region == "us-west-2"


@pytest.mark.parametrize(
    "extra",
    [
        ["--model-id", "us.openai.gpt-6-luna"],
        ["--model-id", "amazon.nova-2-lite-v1:0"],
        ["--model-id", "arn:aws:bedrock:us-east-1:000000000000:inference-profile/x"],
        ["--model-id", MODEL_ID.upper()],
        ["--model-id", MODEL_ID + " "],
        ["--region", "eu-west-1"],
        ["--region", "US-EAST-1"],
        ["--region", "us-east-1 "],
        ["--revision", REVISION.upper()],
        ["--revision", "a" * 39],
        ["--revision", "a" * 41],
        ["--revision", "g" * 40],
        ["--revision", REVISION + "\n"],
        ["--revision", "private-input-marker"],
        ["--max-tokens", "4096"],
        ["--temperature", "0"],
        ["--reasoning-effort", "low"],
        ["--model-config", "{}"],
        ["--profile", "private-input-marker"],
        ["--unknown", "private-input-marker"],
        ["private-input-marker"],
        ["--live"],
        ["--region"],
        ["--live-bedrock=private-input-marker"],
        ["--output-dir", ""],
        ["--output-dir", "\0"],
    ],
)
def test_invalid_values_and_arguments_are_silent(
    cli_args: list[str], extra: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_invalid(cli_args + extra)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("index", [0, 2, 4])
def test_required_arguments_are_enforced(cli_args: list[str], index: int) -> None:
    _assert_invalid(cli_args[:index] + cli_args[index + 2 :])


def test_default_argv_reads_process_arguments(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["fewia-evaluation", *cli_args, "--live-bedrock"])
    assert cli.load_options().revision == REVISION


def test_help_exits_normally_without_reading_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("help read a file")

    monkeypatch.setattr(cli, "load_json", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.load_options(["--help"])
    assert error.value.code == 0
    captured = capsys.readouterr()
    assert "--live-bedrock" in captured.out
    assert "--fixture" not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        '{"private-input-marker":',
        '{"version":"grocery-eval-v1","version":"grocery-eval-v1"}',
        '{"amount":NaN}',
        '{"amount":Infinity}',
        '{"amount":1e9999}',
        '{"reasoningContent":"private-input-marker"}',
    ],
)
def test_invalid_corpus_files_have_static_errors(
    cli_args: list[str], tmp_path: Path, raw: str
) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(raw, encoding="utf-8")
    cli_args[1] = str(path)
    _assert_invalid(cli_args)


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink"])
def test_unavailable_corpus_paths_have_static_errors(
    cli_args: list[str], tmp_path: Path, kind: str
) -> None:
    path = tmp_path / "private-input-marker"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(CORPUS)
    cli_args[1] = str(path)
    _assert_invalid(cli_args)


def test_rates_are_loaded_and_validated(
    cli_args: list[str], tmp_path: Path, rates: dict[str, object]
) -> None:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(rates), encoding="utf-8")
    options = cli.load_options(cli_args + ["--rates", str(path)], fixture=True)
    assert options.rates == rates
    assert options.rates["input_usd_per_1000"] == "0.0003300000"
    _assert_invalid(cli_args + ["--rates", str(path), "--region", "us-west-2"])


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("model_id", "private-input-marker"),
        ("region", "us-west-2"),
        ("currency", "EUR"),
        ("input_usd_per_1000", "NaN"),
        ("output_usd_per_1000", "-1"),
        ("input_usd_per_1000", 0.5),
        ("source_url", "http://private-input-marker.example"),
        ("published_at", "invalid"),
        ("extra", "private-input-marker"),
    ],
)
def test_invalid_rates_have_static_errors(
    cli_args: list[str],
    tmp_path: Path,
    rates: dict[str, object],
    key: str,
    value: object,
) -> None:
    rates[key] = value
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(rates), encoding="utf-8")
    _assert_invalid(cli_args + ["--rates", str(path)])


def test_unavailable_rates_have_static_errors(
    cli_args: list[str], tmp_path: Path
) -> None:
    _assert_invalid(cli_args + ["--rates", str(tmp_path / "private-input-marker")])


def test_local_environment_is_ignored_without_flag(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "profile-marker")
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", "private-input-marker")
    monkeypatch.setenv("FEWIA_EVALUATION_FLOCI_ENDPOINT", "private-input-marker")
    real_get = os.environ.get
    reads: list[str] = []

    def checked_get(key: str, default: str | None = None) -> str | None:
        if key.startswith(("AWS_", "FEWIA_")):
            reads.append(key)
            assert key == "AWS_PROFILE"
            return real_get(key, default)
        return default

    with monkeypatch.context() as patch:
        patch.setattr(os.environ, "get", checked_get)
        options = cli.load_options(cli_args, fixture=True)
    assert reads == ["AWS_PROFILE"]
    assert options.profile_name == "profile-marker"
    assert options.database_url is None
    assert options.endpoint is None


def test_missing_aws_profile_does_not_use_alternate_profile_environment(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_PROFILE", "ignored-profile")
    options = cli.load_options(cli_args, fixture=True)
    assert options.profile_name is None


def test_local_services_accept_host_mapped_floci_endpoint(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("FEWIA_EVALUATION_FLOCI_ENDPOINT", "http://127.0.0.1:4567")
    options = cli.load_options(cli_args + ["--local-services"], fixture=True)
    assert options.database_url == DATABASE_URL
    assert options.endpoint == "http://127.0.0.1:4567"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://0.0.0.0:4567",
        "http://127.0.0.1:4568",
        "https://127.0.0.1:4567",
        "http://floci:4567",
    ],
)
def test_local_services_reject_near_miss_floci_endpoints(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("FEWIA_EVALUATION_FLOCI_ENDPOINT", endpoint)
    _assert_invalid(cli_args + ["--local-services"])


@pytest.mark.parametrize("endpoint", sorted(local_sqs.ALLOWED_ENDPOINTS))
def test_local_services_require_flag_and_hide_inputs_in_repr(
    cli_args: list[str], monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "profile-marker")
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("FEWIA_EVALUATION_FLOCI_ENDPOINT", endpoint)
    options = cli.load_options(cli_args + ["--local-services"], fixture=True)
    assert options.database_url == DATABASE_URL
    assert options.endpoint == endpoint
    rendered = repr(options)
    for hidden in ("scenarios", "profile-marker", DATABASE_URL, endpoint):
        assert hidden not in rendered
    assert "profile_name=" not in rendered
    assert "database_url=" not in rendered
    assert "endpoint=" not in rendered
    assert "corpus=" not in rendered


@pytest.mark.parametrize(
    ("database", "endpoint"),
    [
        (None, ENDPOINT),
        (DATABASE_URL, None),
        ("", ENDPOINT),
        ("private-input-marker", ENDPOINT),
        ("sqlite://", ENDPOINT),
        ("postgresql+psycopg://remote.example/fewia_eval", ENDPOINT),
        ("postgresql+psycopg://localhost/fewia", ENDPOINT),
        ("postgresql+psycopg://localhost/fewia_eval?sslmode=require", ENDPOINT),
        ("postgresql+psycopg://localhost:private-input-marker/fewia_eval", ENDPOINT),
        (DATABASE_URL, "https://localhost:4566"),
        (DATABASE_URL, "http://remote.example:4566"),
        (DATABASE_URL, ENDPOINT + "/"),
    ],
)
def test_invalid_local_service_configuration_has_static_errors(
    cli_args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    database: str | None,
    endpoint: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key, value in (
        ("FEWIA_EVALUATION_DATABASE_URL", database),
        ("FEWIA_EVALUATION_FLOCI_ENDPOINT", endpoint),
    ):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    _assert_invalid(cli_args + ["--local-services"])
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_validation_reads_only_inputs_without_services_or_writes(
    cli_args: list[str],
    tmp_path: Path,
    rates: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(rates), encoding="utf-8")
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("FEWIA_EVALUATION_FLOCI_ENDPOINT", ENDPOINT)
    real_open = os.open
    opened: list[Path] = []

    def checked_open(file: Path, flags: int) -> int:
        assert file in {CORPUS, path}
        assert flags & os.O_ACCMODE == os.O_RDONLY
        assert not flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        opened.append(file)
        return real_open(file, flags)

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("validation initialized a service or wrote a file")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", checked_open)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "mkdir", forbidden)
        patch.setattr(os, "write", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(bedrock.boto3, "Session", forbidden)
        patch.setattr(bedrock, "BedrockConverseProvider", forbidden)
        patch.setattr(local_sqs, "LocalSqsSender", forbidden)
        patch.setattr(evaluation_database, "create_engine", forbidden)
        options = cli.load_options(
            cli_args + ["--rates", str(path), "--local-services", "--live-bedrock"]
        )
    assert opened == [CORPUS, path]
    assert not options.output_dir.exists()


@pytest.mark.parametrize("helper", ["prepare_matrix", "build_manifest", "parse_rates"])
def test_validator_failures_are_sanitized(
    cli_args: list[str],
    tmp_path: Path,
    rates: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    helper: str,
) -> None:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(rates), encoding="utf-8")

    def invalid(*_args: object, **_kwargs: object) -> NoReturn:
        raise ValueError("private-input-marker")

    monkeypatch.setattr(cli, helper, invalid)
    _assert_invalid(cli_args + ["--rates", str(path)])
