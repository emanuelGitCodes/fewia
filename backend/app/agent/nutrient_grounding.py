"""Bind numeric claims to explicit nutrient labels."""

import re
import string
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
# A fact with the basis and side of its payload path: (subject, kind, is_delta, value,
# basis, side). The subject is a nutrient or "energy".
TaggedFact = tuple[str, str, bool, Decimal, str | None, str | None]
BASIS_KEYS = {"per_serving": "serving", "total": "total", "per_100g": "100g"}
SIDE_KEYS = {"before": "before", "after": "after"}
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
    rf"|to|used{_H}+to{_H}+(?:be|have)|stay(?:s|ed)?|remain(?:s|ed)?|at|{UP_VERBS}"
    rf"|{DOWN_VERBS}|about|around|roughly|approximately){_H}+)*"
    r"(?:\n[ \t]*-\s+)?\Z",
    re.IGNORECASE,
)
_SUFFIX = re.compile(
    rf"{_H}*(?:(?:{UP_WORDS}|{DOWN_WORDS}){_H}+)?(?:of{_H}+)?\Z", re.IGNORECASE
)
# A word before a label that is not a qualifier of _LABEL leaves the label unbound.
_LEFT_OK = frozenset(
    "the its their this that and or of with in has have had gives contains"
    " provides previously originally".split()
)
_LEFT_CHARS = frozenset(string.ascii_letters + string.digits + "'-")
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
# A basis phrase right after a claim; _basis_name reads which basis it names.
_BASIS = re.compile(
    r"\s*(?:(?P<serving>per\s+(?:servings?|meals?))"
    r"|per\s+(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>g|grams?|mg|milligrams?|kg|kilograms?)"
    r"|(?P<total>in\s+total|total|for\s+(?:the\s+meal|all\s+servings"
    r"|(?P<n>\d+)\s+(?:servings?|meals?))))\b",
    re.IGNORECASE,
)
# A line that ends with an amount, "25 g" or "25 g per serving". A number can start
# only where no digit, letter, "." or "," precedes it, so the search stays linear.
_AMOUNT_END = re.compile(
    r"(?<![\w.,])(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)[^\S\n]*"
    r"(?:g|grams?|mg|kg|kcal|cal(?:ories?)?|%|percent)"
    rf"(?:[^\S\n]*{_BASIS.pattern})?\Z",
    re.IGNORECASE,
)
# The change that follows an "X to Y" pair, "(+5 g)", after an optional basis phrase.
_PAIR_DELTA = re.compile(rf"(?:{_BASIS.pattern})?\s*\(\s*\Z", re.IGNORECASE)
# What may stand between a claim and its basis phrase: a direction word, "of", a label.
_CLAIM_LEAD = re.compile(
    rf"{_H}*(?:(?:{UP_WORDS}|{DOWN_WORDS}){_H}+)?(?:of{_H}+)?(?:{_LABEL.pattern})?",
    re.IGNORECASE,
)
_CLAUSE = re.compile(r"[!?;\n]|\.(?!\d)|,(?!\d{3}\b)")
_BEFORE = re.compile(
    r"\b(?:from|was|were|before|original(?:ly)?|previously|used\s+to|had)\b",
    re.IGNORECASE,
)
_SCALE = {"k": Decimal(1000), "m": Decimal("0.001")}


def _between(
    labels: Sequence[re.Match[str]], starts: Sequence[int], left: int, right: int
) -> Sequence[re.Match[str]]:
    """The labels that start in [left, right), found by bisection on their starts."""
    return labels[bisect_left(starts, left) : bisect_left(starts, right)]


def _within(points: Sequence[int], left: int, right: int) -> bool:
    """Whether a sorted position falls in [left, right)."""
    at = bisect_left(points, left)
    return at < len(points) and points[at] < right


def pair_delta(plain: str, pair: re.Match[str], change: re.Match[str]) -> bool:
    """Whether `change` is the signed "(+5 g)" that follows the "X to Y" token `pair`."""
    between = plain[pair.end() : change.start()]
    return bool(pair["n2"] and change["sign"] and _PAIR_DELTA.fullmatch(between))


