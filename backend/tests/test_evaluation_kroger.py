"""Tests for the deterministic Kroger evaluation. Everything here is invented."""

import json
import socket
from pathlib import Path

import pytest

from app import evaluation_kroger, kroger_cart
from app.evaluation_kroger import main, run_evaluation
from app.providers.kroger import KrogerCartUnknown, KrogerClient

ERROR_CLASSES = [
    "http_429",
    "http_401",
    "http_500",
    "http_503",
    "timeout",
    "connection_error",
    "malformed_json",
]


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def deny(*args: object, **kwargs: object) -> None:
        attempts.append("socket")
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    return attempts


def _measures(report: dict[str, object]) -> dict[str, dict[str, object]]:
    measures = report["measures"]
    assert isinstance(measures, dict)
    return measures


def _target(report: dict[str, object], name: str) -> dict[str, object]:
    targets = report["targets"]
    assert isinstance(targets, list)
    return next(t for t in targets if t["name"] == name)


def test_report_header_and_measure_names() -> None:
    report = run_evaluation()
    assert report["version"] == "kroger-eval-v1"
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert set(_measures(report)) == {
        "product_match",
        "cart_safety",
        "failure_handling",
        "secret_scan",
        "quote_label",
        "code_latency_ms",
    }
    targets = report["targets"]
    assert isinstance(targets, list)
    assert all(set(t) == {"name", "goal", "value", "status"} for t in targets)
    assert all(t["status"] == "PASS" for t in targets)


def test_product_match_values() -> None:
    match = _measures(run_evaluation())["product_match"]
    assert match["lines"] == 7
    assert match["matched"] == 4
    assert match["unmatched"] == 3
    assert match["rate"] == round(4 / 7, 4)
    assert "out_of_stock_chosen" not in match


def test_targets_for_product_match() -> None:
    report = run_evaluation()
    assert _target(report, "out_of_stock_chosen") == {
        "name": "out_of_stock_chosen",
        "goal": 0,
        "value": 0,
        "status": "PASS",
    }
    unmatched = _target(report, "unmatched_listed")
    assert unmatched["goal"] == 3
    assert unmatched["value"] == 3


def test_removed_stock_filter_fails_the_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kroger_cart, "OUT_OF_STOCK", "NO_SUCH_LEVEL")
    report = run_evaluation()
    chosen = _target(report, "out_of_stock_chosen")["value"]
    assert isinstance(chosen, int) and chosen > 0
    assert _target(report, "out_of_stock_chosen")["status"] == "FAIL"
    assert _target(report, "unmatched_listed")["status"] == "FAIL"


def test_cart_safety() -> None:
    report = run_evaluation()
    safety = _measures(report)["cart_safety"]
    assert safety["cart_requests_before_add"] == 0
    assert safety["cart_requests_by_add"] == 1
    assert safety["add_items_equal_preview"] is True
    assert _target(report, "cart_requests_before_add")["status"] == "PASS"
    assert _target(report, "add_items_equal_preview")["status"] == "PASS"


def test_failure_handling_rows() -> None:
    report = run_evaluation()
    rows = _measures(report)["failure_handling"]
    assert isinstance(rows, list)
    assert [row["error"] for row in rows] == ERROR_CLASSES
    for row in rows:
        assert row["status_class"] == "unavailable"
        assert row["partial_preview"] is False
        assert _target(report, f"partial_preview_{row['error']}")["status"] == "PASS"


def test_secret_scan_is_clean_and_can_detect() -> None:
    scan = _measures(run_evaluation())["secret_scan"]
    assert scan == {"preview": 0, "errors": 0, "report": 0, "count": 0}
    assert evaluation_kroger._hits(f"x {evaluation_kroger.APP_TOKEN} y") == 1
    assert evaluation_kroger._hits(f"Bearer {evaluation_kroger.CUSTOMER_TOKEN}") == 2


def test_quote_label() -> None:
    report = run_evaluation()
    assert _measures(report)["quote_label"] == {
        "store_label": True,
        "utc_read_time": True,
    }
    assert _target(report, "quote_store_label")["status"] == "PASS"
    assert _target(report, "quote_utc_read_time")["status"] == "PASS"


