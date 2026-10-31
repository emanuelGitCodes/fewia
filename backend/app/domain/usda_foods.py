"""Bundled USDA SR Legacy foods. An absent bundle means zero USDA foods."""

import gzip
import json
import re
import zlib
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from app.domain.catalog import Ingredient
from app.domain.nutrition import NutritionFacts

BUNDLE_VERSION = "usda-sr-legacy-2018-04-v1"
DEFAULTS_VERSION = "usda-defaults-v1"
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
BUNDLE_PATH = Path(__file__).with_name("usda_foods.json.gz")
DEFAULTS_PATH = Path(__file__).with_name("usda_defaults.json")
KEPT_CATEGORIES = frozenset({1, 2, 4, 5, 7, 9, 10, 11, 12, 13, 15, 16, 17, 20})
_VEGAN_CATEGORIES = frozenset({9, 11, 12, 16, 20})
_VEGETARIAN_CATEGORIES = _VEGAN_CATEGORIES | {1}
_MEAT_INGREDIENTS = re.compile(
    r"\b(?:pork|beef|chicken|turkey|duck|goose|geese|lamb|veal|venison|bison|"
    r"buffalo|rabbit|goat|meat|poultry|"
    r"bacon|ham|sausage|frankfurter|pepperoni|salami|lard|tallow|gelatin|"
    r"fish|tuna|salmon|cod|anchov(?:y|ies)|sardines?|tilapia|haddock|pollock|"
    r"mackerel|herring|shrimp|prawns?|crab|lobster|clams?|oysters?|mussels?|"
    r"scallops?|squid|octopus|broth|stock)\b"
)
_VEGAN_INGREDIENTS = re.compile(
    r"\b(?:milk|buttermilk|butter|cream|cheese|yogurt|yoghurt|whey|casein|"
    r"caseinate|eggs?|albumen|honey)\b"
)
_PLANT_PHRASES = re.compile(
    r"\b(?:coconut milk, (?:raw,? |canned )?"
    r"\(?liquid expressed from grated meat and water\)?|"
    r"(?:peanut|almond|cashew|sunflower seed) butter|"
    r"(?:coconut|soy|soya|almond|oat|rice) milk|coconut cream|coconut meat|"
    r"(?:tofu|soy) yogurt|soybean, curd cheese|"
    r"oyster mushrooms?|mushrooms?, oyster|(?:vegetable|vegetarian) (?:broth|stock)|"
    r"(?:chicken|bacon|frankfurter),? meatless|"
    r"meatless (?:chicken|bacon|frankfurter))\b"
)
_EGG_FREE = re.compile(r"\b(?:without eggs?|no eggs?|egg free|eggless)\b")
_PLAIN_PREPARATION = re.compile(
    r"\b(?:prepared with (?:calcium sulfate(?: and magnesium chloride)?|"
    r"magnesium chloride|nigari|water)|with(?: added)? salt|solids and liquids)\b"
)
_DAIRY_EGG_PREPARATION = re.compile(
    r"\bwith (?:milk|buttermilk|butter|cream|cheese|yogurt|yoghurt|whey|"
    r"casein|caseinate|eggs?|albumen|honey)"
    r"(?: and (?:milk|buttermilk|butter|cream|cheese|yogurt|yoghurt|whey|"
    r"casein|caseinate|eggs?|albumen|honey|salt))*\b"
)
_MIXED_DESCRIPTION = re.compile(
    r"\b(?:with|prepared|recipe|and|mixed|mixture|soup|stew|salad|sauce|dinner|entree|"
    r"refried|flavored|flavoured|stuffed|filling)\b|\bbeans,? baked\b"
)
_ANIMAL_PREPARATIONS = re.compile(
    r"\b(?:(?:pasta|noodles?)\b.*\bfresh refrigerated|pancakes?|waffles?|fritters?|"
    r"crepes?|breaded|battered|tempura|dumplings?|gnocchi|meatless|veggie burgers?|"
    r"soyburgers?|meat (?:substitutes?|analogs?|analogues?)|croissants?|pastry|"
    r"pastries|biscuits?|muffins?|tortilla mix)\b"
)
_LARD_FAT = re.compile(r"\btortilla mix\b|\bshortening\b")
_VEGETABLE_SHORTENING = re.compile(r"\bvegetable shortening\b")
_RENNET_CHEESES = re.compile(
    r"\b(?:parmesan|romano|pecorino|grana|gruy[eè]re|emmental|manchego|gorgonzola)\b"
)
_MAX_CANDIDATES = 3
_SHORT_LIMIT = 60
_LONG_LIMIT = 90
_COMPOSITE = "composite"
_FILLER = frozenset(
    {
        "broilers or fryers",
        "separable lean and fat",
        "fresh",
        "all grades",
        "nfs",
    }
)


@dataclass(frozen=True)
class UsdaFood:
    ingredient: Ingredient
    facts: NutritionFacts
    description: str
    tokens: frozenset[str]
    head: frozenset[str]


