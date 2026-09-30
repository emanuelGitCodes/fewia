import ast
import re
from pathlib import Path

import pytest

from app.domain.supermarket_estimate import SPOONACULAR_COST_NOTICE
from app.services.meal_nutrition import NOTICE, PORTION_NOTICE

FRONTEND_TYPES = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "apiTypes.ts"
)


@pytest.mark.parametrize(
    ("frontend_name", "backend_notice"),
    [
        ("NUTRITION_NOTICE", NOTICE),
        ("NUTRITION_PORTION_NOTICE", PORTION_NOTICE),
        ("SPOONACULAR_COST_NOTICE", SPOONACULAR_COST_NOTICE),
    ],
)
def test_frontend_notice_matches_backend(
    frontend_name: str, backend_notice: str
) -> None:
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    match = re.search(
        rf"export\s+const\s+{re.escape(frontend_name)}\s*=\s*"
        r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')",
        source,
    )

    assert match is not None, f"Missing frontend constant {frontend_name}"
    assert ast.literal_eval(match.group(1)) == backend_notice