def test_code_latency_shape() -> None:
    report = run_evaluation()
    latency = _measures(report)["code_latency_ms"]
    assert latency["runs"] == 30
    assert latency["scope"] == "our code, synthetic transport, no network"
    p50, p95 = latency["p50"], latency["p95"]
    assert isinstance(p50, float) and isinstance(p95, float)
    assert 0 <= p50 <= p95
    targets = report["targets"]
    assert isinstance(targets, list)
    assert not any("latency" in str(t["name"]) for t in targets)


def test_cli_writes_report_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "kroger.json"
    assert main(["--output", str(path)]) == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["version"] == "kroger-eval-v1"
    assert capsys.readouterr().out.strip() == str(path)


def test_cli_exits_zero_when_a_measure_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kroger_cart, "OUT_OF_STOCK", "NO_SUCH_LEVEL")
    path = tmp_path / "failed.json"
    assert main(["--output", str(path)]) == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert any(t["status"] == "FAIL" for t in written["targets"])


def test_cli_exits_zero_when_add_to_cart_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: KrogerClient, token: str, items: object) -> None:
        raise KrogerCartUnknown

    monkeypatch.setattr(KrogerClient, "add_to_cart", boom)
    path = tmp_path / "cart.json"
    assert main(["--output", str(path)]) == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert _target(written, "add_items_equal_preview")["status"] == "FAIL"
    assert "did not confirm" not in path.read_text(encoding="utf-8")


def test_cli_exits_zero_when_attach_kroger_quote_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("invented quote failure")

    monkeypatch.setattr(evaluation_kroger, "attach_kroger_quote", boom)
    path = tmp_path / "quote.json"
    assert main(["--output", str(path)]) == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert _target(written, "quote_store_label")["status"] == "FAIL"
    assert _target(written, "quote_utc_read_time")["status"] == "FAIL"
    assert "invented quote failure" not in path.read_text(encoding="utf-8")


def test_injected_leak_fails_secret_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        evaluation_kroger,
        "_error_text",
        lambda error: f"leak {evaluation_kroger.APP_TOKEN}",
    )
    report = run_evaluation()
    target = _target(report, "secret_hits")
    value = target["value"]
    assert isinstance(value, int) and value > 0
    assert target["status"] == "FAIL"
    scan = _measures(report)["secret_scan"]
    assert scan["count"] == value


def test_cli_rejects_existing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "exists.json"
    path.write_text("keep", encoding="utf-8")
    assert main(["--output", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == "keep"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Invalid evaluation CLI input"


@pytest.mark.parametrize(
    "argv",
    [[], ["--output"], ["--bogus", "x"], ["--output", ""], ["-h"]],
)
def test_cli_rejects_invalid_input(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "Invalid evaluation CLI input"


def test_cli_rejects_missing_parent_directory(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path / "missing" / "out.json")]) == 2


def test_output_holds_no_descriptions_or_tokens(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    assert main(["--output", str(path)]) == 0
    text = path.read_text(encoding="utf-8")
    forbidden = [
        evaluation_kroger.CLIENT_ID,
        evaluation_kroger.CLIENT_SECRET,
        evaluation_kroger.APP_TOKEN,
        evaluation_kroger.CUSTOMER_TOKEN,
        "Bearer",
        "Authorization",
    ]
    forbidden.append(str(evaluation_kroger._QUOTE_PRODUCT["description"]))
    for products in evaluation_kroger.LINE_PRODUCTS.values():
        for product in products:
            forbidden.append(str(product["description"]))
            forbidden.append(str(product["upc"]))
    for value in forbidden:
        assert value not in text


def test_no_network_call_runs(no_sockets: list[str], tmp_path: Path) -> None:
    run_evaluation()
    assert main(["--output", str(tmp_path / "out.json")]) == 0
    assert no_sockets == []
    with pytest.raises(AssertionError):
        socket.create_connection(("127.0.0.1", 9))
    assert no_sockets == ["socket"]
