"""Bind numeric claims to explicit nutrient labels."""

import re
from collections.abc import Sequence
from decimal import Decimal

NUTRIENT_KEYS = {
    "protein_mg": "protein",
    "carbohydrate_mg": "carbohydrate",
    "fat_mg": "fat",
}
NutrientFact = tuple[str, str, bool, Decimal]
_ALIASES = {
    "protein": "protein",
    "proteins": "protein",
    "carb": "carbohydrate",
    "carbs": "carbohydrate",
    "carbohydrate": "carbohydrate",
    "carbohydrates": "carbohydrate",
    "fat": "fat",
    "fats": "fat",
}
_LABEL = re.compile(
    r"\b(?P<qualifier>(?:(?:total|saturated|trans|unsaturated|monounsaturated"
    r"|polyunsaturated|mono-unsaturated|poly-unsaturated|net|added|dietary)"
    r"[\s-]+)+)?"
    r"(?P<label>proteins?|carbohydrates?|carbs?|fats?|fibers?|fibres?|sugars?"
    r"|sodium|potassium|calcium|iron|cholesterol|vitamins?)\b",
    re.IGNORECASE,
)
_PREFIX = re.compile(
    r"\s*(?::\s*)?(?:(?:is|are|was|were|has|contains|provides|changes?|by|from|to"
    r"|gains?|gained|gaining|adds?|added|adding|rises?|rising|rose|increases?"
    r"|increased|increasing|loses?|lost|losing|drops?|dropped|dropping|falls?"
    r"|falling|fell|decreases?|decreased|decreasing|reduces?|reduced|reducing"
    r"|about|around|roughly|approximately)\s+)*\s*(?:\n[ \t]*-\s+)?\Z",
    re.IGNORECASE,
)
_SUFFIX = re.compile(
    r"\s*(?:(?:more|higher|extra|up|less|fewer|lower|down)\s+)?(?:of\s+)?\Z",
    re.IGNORECASE,
)
_PAIR = re.compile(r"\s*(?:and|or|/|,|&)\s*\Z", re.IGNORECASE)
_CONTINUE = re.compile(
    r"\s*(?:,\s*(?:(?:and|or)\s+)?|(?:and|or|plus|to)\s+"
    r"|\(\s*(?:from\s+)?)\Z",
    re.IGNORECASE,
)
_UNCERTAIN_PAIR = re.compile(r"[\s,/&]*(?:(?:and|or|of)\b[\s,/&]*)*\Z", re.IGNORECASE)
_DEFERRED_ADDITION = re.compile(r"\s*,\s*and\s+more\s+\Z", re.IGNORECASE)
_DEFERRED_END = re.compile(r"\s+later\s*(?:[.!?;\n]|\Z)", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[.!?;\n]")
_COUNT_UNIT = re.compile(
    r"\s*(?:servings?|meals?|ounces?|oz|lbs?|pounds?|packages?)\b", re.IGNORECASE
)


def nutrient_bindings(
    text: str, tokens: Sequence[re.Match[str]]
) -> dict[int, str | None]:
    """Return a nutrient, or None for uncertain nutrition grammar, per token."""
    plain = re.sub(r"[*_#]", " ", text)
    labels = list(_LABEL.finditer(plain))
    ambiguous: set[int] = set()
    for left_label, right_label in zip(labels, labels[1:], strict=False):
        if _PAIR.fullmatch(plain[left_label.end() : right_label.start()]):
            ambiguous.update((left_label.start(), right_label.start()))
    bindings: dict[int, str | None] = {}
    consumed: set[int] = set()
    for index, token in enumerate(tokens):
        start = tokens[index - 1].end() if index else 0
        end = tokens[index + 1].start() if index + 1 < len(tokens) else len(text)
        prefixes = [
            label
            for label in labels
            if start <= label.start() < token.start()
            and _PREFIX.fullmatch(plain[label.end() : token.start()])
        ]
        suffixes = [
            label
            for label in labels
            if token.end() <= label.start() < end
            and _SUFFIX.fullmatch(plain[token.end() : label.start()])
        ]
        direct = prefixes + suffixes
        if direct:
            consumed.update(label.start() for label in direct)
            nutrients = {
                _ALIASES.get(label["label"].lower())
                if label.start() not in ambiguous
                and (label["qualifier"] or "total").strip().lower() == "total"
                else None
                for label in direct
            }
            bindings[token.start()] = nutrients.pop() if len(nutrients) == 1 else None
    for label in labels:
        if label.start() in consumed:
            continue
        for token in tokens:
            if not token["n1"] or token["en"]:
                continue
            left, right = (
                (token.end(), label.start())
                if token.end() <= label.start()
                else (label.end(), token.start())
            )
            gap = plain[left:right]
            if (
                token.end() <= label.start()
                and _DEFERRED_ADDITION.fullmatch(gap)
                and _DEFERRED_END.match(plain, label.end())
            ):
                continue
            if not _CLAUSE_END.search(gap) and not any(
                left <= other.start() < right for other in [*labels, *tokens]
            ):
                bindings[token.start()] = None
    for index in range(len(tokens) - 2, -1, -1):
        previous, token = tokens[index], tokens[index + 1]
        if (
            previous.start() in bindings
            or token.start() not in bindings
            or not previous["n1"]
            or previous["en"]
            or _COUNT_UNIT.match(plain, previous.end())
        ):
            continue
        gap = plain[previous.end() : token.start()]
        if _CLAUSE_END.search(gap):
            continue
        if _CONTINUE.fullmatch(gap):
            bindings[previous.start()] = bindings[token.start()]
        elif _UNCERTAIN_PAIR.fullmatch(gap):
            bindings[previous.start()] = None
    for previous, token in zip(tokens, tokens[1:], strict=False):
        if (
            previous.start() not in bindings
            or token.start() in bindings
            or not token["n1"]
            or token["en"]
            or (
                bindings[previous.start()] is not None
                and _COUNT_UNIT.match(plain, token.end())
            )
        ):
            continue
        gap_start = previous.end()
        gap = plain[gap_start : token.start()]
        if bindings[previous.start()] is None:
            if _CLAUSE_END.search(gap):
                continue
            count_unit = _COUNT_UNIT.match(gap)
            if count_unit:
                gap = gap[count_unit.end() :]
                gap_start += count_unit.end()
        for label in labels:
            if label.start() in consumed and gap_start <= label.start() < token.start():
                offset = label.start() - gap_start
                gap = (
                    gap[:offset]
                    + " " * (label.end() - label.start())
                    + gap[label.end() - gap_start :]
                )
        if _CONTINUE.fullmatch(gap):
            bindings[token.start()] = bindings[previous.start()]
    return bindings


def nutrient_grounded(
    nutrient: str | None,
    kind: str,
    value: Decimal,
    sign: str | None,
    facts: set[NutrientFact],
) -> bool:
    """Match only the bound nutrient, unit, and absolute or signed value."""
    if nutrient is None:
        return False
    if sign:
        signed = -value if sign == "-" else value
        return (nutrient, kind, True, signed) in facts or (
            signed < 0 and (nutrient, kind, False, signed) in facts
        )
    return (nutrient, kind, False, value) in facts