def _fail(message: str) -> ValueError:
    return ValueError(f"USDA foods are invalid: {message}")


def _strip_includes(text: str) -> str:
    while found := re.search(r"\(includes", text, re.IGNORECASE):
        start = found.start()
        depth, end = 0, len(text)
        for index in range(start, len(text)):
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            if depth == 0:
                end = index + 1
                break
        text = text[:start] + text[end:]
    return " ".join(text.split())


def full_display_name(description: str) -> str:
    head, _, rest = _strip_includes(description).partition(",")
    head, rest = head.strip().lower(), rest.strip()
    return f"{head} ({rest})" if rest else head


def _top_level_split(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for index, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth <= 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _collapse_composite(qualifiers: list[str]) -> list[str]:
    """Replace a comma-split "composite of ..., and ..." run with "composite".

    Short qualifiers (two words or fewer) are merged up to the first "and ..." one;
    a run that does not end in "and ..." merges nothing after "composite of ...".
    """
    for start, qualifier in enumerate(qualifiers):
        if qualifier.lower().startswith("composite of"):
            stop = start
            for index in range(start + 1, len(qualifiers)):
                following = qualifiers[index]
                if len(following.split()) > 2:
                    break
                if following.lower().startswith("and "):
                    stop = index
                    break
            return [*qualifiers[:start], _COMPOSITE, *qualifiers[stop + 1 :]]
    return qualifiers


def _before_open_paren(text: str) -> str:
    """Cut before the first "(" that the text leaves unmatched."""
    opened: list[int] = []
    for index, char in enumerate(text):
        if char == "(":
            opened.append(index)
        elif char == ")" and opened:
            opened.pop()
    return text[: opened[0]].rstrip(" ,") if opened else text


def display_name(description: str, limit: int = _SHORT_LIMIT) -> str:
    text = _strip_includes(description)
    if not text or text.startswith(","):
        raise _fail("a description has no head")
    head, *texts = _top_level_split(text)
    texts = _collapse_composite(texts)
    head = head.lower()
    if not texts:
        return head
    room = limit - len(head) - 3
    last = len(texts) - 1
    kept = {index for index, item in enumerate(texts) if item == _COMPOSITE}
    if last not in kept:
        avail = room - sum(len(texts[index]) + 2 for index in kept)
        if len(texts[last]) > avail:
            cut = texts[last][: max(avail, 0) + 1]
            cut = cut.rsplit(" ", 1)[0].rstrip(" ,") if " " in cut else ""
            texts[last] = _before_open_paren(cut)
        if texts[last]:
            kept.add(last)
    used = sum(len(texts[index]) for index in kept) + 2 * max(len(kept) - 1, 0)
    if texts[last]:
        for index in reversed(range(last)):
            size = len(texts[index])
            if (
                index not in kept
                and texts[index].lower() not in _FILLER
                and used + size + 2 <= room
            ):
                kept.add(index)
                used += size + 2
    parts = [texts[index] for index in sorted(kept)]
    return f"{head} ({', '.join(parts)})" if parts else head


def word_tokens(text: str) -> frozenset[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[a-z]+", text.lower()):
        if len(word) > 3 and not word.endswith("ss"):
            if word.endswith("es") and word[:-2].endswith(("ch", "sh", "to")):
                word = word[:-2]
            elif word.endswith("s"):
                word = word[:-1]
        tokens.add(word)
    return frozenset(tokens)


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _diet_flags(description: str, category: int) -> tuple[bool, bool]:
    """Classify described ingredients, without inferring an unlisted recipe.

    Mixed dishes need more evidence than a plant category. These bounded rules
    do not establish allergy or cross-contact safety.
    """
    text = " ".join(description.lower().replace("-", " ").split())
    text = _PLANT_PHRASES.sub("plant food", text)
    text = _EGG_FREE.sub("", text)
    if _MEAT_INGREDIENTS.search(text):
        return False, False
    vegetarian = category in _VEGETARIAN_CATEGORIES
    vegan = category in _VEGAN_CATEGORIES and not _VEGAN_INGREDIENTS.search(text)
    # Fail closed: these preparations usually hold egg, milk, butter, or lard,
    # and these cheeses use animal rennet.
    vegan = vegan and not _ANIMAL_PREPARATIONS.search(text)
    if _RENNET_CHEESES.search(text) or _LARD_FAT.search(
        _VEGETABLE_SHORTENING.sub("", text)
    ):
        vegetarian = False
    preparation = _DAIRY_EGG_PREPARATION.sub("", _PLAIN_PREPARATION.sub("", text))
    if _MIXED_DESCRIPTION.search(preparation):
        return False, False
    return vegetarian, vegan


def _food(row: object) -> UsdaFood:
    if not isinstance(row, list) or len(row) != len(COLUMNS):
        raise _fail("row has unexpected fields")
    fdc_id, description, category, *amounts = row
    if (
        type(fdc_id) is not int
        or fdc_id <= 0
        or type(description) is not str
        or not description.strip()
        or category not in KEPT_CATEGORIES
        or not all(_count(amount) for amount in amounts)
    ):
        raise _fail("row has invalid values")
    vegetarian, vegan = _diet_flags(description, category)
    ingredient = Ingredient(
        f"usda_{fdc_id}",
        display_name(description),
        "g",
        454,
        None,
        vegetarian,
        vegan,
        False,
    )
    return UsdaFood(
        ingredient,
        NutritionFacts(fdc_id, *amounts),
        description,
        word_tokens(description),
        word_tokens(description.split(",")[0]),
    )


def parse_bundle(payload: object) -> list[UsdaFood]:
    keys = {"version", "source", "source_sha256", "columns", "rows"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise _fail("file has unexpected fields")
    digest = payload["source_sha256"]
    if (
        payload["version"] != BUNDLE_VERSION
        or payload["columns"] != COLUMNS
        or type(payload["source"]) is not str
        or type(digest) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not isinstance(payload["rows"], list)
    ):
        raise _fail("header is invalid")
    foods = [_food(row) for row in payload["rows"]]
    ids = [food.facts.fdc_id for food in foods]
    if ids != sorted(set(ids)):
        raise _fail("rows must be unique and sorted by fdc_id")
    return _keep_names_unique(foods)


def _keep_names_unique(foods: list[UsdaFood]) -> list[UsdaFood]:
    """Colliding names are retried with a longer limit, then fall back to full names."""

    def longer(food: UsdaFood) -> str:
        return display_name(food.description, _LONG_LIMIT)

    def full(food: UsdaFood) -> str:
        return full_display_name(food.description)

    renames: tuple[Callable[[UsdaFood], str], ...] = (longer, full)
    for rename in renames:
        counts = Counter(food.ingredient.name for food in foods)
        foods = [
            replace(food, ingredient=replace(food.ingredient, name=rename(food)))
            if counts[food.ingredient.name] > 1
            else food
            for food in foods
        ]
    names = [food.ingredient.name for food in foods]
    if len(set(names)) != len(names):
        raise _fail("display names must be unique")
    return foods


def load_bundle(path: Path = BUNDLE_PATH) -> list[UsdaFood]:
    if not path.is_file():
        return []
    try:
        payload: object = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, zlib.error, ValueError) as error:
        raise _fail(f"could not load {path.name}") from error
    return parse_bundle(payload)


def load_defaults(
    reserved: Collection[str],
    fdc_ids: Collection[int] | None,
    path: Path = DEFAULTS_PATH,
) -> dict[str, int]:
    """Return term -> fdc_id. fdc_ids is None when the bundle is absent."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _fail(f"could not load {path.name}") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "defaults"}
        or payload["version"] != DEFAULTS_VERSION
        or not isinstance(payload["defaults"], dict)
    ):
        raise _fail("defaults file is invalid")
    for term, fdc_id in payload["defaults"].items():
        if (
            term != " ".join(term.lower().split())
            or not term
            or type(fdc_id) is not int
            or term in reserved
            or (fdc_ids is not None and fdc_id not in fdc_ids)
        ):
            raise _fail("a default term is invalid")
    return dict(payload["defaults"])


class UsdaIndex:
    """Resolve a normalized query to USDA ingredient IDs: defaults, exact, tokens."""

    def __init__(self, foods: Sequence[UsdaFood], defaults: Mapping[str, int]) -> None:
        self._foods = tuple(foods)
        by_fdc = {food.facts.fdc_id: food.ingredient.id for food in foods}
        self._defaults = {
            term: by_fdc[fdc] for term, fdc in defaults.items() if fdc in by_fdc
        }
        self._exact: dict[str, list[str]] = {}
        for food in foods:
            description = " ".join(food.description.lower().split())
            for key in {food.ingredient.name.lower(), description}:
                self._exact.setdefault(key, []).append(food.ingredient.id)

    def lookup(self, query: str) -> list[str]:
        """Return one ID (found), several (ambiguous, at most 3), or none."""
        if query in self._defaults:
            return [self._defaults[query]]
        if query in self._exact:
            return self._exact[query][:_MAX_CANDIDATES]
        wanted = word_tokens(query)
        hits = [food for food in self._foods if wanted and wanted <= food.tokens]
        same = [food for food in hits if food.tokens == wanted]
        if len(hits) == 1 or len(same) == 1:
            return [(same or hits)[0].ingredient.id]

        def rank(food: UsdaFood) -> tuple[int, int, int, int]:
            tier = 0 if food.head == wanted else 1 if wanted <= food.head else 2
            raw = 0 if "raw" in food.tokens else 1
            return tier, raw, len(food.tokens), food.facts.fdc_id

        return [food.ingredient.id for food in sorted(hits, key=rank)[:_MAX_CANDIDATES]]


USDA_FOODS = load_bundle()
USDA_INGREDIENTS = {food.ingredient.id: food.ingredient for food in USDA_FOODS}
USDA_NUTRITION = {food.ingredient.id: food.facts for food in USDA_FOODS}
