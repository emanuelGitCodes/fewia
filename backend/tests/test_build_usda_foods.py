import gzip
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from app.domain.usda_foods import BUNDLE_VERSION, COLUMNS, load_bundle

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_usda_foods.py"
_FIXTURE = Path(__file__).parent / "fixtures" / "usda_sr"
_SHA = "ab" * 32
_CURATED_FDC_IDS = {174036, 173110, 167902, 168314, 171505, 175167}
_EXPECTED_ROWS = [
    [
        100001,
        "Tofu, raw, firm, prepared with calcium sulfate",
        16,
        76,
        8080,
        4780,
        1870,
        7,
    ],
    [100002, "Tofu, fried", 16, 270, 18800, 20200, 8880, 16],
    [100003, "Tempeh", 16, 192, 20300, 10800, 7640, 9],
    [100004, "Cheese, cheddar", 1, 403, 22900, 33300, 3090, 653],
    [100005, "Cheese, mozzarella, whole milk", 1, 300, 22200, 22400, 2190, 627],
    [100006, "Cheese, feta", 1, 264, 14200, 21300, 4090, 917],
    [
        100007,
        "Beans, kidney, raw (Includes foods for USDA's Food Distribution Program)",
        16,
        337,
        23600,
        830,
        61300,
        24,
    ],
    [100008, "Beans, pinto, raw", 16, 347, 21400, 1230, 62600, 12],
    [100010, "Rice, white, raw", 20, 365, 7130, 660, 80000, 5],
    [100012, "Beef, rounded", 13, 200, 20000, 12000, 0, 60],
    [100013, "Rounding test", 9, 53, 9045, 1, 0, 2],
    [100014, "Chicken, thigh, raw", 5, 121, 19700, 4300, 0, 94],
    [100015, "Chicken, thigh, cooked, roasted", 5, 232, 26000, 13400, 0, 120],
    [100016, "Chicken, breast, raw", 5, 114, 21200, 2600, 0, 70],
    [100017, "Beans, kidney", 16, 330, 22000, 1000, 60000, 20],
    [100018, "Cheese, swiss", 1, 380, 27000, 28000, 5400, 192],
    [100019, "Milk, whole", 1, 61, 3150, 3270, 4780, 43],
    [100020, "Cheese substitute, mozzarella", 1, 250, 15000, 18000, 4000, 500],
    [100021, "Spices, pepper", 2, 251, 10400, 3260, 64800, 20],
    [100022, "Pork, test", 10, 263, 16900, 21200, 0, 56],
]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_usda_foods", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_script()


def run(out: Path, directory: Path = _FIXTURE) -> None:
    assert build.main([str(directory), str(out), "--source-sha256", _SHA]) == 0


