import json
import re
from pathlib import Path

import pytest

from app.agent.meal_search_rank import stem
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.evaluation_retrieval import main

QUERIES = Path(__file__).parent / "evaluation" / "retrieval_queries.json"


def test_query_file_states_its_proxy_and_relevance_follows_the_rule() -> None:
    data = json.loads(QUERIES.read_text(encoding="utf-8"))
    assert data["relevance"] == "recipe id holds every query word"
    assert len(data["queries"]) == 15
    for row in data["queries"]:
        stems = {stem(w) for w in row["query"].lower().split()}
        expected = [
            r
            for r in SUPPORTED_RECIPE_IDS
            if stems <= {stem(t) for t in re.findall(r"[a-z]+", r)}
        ]
        assert row["relevant"] == expected


def test_cli_reports_both_orders(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    assert main(["--queries", str(QUERIES), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    for order in ("bm25", "catalog_order"):
        assert set(report[order]) == {"recall_at_3", "mrr", "queries"}
        assert report[order]["queries"] == 15
        assert 0 <= report[order]["recall_at_3"] <= 1
        assert 0 <= report[order]["mrr"] <= 1


def test_cli_refuses_an_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text("keep", encoding="utf-8")
    assert main(["--queries", str(QUERIES), "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "keep"


def test_cli_exits_2_without_a_traceback_on_a_catalog_tool_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "blank.json"
    bad.write_text(
        json.dumps({"queries": [{"query": "   ", "relevant": ["bean_tacos"]}]}),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    assert main(["--queries", str(bad), "--output", str(output)]) == 2
    assert not output.exists()
    assert "Traceback" not in capsys.readouterr().err


def test_cli_rejects_invalid_queries(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"queries": [{"query": "rice", "relevant": ["nope"]}]}),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    assert main(["--queries", str(bad), "--output", str(output)]) == 2
    assert not output.exists()
    assert (
        main(["--queries", str(tmp_path / "missing.json"), "--output", str(output)])
        == 2
    )
