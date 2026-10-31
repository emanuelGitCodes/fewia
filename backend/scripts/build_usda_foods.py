"""Build the bundled USDA SR Legacy foods file from the FoodData Central CSVs.

Usage: build_usda_foods.py <sr_csv_dir> <out.json.gz> --source-sha256 <hex>

Stdlib only. The input is read as data and never executed.
"""

import argparse
import csv
import gzip
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

VERSION = "usda-sr-legacy-2018-04-v1"
SOURCE = "USDA FoodData Central SR Legacy 2018-04"
COLUMNS = [
    "fdc_id",
    "description",
    "category_id",
    "energy_kcal",
    "protein_mg",
    "fat_mg",
    "carbohydrate_mg",
    "sodium_mg",
]
KEPT_CATEGORIES = frozenset({1, 2, 4, 5, 7, 9, 10, 11, 12, 13, 15, 16, 17, 20})
# nutrient id -> (multiplier to the stored unit)
NUTRIENTS = {1008: 1, 1003: 1000, 1004: 1000, 1005: 1000, 1093: 1}
CURATED_FILE = (
    Path(__file__).resolve().parent.parent / "app" / "domain" / "curated_foods.json"
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _integer(amount: str, multiplier: int) -> int:
    try:
        value = Decimal(amount) * multiplier
    except InvalidOperation:
        raise ValueError(f"bad amount {amount!r}") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"bad amount {amount!r}")
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def curated_fdc_ids(path: Path = CURATED_FILE) -> set[int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(food["fdc_id"]) for food in payload["foods"]}


def build_rows(directory: Path, excluded: set[int]) -> list[list[object]]:
    categories = {int(row["id"]) for row in _read(directory / "food_category.csv")}
    missing = KEPT_CATEGORIES - categories
    if missing:
        raise ValueError(f"food_category.csv lacks categories {sorted(missing)}")
    foods: dict[int, tuple[str, int]] = {}
    for row in _read(directory / "food.csv"):
        category = row["food_category_id"].strip()
        if not category.isdigit() or int(category) not in KEPT_CATEGORIES:
            continue
        fdc_id = int(row["fdc_id"])
        if fdc_id in excluded:
            continue
        if fdc_id in foods:
            raise ValueError(f"duplicate food {fdc_id}")
        foods[fdc_id] = (" ".join(row["description"].split()), int(category))
    amounts: dict[int, dict[int, int]] = {}
    for row in _read(directory / "food_nutrient.csv"):
        nutrient, fdc_id = int(row["nutrient_id"]), int(row["fdc_id"])
        amount = row["amount"].strip()
        if nutrient not in NUTRIENTS or fdc_id not in foods or not amount:
            continue
        found = amounts.setdefault(fdc_id, {})
        if nutrient in found:
            raise ValueError(f"duplicate nutrient {nutrient} for food {fdc_id}")
        found[nutrient] = _integer(amount, NUTRIENTS[nutrient])
    rows: list[list[object]] = []
    for fdc_id in sorted(foods):
        found = amounts.get(fdc_id, {})
        description, category = foods[fdc_id]
        if description and set(found) == set(NUTRIENTS):
            values = [found[nutrient] for nutrient in NUTRIENTS]
            rows.append([fdc_id, description, category, *values])
    return rows


def encode(rows: list[list[object]], source_sha256: str) -> bytes:
    payload = {
        "version": VERSION,
        "source": SOURCE,
        "source_sha256": source_sha256,
        "columns": COLUMNS,
        "rows": rows,
    }
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return gzip.compress(text.encode("utf-8"), mtime=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sr_csv_dir", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{64}", args.source_sha256):
        parser.error("--source-sha256 must be 64 lowercase hex characters")
    rows = build_rows(args.sr_csv_dir, curated_fdc_ids())
    args.out.write_bytes(encode(rows, args.source_sha256))
    print(len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
