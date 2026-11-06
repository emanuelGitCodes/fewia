"""Compare the BM25 order of search_meals with catalog order, with no model call.

Relevance is a proxy: a recipe id holds every query word. The report holds ids
and numbers only.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from app.agent.catalog_tool import CatalogToolError, search_result_ids
from app.domain.grocery import SUPPORTED_RECIPE_IDS

RECALL_RANK = 3


class RetrievalInputError(ValueError):
    pass


def _fail(message: str) -> NoReturn:
    raise RetrievalInputError(message)


def load_queries(path: Path) -> list[tuple[str, frozenset[str]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        _fail("queries file is unreadable")
    rows = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        _fail("queries must be a non-empty list")
    queries: list[tuple[str, frozenset[str]]] = []
    for row in rows:
        if not isinstance(row, dict):
            _fail("each query must be an object")
        query, relevant = row.get("query"), row.get("relevant")
        if not isinstance(query, str) or not 1 <= len(query) <= 120:
            _fail("query must be a short string")
        if (
            not isinstance(relevant, list)
            or not relevant
            or not all(r in SUPPORTED_RECIPE_IDS for r in relevant)
        ):
            _fail("relevant must hold supported recipe ids")
        queries.append((query, frozenset(relevant)))
    return queries


def _metrics(
    queries: list[tuple[str, frozenset[str]]], rank: bool
) -> dict[str, float | int]:
    recall = 0.0
    reciprocal = 0.0
    for query, relevant in queries:
        ids = search_result_ids({"query": query}, rank=rank)
        recall += len(relevant.intersection(ids[:RECALL_RANK])) / len(relevant)
        for position, rid in enumerate(ids, start=1):
            if rid in relevant:
                reciprocal += 1 / position
                break
    count = len(queries)
    return {
        "recall_at_3": round(recall / count, 4),
        "mrr": round(reciprocal / count, 4),
        "queries": count,
    }


def evaluate(queries: list[tuple[str, frozenset[str]]]) -> dict[str, object]:
    return {
        "bm25": _metrics(queries, True),
        "catalog_order": _metrics(queries, False),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation_retrieval")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        report = evaluate(load_queries(args.queries))
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except (RetrievalInputError, CatalogToolError, OSError) as error:
        print(f"invalid input: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
