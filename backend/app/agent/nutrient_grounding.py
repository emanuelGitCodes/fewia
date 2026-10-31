"""Bind numeric claims to explicit nutrient labels."""

import re
from bisect import bisect_left
from collections.abc import Sequence
from decimal import Decimal

# One source for the direction words: grounding.py builds its verb and direction
# patterns from these, and so do _PREFIX and _SUFFIX below.
UP_VERBS = (
    r"gain(?:s|ed|ing)?|add(?:s|ed|ing)?|ris(?:e|es|ing)|rose"
    r"|increas(?:e|es|ed|ing)"
)
DOWN_VERBS = (
    r"los(?:e|es|ing)|lost|drop(?:s|ped|ping)?|fall(?:s|ing)?|fell"
    r"|(?:decreas|reduc)(?:e|es|ed|ing)"
)
UP_WORDS = "more|higher|extra|up"
DOWN_WORDS = "less|fewer|lower|down"
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
# A binding never crosses a line break, except the "\n- " of a bullet after a colon.
_H = r"[^\S\n]"
_PREFIX = re.compile(
    rf"{_H}*(?::{_H}*)?(?:(?:is|are|was|were|has|contains|provides|changes?|by|from"
    rf"|to|{UP_VERBS}|{DOWN_VERBS}|about|around|roughly|approximately){_H}+)*"
    r"(?:\n[ \t]*-\s+)?\Z",
    re.IGNORECASE,
)
_SUFFIX = re.compile(
    rf"{_H}*(?:(?:{UP_WORDS}|{DOWN_WORDS}){_H}+)?(?:of{_H}+)?\Z", re.IGNORECASE
)
# A word before a label that is not a qualifier of _LABEL leaves the label unbound.
_LEFT_OK = frozenset(
    "the its their this that and or of with in has have had gives contains"
    " provides".split()
)
_LEFT_WORD = re.compile(r"[A-Za-z0-9'-]+\Z")
# A label then "by", for "protein by 5 g" (no verb) and "reduces calories by 20 kcal".
LABEL_BY = rf"(?:{_LABEL.pattern}|\b(?:calories?|energy)\b){_H}+(?=by\b)"
_PAIR = re.compile(r"\s*(?:and|or|/|,|&)\s*\Z", re.IGNORECASE)
_CONTINUE = re.compile(
    rf"{_H}*(?:,{_H}*(?:(?:and|or){_H}+)?|(?:and|or|plus|to){_H}+"
    rf"|\({_H}*(?:from{_H}+)?)\Z",
    re.IGNORECASE,
)
_UNCERTAIN_PAIR = re.compile(r"[\s,/&]*(?:(?:and|or|of)\b[\s,/&]*)*\Z", re.IGNORECASE)
_DEFERRED_ADDITION = re.compile(r"\s*,\s*and\s+more\s+\Z", re.IGNORECASE)
_DEFERRED_END = re.compile(r"\s+later\s*(?:[.!?;\n]|\Z)", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[.!?;\n]")
_COUNT_UNIT = re.compile(
    r"\s*(?:servings?|meals?|ounces?|oz|lbs?|pounds?|packages?)\b", re.IGNORECASE
)
_TAIL_BOUNDARY = re.compile(r"[!?;\n]|\.(?!\d)")
_TAIL_END = re.compile(r"\s*(?:\)\s*)*\Z")
_FDC_CITATION = re.compile(r"\s*\(USDA FDC [0-9]+\)")
_ENERGY_CLAUSE = re.compile(
    r"\s+(?:but|while(?:\s+protein\s+and)?)\s+\Z", re.IGNORECASE
)
_MACRO_JOIN = re.compile(
    rf"{_H}*(?:\){_H}*)*(?:,{_H}*(?:(?:and|or){_H}+)?|(?:and|or|plus){_H}+"
    rf"|[/&(]{_H}*)\Z",
    re.IGNORECASE,
)
_BASIS = re.compile(
    r"\s*(?:per\s+(?:servings?|meals?|\d+(?:\.\d+)?\s*"
    r"(?:g|grams?|mg|milligrams?|kg|kilograms?))"
    r"|for\s+\d+\s+(?:servings?|meals?))\b",
    re.IGNORECASE,
)


def _between(
    labels: Sequence[re.Match[str]], starts: Sequence[int], left: int, right: int
) -> Sequence[re.Match[str]]:
    """The labels that start in [left, right), found by bisection on their starts."""
    return labels[bisect_left(starts, left) : bisect_left(starts, right)]


def _within(points: Sequence[int], left: int, right: int) -> bool:
    """Whether a sorted position falls in [left, right)."""
    at = bisect_left(points, left)
    return at < len(points) and points[at] < right


def _left_ok(plain: str, label: re.Match[str]) -> bool:
    """False when an unlisted word sits right before the label ("animal protein")."""
    low = max(0, label.start() - 16)
    raw = plain[low : label.start()]
    before = raw.rstrip(" \t\n")
    word = _LEFT_WORD.search(before)
    if (
        word is None
        or not any(c.isalnum() for c in word.group())
        or word.group().lower() in _LEFT_OK
    ):
        return True
    if "\n" not in raw[len(before) :]:
        return False
    # The label starts a line: only the end of a line that holds an amount ("25 g",
    # "25 g per serving") leaves it bound. "Plant" alone on the line above does not.
    line = plain[plain.rfind("\n", 0, low + word.start()) + 1 : low + word.end()]
    return any(c.isdigit() for c in line)


def _claim_tail_allowed(
    plain: str,
    tokens: Sequence[re.Match[str]],
    labels: Sequence[re.Match[str]],
    starts: Sequence[int],
    index: int,
    nutrient: str,
) -> bool:
    """Accept only structural continuations after a nutrient amount."""
    tail_start = tokens[index].end()
    next_token = tokens[index + 1] if index + 1 < len(tokens) else None
    next_start = next_token.start() if next_token is not None else len(plain)
    boundary = _TAIL_BOUNDARY.search(plain, tail_start)
    clause_end = boundary.start() if boundary else len(plain)
    local_end = min(next_start, clause_end)
    for label in _between(labels, starts, tail_start, local_end):
        if _SUFFIX.fullmatch(plain[tail_start : label.start()]):
            if _ALIASES.get(label["label"].lower()) != nutrient:
                return False
            tail_start = label.end()
            break
    basis = _BASIS.match(plain, tail_start, clause_end)
    if basis:
        tail_start = basis.end()
    citation = _FDC_CITATION.match(plain, tail_start, clause_end)
    if citation:
        tail_start = citation.end()
    if basis or citation:
        next_token = next(
            (other for other in tokens[index + 1 :] if other.start() >= tail_start),
            None,
        )
        next_start = next_token.start() if next_token is not None else len(plain)
        local_end = min(next_start, clause_end)
    gap = plain[tail_start:local_end]
    if local_end == clause_end and _TAIL_END.fullmatch(gap):
        return True
    if next_start >= clause_end:
        return False
    if next_token is not None and next_token["en"] and _ENERGY_CLAUSE.fullmatch(gap):
        return True
    if not basis and _CONTINUE.fullmatch(gap):
        return True
    for label in _between(labels, starts, tail_start, next_start):
        if _PREFIX.fullmatch(plain[label.end() : next_start]) and _MACRO_JOIN.fullmatch(
            plain[tail_start : label.start()]
        ):
            return True
    return False


def nutrient_bindings(
    text: str, tokens: Sequence[re.Match[str]]
) -> dict[int, str | None]:
    """Return a nutrient, or None for uncertain nutrition grammar, per token."""
    plain = re.sub(r"[*_#]", " ", text)
    labels = list(_LABEL.finditer(plain))
    # Positions are computed once; the loops below bisect them instead of rescanning.
    starts = [label.start() for label in labels]
    token_starts = [token.start() for token in tokens]
    marks = sorted([*starts, *token_starts])
    clause_ends = [end.start() for end in _CLAUSE_END.finditer(plain)]
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
            for label in _between(labels, starts, start, token.start())
            if _PREFIX.fullmatch(plain[label.end() : token.start()])
        ]
        suffixes = [
            label
            for label in _between(labels, starts, token.end(), end)
            if _SUFFIX.fullmatch(plain[token.end() : label.start()])
        ]
        direct = prefixes + suffixes
        if direct:
            consumed.update(label.start() for label in direct)
            nutrients = {
                _ALIASES.get(label["label"].lower())
                if label.start() not in ambiguous
                and (label["qualifier"] or "total").strip().lower() == "total"
                and (label in suffixes or _left_ok(plain, label))
                else None
                for label in direct
            }
            bindings[token.start()] = nutrients.pop() if len(nutrients) == 1 else None
    for label in labels:
        if label.start() in consumed:
            continue
        # Only the nearest token on each side can have no label or token between.
        near = bisect_left(token_starts, label.start())
        for token in tokens[max(near - 1, 0) : near + 1]:
            if not token["n1"] or token["en"]:
                continue
            left, right = (
                (token.end(), label.start())
                if token.end() <= label.start()
                else (label.end(), token.start())
            )
            if _within(clause_ends, left, right) or _within(marks, left, right):
                continue
            if (
                token.end() <= label.start()
                and _DEFERRED_ADDITION.fullmatch(plain[left:right])
                and _DEFERRED_END.match(plain, label.end())
            ):
                continue
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
        for label in _between(labels, starts, gap_start, token.start()):
            if label.start() in consumed:
                offset = label.start() - gap_start
                gap = (
                    gap[:offset]
                    + " " * (label.end() - label.start())
                    + gap[label.end() - gap_start :]
                )
        if _CONTINUE.fullmatch(gap):
            bindings[token.start()] = bindings[previous.start()]
    for index, token in enumerate(tokens):
        nutrient = bindings.get(token.start())
        if nutrient is not None and not _claim_tail_allowed(
            plain, tokens, labels, starts, index, nutrient
        ):
            bindings[token.start()] = None
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
