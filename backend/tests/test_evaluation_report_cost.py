from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluate import main as evaluate_main
from app.evaluation_report import main
from app.evaluation_report_values import INVALID

DIGEST = "0123456789abcdef0123456789abcdef01234567"
HASH64 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SECRET = "do-not-echo-raw-input"
MARKER = "FIXTURE_SECRET_MARKER"
FAKE = "deterministic_fake_provider"
MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-east-1"
KNOWN = "0.13163909"
SOURCE_URL = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
    "AmazonBedrock/current/us-east-1/index.json"
)
PRICING = Path(__file__).parent / "evaluation/pricing/nova2-lite-use1-20260922.json"


def _slot(
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    *,
    unknown: bool = False,
) -> dict[str, object]:
    usage: dict[str, object] | None
    if unknown:
        usage = None
    else:
        usage = {
            "inputTokens": 0 if input_tokens is None else input_tokens,
            "outputTokens": 0 if output_tokens is None else output_tokens,
        }
    return {
        "status": "scored",
        "report": {"checks": {"accepted": True}, "evidence_class": FAKE},
        "observation": {
            "status": "completed",
            "turns": [
                {
                    "status": "completed",
                    "elapsed_seconds": 1.0,
                    "result": {"usage": usage},
                }
            ],
        },
    }


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "metrics_status": "unassessed",
        "revision": DIGEST,
        "model_id": MODEL_ID,
        "source_region": REGION,
        "slots": [_slot()],
        "prompt_hash": HASH64,
        "catalog_version": "sample-prices-v1",
        "estimated_usd": "999.99",
        "known_subset_estimated_usd": "999.99",
    }
    body.update(overrides)
    return body


def _write(path: Path, body: dict[str, object]) -> None:
    path.write_text(json.dumps(body), encoding="utf-8")


def _argv(source: Path, output: Path, rates: Path | None = None) -> list[str]:
    args = ["--input", str(source), "--output", str(output)]
    if rates is not None:
        args.extend(["--rates", str(rates)])
    return args


def _static(text: str, *paths: Path) -> None:
    assert "Traceback" not in text
    assert SECRET not in text
    assert MARKER not in text
    for path in paths:
        assert str(path) not in text
        assert path.name not in text


def _ok(capsys: pytest.CaptureFixture[str], *paths: Path) -> str:
    captured = capsys.readouterr()
    assert captured.err == ""
    _static(captured.out, *paths)
    return captured.out


def _fail(capsys: pytest.CaptureFixture[str], expected: str, *paths: Path) -> None:
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == expected
    _static(captured.err, *paths)


def _provider_boom(*_a: object, **_k: object) -> None:
    raise AssertionError("provider")


def test_fixture_batch_without_model_rejects_rates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.evaluate.build_bedrock", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_bedrock", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_plaid", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_instacart", _provider_boom)
    batch = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    assert (
        evaluate_main(
            ["--mode", "fixture", "--revision", DIGEST, "--output", str(batch)]
        )
        == 0
    )
    capsys.readouterr()
    original = batch.read_bytes()
    rates_original = PRICING.read_bytes()
    assert main(_argv(batch, output, PRICING)) == 1
    _fail(capsys, INVALID, batch, output, PRICING)
    assert not output.exists()
    assert batch.read_bytes() == original
    assert PRICING.read_bytes() == rates_original


def test_twenty_four_known_slots_use_fixture_rates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    slots = [_slot(0, 0) for _ in range(23)] + [_slot(166198, 27925)]
    original_rates = PRICING.read_bytes()
    _write(source, _payload(slots=slots))
    original = source.read_bytes()
    assert main(_argv(source, output, PRICING)) == 0
    text = output.read_text(encoding="utf-8")
    out = _ok(capsys, source, output, PRICING)
    assert "evaluation report written" in out
    assert "slots: 24" in out
    assert "## Estimated model cost" in text
    assert f"estimated_usd: {KNOWN}" in text
    assert f"known_subset_estimated_usd: {KNOWN}" in text
    assert "currency: `USD`" in text
    assert "input_usd_per_million: 0.33" in text
    assert "output_usd_per_million: 2.75" in text
    assert f"model_id: `{MODEL_ID}`" in text
    assert f"source_region: `{REGION}`" in text
    assert "routing: `geographic`" in text
    assert "service_tier: `standard`" in text
    assert "effective_date: `2026-09-01`" in text
    assert "retrieved_date: `2026-09-22`" in text
    assert f"source_url: [source]({SOURCE_URL})" in text
    assert "Text input/output token estimate only." in text
    assert "Not an AWS invoice or observed billing." in text
    assert "999.99" not in text
    assert source.read_bytes() == original
    assert PRICING.read_bytes() == original_rates
    assert not output.with_name(output.name + ".tmp").exists()