def payload_of(path: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(gzip.decompress(path.read_bytes()))
    return loaded


def test_two_runs_are_byte_identical_with_a_zero_gzip_mtime(tmp_path: Path) -> None:
    run(tmp_path / "a.json.gz")
    run(tmp_path / "b.json.gz")
    first = (tmp_path / "a.json.gz").read_bytes()
    assert first == (tmp_path / "b.json.gz").read_bytes()
    assert first[:2] == b"\x1f\x8b"
    assert first[4:8] == b"\x00\x00\x00\x00"


def test_output_has_the_header_and_the_expected_sorted_rows(tmp_path: Path) -> None:
    run(tmp_path / "out.json.gz")
    payload = payload_of(tmp_path / "out.json.gz")
    assert payload == {
        "version": "usda-sr-legacy-2018-04-v1",
        "source": "USDA FoodData Central SR Legacy 2018-04",
        "source_sha256": _SHA,
        "columns": [
            "fdc_id",
            "description",
            "category_id",
            "energy_kcal",
            "protein_mg",
            "fat_mg",
            "carbohydrate_mg",
            "sodium_mg",
        ],
        "rows": _EXPECTED_ROWS,
    }
    assert payload["version"] == BUNDLE_VERSION
    assert payload["columns"] == COLUMNS


def test_the_row_count_is_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(tmp_path / "out.json.gz")
    assert capsys.readouterr().out.strip() == str(len(_EXPECTED_ROWS))


def test_drops_categories_incomplete_foods_and_curated_ids(tmp_path: Path) -> None:
    run(tmp_path / "out.json.gz")
    rows = cast(list[list[object]], payload_of(tmp_path / "out.json.gz")["rows"])
    built = {row[0] for row in rows}
    assert built == {row[0] for row in _EXPECTED_ROWS}
    assert 100009 not in built  # category 18 is dropped
    assert 100011 not in built  # no sodium
    assert 100023 not in built  # a blank energy amount
    assert 174036 not in built  # a curated fdc_id


def test_curated_fdc_ids_are_read_from_the_curated_file() -> None:
    assert build.curated_fdc_ids() == _CURATED_FDC_IDS


def test_exclusion_is_by_the_given_ids_only() -> None:
    rows = build.build_rows(_FIXTURE, set())
    assert 174036 in {row[0] for row in rows}
    assert len(rows) == len(_EXPECTED_ROWS) + 1


def test_rounding_is_half_up_on_milligrams() -> None:
    rows = {item[0]: item for item in build.build_rows(_FIXTURE, set())}
    assert rows[100013][3:] == [53, 9045, 1, 0, 2]
    assert build._integer("9.045", 1000) == 9045
    assert build._integer("0.0005", 1000) == 1
    assert build._integer("0.0004", 1000) == 0
    assert build._integer("2.5", 1) == 3


@pytest.mark.parametrize("amount", ["-1", "abc", "NaN", "Infinity"])
def test_bad_amounts_are_rejected(amount: str) -> None:
    with pytest.raises(ValueError, match="bad amount"):
        build._integer(amount, 1)


@pytest.mark.parametrize("digest", ["", "abc", "A" * 64, "g" * 64, "a" * 63])
def test_a_bad_source_digest_is_rejected(tmp_path: Path, digest: str) -> None:
    out = tmp_path / "x.json.gz"
    with pytest.raises(SystemExit):
        build.main([str(_FIXTURE), str(out), "--source-sha256", digest])
    assert not out.exists()


def test_a_directory_without_the_kept_categories_is_rejected(tmp_path: Path) -> None:
    for name in ("food.csv", "food_nutrient.csv"):
        (tmp_path / name).write_bytes((_FIXTURE / name).read_bytes())
    short = '"id","code","description"\n"1","0100","x"\n'
    (tmp_path / "food_category.csv").write_text(short)
    with pytest.raises(ValueError, match="lacks categories"):
        build.build_rows(tmp_path, set())


def test_a_duplicate_nutrient_row_is_rejected(tmp_path: Path) -> None:
    for name in ("food.csv", "food_category.csv"):
        (tmp_path / name).write_bytes((_FIXTURE / name).read_bytes())
    extra = '"900","100001","1008","77","1"\n'
    text = (_FIXTURE / "food_nutrient.csv").read_text()
    (tmp_path / "food_nutrient.csv").write_text(text + extra)
    with pytest.raises(ValueError, match="duplicate nutrient"):
        build.build_rows(tmp_path, set())


def test_the_built_file_loads_with_the_runtime_loader(tmp_path: Path) -> None:
    run(tmp_path / "out.json.gz")
    foods = load_bundle(tmp_path / "out.json.gz")
    assert [food.facts.fdc_id for food in foods] == [row[0] for row in _EXPECTED_ROWS]
    names = {food.facts.fdc_id: food.ingredient.name for food in foods}
    assert names[100001] == "tofu (raw, firm, prepared with calcium sulfate)"
    assert names[100003] == "tempeh"
    assert names[100007] == "beans (kidney, raw)"


def test_the_script_never_imports_anything_outside_the_standard_library() -> None:
    imported = {
        line.split()[1].split(".")[0]
        for line in _SCRIPT.read_text().splitlines()
        if line.startswith(("import ", "from "))
    }
    assert imported <= {
        "argparse",
        "csv",
        "gzip",
        "json",
        "re",
        "sys",
        "decimal",
        "pathlib",
    }