def _left_ok(plain: str, label: re.Match[str]) -> bool:
    """False when an unlisted word sits right before the label ("animal protein")."""
    # No fixed window: walk back over whitespace (plain has turned "*_#" into spaces),
    # then over the word. Each label walks only the text right before it.
    end = label.start()
    while end and plain[end - 1].isspace():
        end -= 1
    start = end
    while start and plain[start - 1] in _LEFT_CHARS:
        start -= 1
    word = plain[start:end]
    if not any(c.isalnum() for c in word) or word.lower() in _LEFT_OK:
        return True
    if "\n" not in plain[end : label.start()]:
        return False
    # The label starts a line: it stays bound only when the line above ends with an
    # amount ("25 g", "25 g per serving"). Any other last word is checked as above.
    line = plain[plain.rfind("\n", 0, end) + 1 : end]
    return _AMOUNT_END.search(line) is not None


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
    if (
        next_token is not None
        and not next_token["en"]
        and pair_delta(plain, tokens[index], next_token)
    ):
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
            bindings.get(previous.start()) is not None
            and token.start() not in bindings
            and not token["en"]
            and pair_delta(plain, previous, token)
        ):
            bindings[token.start()] = bindings[previous.start()]  # "20 to 25 g (+5 g)"
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


def _basis_name(match: re.Match[str]) -> str:
    if match["serving"] or match["n"] == "1":
        return "serving"
    if match["total"]:
        return "total"
    grams = Decimal(match["qty"]) * _SCALE.get(match["unit"][0].lower(), Decimal(1))
    return "100g" if grams == 100 else "other"


def _basis_match(plain: str, end: int) -> re.Match[str] | None:
    stop = _TAIL_BOUNDARY.search(plain, end)
    lead = _CLAIM_LEAD.match(plain, end)
    start = lead.end() if lead else end
    return _BASIS.match(plain, start, stop.start() if stop else len(plain))


def claim_basis(plain: str, end: int) -> str | None:
    """The basis a claim names right after its number: "serving", "total", "100g"."""
    match = _basis_match(plain, end)
    return _basis_name(match) if match else None


def basis_count(plain: str, end: int) -> int | None:
    """Where the N of a "for N servings" basis phrase starts after a claim, else None."""
    match = _basis_match(plain, end)
    return match.start("n") if match and match["n"] else None


def before_marker(plain: str, start: int) -> bool:
    """Whether the clause around a claim holds a word that places it before a swap."""
    head = _CLAUSE.split(plain[max(0, start - 200) : start])[-1]
    tail = _CLAUSE.split(plain[start : start + 200], 1)[0]
    return _BEFORE.search(head + tail) is not None


def tag_ok(
    tagged: set[TaggedFact], fact: NutrientFact, basis: str | None, before: bool
) -> bool:
    """Whether a fact has a basis and side that a claim may use.

    A claim with a basis matches a fact of that basis or of none. A fact that is only
    on the before side matches only a claim whose clause has a before marker. A fact
    with no tag at all (a hand-built FactSet) has no basis and no side.
    """
    pairs = [(f[4], f[5]) for f in tagged if f[:4] == fact]
    return not pairs or any(
        basis in (None, have) or have is None
        for have, side in pairs
        if before or side != "before"
    )


def nutrient_grounded(
    nutrient: str | None,
    kind: str,
    value: Decimal,
    sign: str | None,
    facts: set[NutrientFact],
    tagged: set[TaggedFact] | None = None,
    basis: str | None = None,
    before: bool = False,
) -> bool:
    """Match only the bound nutrient, unit, signed or absolute value, basis, side."""
    if nutrient is None:
        return False

    def usable(fact: NutrientFact) -> bool:
        if fact not in facts:
            return False
        return tagged is None or tag_ok(tagged, fact, basis, before)

    if sign:
        signed = -value if sign == "-" else value
        return usable((nutrient, kind, True, signed)) or (
            signed < 0 and usable((nutrient, kind, False, signed))
        )
    return usable((nutrient, kind, False, value))