def test_partial_unknown_keeps_overall_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    slots = [_slot(166198, 27925)]
    slots.extend(_slot(0, 0) for _ in range(11))
    slots.extend(_slot(unknown=True) for _ in range(12))
    _write(source, _payload(slots=slots))
    original = source.read_bytes()
    original_rates = PRICING.read_bytes()
    assert main(_argv(source, output, PRICING)) == 0
    text = output.read_text(encoding="utf-8")
    assert "slots: 24" in _ok(capsys, source, output, PRICING)
    assert "estimated_usd: unknown" in text
    assert f"known_subset_estimated_usd: {KNOWN}" in text
    assert not any(line.startswith("estimated_usd: 0") for line in text.splitlines())
    assert source.read_bytes() == original
    assert PRICING.read_bytes() == original_rates


@pytest.mark.parametrize(
    "override",
    [
        {"model_id": "other-model"},
        {"source_region": "us-west-2"},
        {"service_tier": "priority"},
    ],
)
def test_mismatched_model_region_and_service_reject(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    override: dict[str, object],
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    _write(source, _payload(**override))
    original = source.read_bytes()
    original_rates = PRICING.read_bytes()
    assert main(_argv(source, output, PRICING)) == 1
    _fail(capsys, INVALID, source, output, PRICING)
    assert not output.exists()
    assert source.read_bytes() == original
    assert PRICING.read_bytes() == original_rates


def test_missing_source_region_with_rates_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload(source_region=None))
    original = source.read_bytes()
    assert main(_argv(source, output, PRICING)) == 1
    _fail(capsys, INVALID, source, output, PRICING)
    assert not output.exists()
    assert source.read_bytes() == original
    omitted = tmp_path / "omitted.json"
    body = _payload()
    del body["source_region"]
    _write(omitted, body)
    omitted_out = tmp_path / "omitted.md"
    assert main(_argv(omitted, omitted_out, PRICING)) == 1
    _fail(capsys, INVALID, omitted, omitted_out, PRICING)
    assert not omitted_out.exists()


def test_bad_rates_json_and_source_url_are_static(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload())
    original = source.read_bytes()
    bad_json = tmp_path / f"{SECRET}.json"
    bad_json.write_text("{" + SECRET, encoding="utf-8")
    assert main(_argv(source, output, bad_json)) == 1
    _fail(capsys, INVALID, source, output, bad_json)
    assert not output.exists()
    assert source.read_bytes() == original
    bad_url = tmp_path / "rates.json"
    rates = json.loads(PRICING.read_text(encoding="utf-8"))
    rates["source_url"] = f"https://user:pass@example.invalid/{MARKER}"
    _write(bad_url, rates)
    url_original = bad_url.read_bytes()
    assert main(_argv(source, output, bad_url)) == 1
    _fail(capsys, INVALID, source, output, bad_url)
    assert not output.exists()
    assert source.read_bytes() == original
    assert bad_url.read_bytes() == url_original
    http = tmp_path / "http.json"
    rates["source_url"] = f"http://example.invalid/{MARKER}"
    _write(http, rates)
    http_original = http.read_bytes()
    original_rates = PRICING.read_bytes()
    assert main(_argv(source, output, http)) == 1
    _fail(capsys, INVALID, source, output, http)
    assert not output.exists()
    assert http.read_bytes() == http_original
    assert PRICING.read_bytes() == original_rates


def test_no_rates_cli_preserves_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload(model_id="eval-fake-v1", source_region="us-east-1"))
    original = source.read_bytes()
    assert main(_argv(source, output)) == 0
    text = output.read_text(encoding="utf-8")
    out = _ok(capsys, source, output)
    assert "evaluation report written" in out
    assert "slots: 1" in out
    assert "Global quality: UNASSESSED" in text
    assert "## Estimated model cost" not in text
    assert "estimated_usd:" not in text
    assert "999.99" not in text
    assert source.read_bytes() == original
    assert not output.with_name(output.name + ".tmp").exists()


def test_help_lists_rates(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    help_text = _ok(capsys)
    assert "--input" in help_text
    assert "--output" in help_text
    assert "--rates" in help_text
