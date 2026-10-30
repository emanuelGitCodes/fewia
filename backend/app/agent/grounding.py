"""Check a model-written reply against the facts that tools returned (0022).

An "about N" energy token, with N a multiple of 10, also passes when some
energy fact is within 9 of N (see APPROX_WINDOW).

Character rule: the reply is folded (NFKD, no combining marks) and then every
character must be in the allowed set (see _UNSUPPORTED): ASCII letters, digits,
space, newline, tab, the punctuation . , ; : ! ? ' " ( ) [ ] $ % / + - & * # _,
and the cent sign. The server templates emit nothing else. Any other character
fails with `unsupported_character`; nothing is deleted without being classified,
so no character can hide a claim. Dashes are mapped to "-", curly quotes to
ASCII quotes, and vulgar fractions are named as the number word "half", before
the check. The only whitespace allowed is space, newline, and tab.

Exemption rule: the only exemptions are the exact sentences of the server safety
note (`_SAFETY`), removed verbatim from the raw reply before any normalization,
for the claim check only, and only at the very start of the reply or right after a
sentence end: a word of three or more letters or digits, one of .!?, and whitespace
(see _SENTENCE_END). No exemption depends on any other nearby words.

Token boundary rule: a number must be followed by the end of the text, whitespace,
punctuation from the allowed set, or a recognized unit (see _UNITS). A number
directly followed by any other letter ("12k", "2x", "3K") is `unmatched_number`.
So is a number, whitespace, and a scale word or multiplier ("$12 K", "2 x").
Mass units: "mg" must match a milligram fact, "kg" is grams times 1000.

Digit rule: any digit, number, or letter-number character other than ASCII 0-9
(superscripts, circled or fullwidth digits, other scripts, "Ⅻ") fails with
`unsupported_character` before folding. Vulgar fractions are the exception.
An ellipsis, a spaced dot, or an abbreviation ("e.g.", "Dr.", "U.S.") does not end a
sentence, so a server sentence after one is not exempt.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.agent.catalog_tool import _SAFETY, TOOL_NAME
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.meal_tags import CARNIVORE_NOTE, KETO_NOTE

MAX_REPLY_CHARS = 1200
APPROX_WINDOW = 10
_NUM = r"(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"
# normalize maps every dash and minus sign to a hyphen-minus first.
_SIGN = r"[+\-]"
_MINUS = "-"
_DASHES = re.compile("[‐-―−﹣－]")
_SPACES = re.compile(r"\s")
_QUOTES = str.maketrans("‘’“”", "''\"\"")
_UNSUPPORTED = re.compile(r"[^A-Za-z0-9 \n\t.,;:!?'\"()\[\]$%/+\-&*#_¢]")
_SMALL = "one two three four five six seven eight nine ten eleven twelve".split()
_WORD = rf"\b(?:{'|'.join(_SMALL)})\b"
_BIG = (
    r"(?:(?:thir|four|fif|six|seven|eigh|nine)teen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?|half"
    r"|halves|couple|zero|twice|double|triple|quadruple|quarters?|once|tens"
    r"|thirds?|fifths?|few|several|(?:fourth|sixth|seventh|eighth|ninth|tenth)s?"
    r"|pair|couple)"
)
# Vulgar fractions U+00BC-U+00BE, U+2150-U+215E, and U+2189.
_FRACTION = r"[¼-¾⅐-⅞↉]"
_TOKEN = re.compile(
    rf"(?:(?<!\w)(?P<s1>{_SIGN}))?(?:\bUSD\s*)?(?P<s2>{_SIGN})?\$\s*"
    rf"(?P<usd>{_NUM})(?:\s*(?:to\b|-)\s*\$?\s*(?P<usd2>{_NUM}))?"
    rf"|(?:(?<!\w)(?P<s3>{_SIGN}))?(?:\bUSD\s*(?P<s4>{_SIGN})?\s*(?P<usdn>{_NUM})"
    rf"(?:\s*(?:to\b|-)\s*(?P<usdn2>{_NUM}))?"
    rf"|(?P<mn>{_NUM}|{_WORD})(?:\s*(?:to\b|-)\s*(?P<mn2>{_NUM}|{_WORD}))?[\s-]*"
    r"(?:(?P<mu>dollars?|USD|bucks?)\b|(?P<cents>cents?\b|¢)|(?P<sym>\$(?!\s*\.?\d))))"
    r"|(?P<bare>\b(?:dollars?|bucks?|cents?|USD)\b)"
    rf"|(?P<dw>\$\s*(?=\b(?:{'|'.join(_SMALL)})\b|\b{_BIG}\b))"
    rf"|(?P<big>\b{_BIG}\b)"
    rf"|(?:(?<!\w)(?P<sign>{_SIGN}))?(?P<n1>{_NUM}|\b(?:{'|'.join(_SMALL)})\b)"
    rf"(?:\s*(?:to|-)\s*(?P<n2>{_NUM}))?"
    r"(?:\s*(?:(?P<en>kcal|calories|calorie|cal)\b|(?P<ms>grams|gram|g)\b"
    r"|(?P<mm>mg)\b|(?P<kg>kg)\b|(?P<pc>%|percent\b)))?",
    re.IGNORECASE,
)
_KINDS = {"en": "energy", "ms": "mass", "mm": "milli", "kg": "mass", "pc": "percent"}
_UNITS = frozenset(
    "kcal calories calorie cal g gram grams mg kg percent dollars dollar cents cent"
    " usd buck bucks serving servings meal meals ounce ounces oz lb lbs pound pounds"
    " package packages".split()
)
# A number glued to letters: only a recognized unit may follow it directly.
_ATTACHED = re.compile(rf"({_NUM})([A-Za-z]+)")
_PERCENT_AFTER = re.compile(r"\s*(?:%|percent\b)", re.IGNORECASE)
_APPROX = re.compile(r"\b(?:about|around|roughly|approximately)\s+$", re.IGNORECASE)
_DETERMINER = re.compile(
    r"\b(?:which|this|that|the|any|no|each|every|another|a|an)\s+$", re.IGNORECASE
)
_OF = re.compile(r"\s+of\b", re.IGNORECASE)
# "which one do you mean": "one" is a pronoun only at the end of a clause or before
# a function word. Any other noun or unit ("a one egg omelet", "a one-pound pack")
# makes it a quantity, which is checked like a digit.
_ONE_TAIL = re.compile(
    r"\s*(?:[^\w\s-]|$|(?:of|do|does|did|should|would|could|can|will|is|are|was"
    r"|were|you|i|we|they|it|that|which|to|for|with|in|on|and|or|but|if|so|as|than"
    r"|works|fits|looks|sounds|suits|has|have|had|costs|instead|more|less|please)\b)",
    re.IGNORECASE,
)
# UUIDs, long hex hashes, and ISO dates or datetimes carry no quantity.
_OPAQUE = re.compile(
    r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|[0-9a-f]{16,}"
    r"|\d{4}-\d{2}-\d{2}(?:[T ][\d:.+\-Z]*)?",
    re.IGNORECASE,
)
# Matched on letters only (see _squash), so spacing and punctuation tricks fail closed.
_FORBIDDEN = re.compile(
    r"safefor|allergyfree|allergenfree|celiacsafe|medical|cures|treats|prevents"
    r"|diagnos|glutenfree"
    r"|placed[a-z]{0,8}order|orderhasbeenplaced|orderwasplaced|toyourcart|bought"
    r"|purchased|checkedout"
)
# A number, whitespace, then a scale word or multiplier ("$12 K", "2 x the protein").
_SCALED = re.compile(
    rf"({_NUM})\s+(?:k|m|b|mm|mn|bn|bln|tn|mil|grand|thousand|million|billion"
    r"|trillion|x)\b",
    re.IGNORECASE,
)
# The server safety note names the claims it refuses; each exact sentence is removed
# verbatim from the raw reply before the claim check, and nothing else is exempt.
_SERVER_SENTENCE = re.compile(
    r"(?:\A\s*|(?<=[.!?])\s+)(?:"
    + "|".join(re.escape(s) for s in re.split(r"(?<=\.) ", _SAFETY))
    + ")"
)
# A sentence end is a word of 3+ letters or digits, then one of .!? ("Dr.", "No.",
# "e.g.", "U.S.", "a.m.", ". . ." and "..." are not sentence ends).
_SENTENCE_END = re.compile(r"(?<![\w.])\w{3,}[.!?]\Z")


@dataclass
class FactSet:
    money: set[Decimal] = field(default_factory=set)
    energy: set[Decimal] = field(default_factory=set)
    mass: set[Decimal] = field(default_factory=set)
    milli: set[Decimal] = field(default_factory=set)
    percent: set[Decimal] = field(default_factory=set)
    count: set[Decimal] = field(default_factory=set)
    generic: set[Decimal] = field(default_factory=set)
    # Signed changes as (kind, value); only a signed token may match these.
    deltas: set[tuple[str, Decimal]] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reasons: tuple[str, ...]
    unmatched: tuple[str, ...]
    has_money: bool


def _whole_grams(mg: int) -> Decimal:
    return Decimal((abs(mg) * 2 + 1000) // 2000 * (-1 if mg < 0 else 1))


def _kinds(
    key: str, number: int, forced: str | None = None
) -> list[tuple[str, Decimal]]:
    low, value = key.lower(), Decimal(number)
    if forced:
        return [(forced, value)]
    if low.endswith("_cents"):
        return [("money", value)]
    if low.endswith("_mg"):
        tenth = (value / 1000).quantize(Decimal("0.1"), ROUND_HALF_UP)
        return [("mass", _whole_grams(number)), ("mass", tenth), ("milli", value)]
    if "kcal" in low:
        return [("energy", value)]
    if "percent" in low:
        return [("percent", value)]
    return [("count", value), *([("mass", value)] if low.endswith("_g") else [])]


def _fold(text: str) -> str:
    """NFKD without combining marks, ASCII quotes, and hyphen-minus dashes."""
    # NFKD would turn a vulgar fraction into digits, so name it as a number word.
    text = re.sub(_FRACTION, " half ", text)
    parts = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in parts if unicodedata.category(c) != "Mn")
    return _DASHES.sub("-", folded.translate(_QUOTES))


def normalize(text: str) -> str:
    """The text every check runs on: folded, with every space mapped to " "."""
    return _SPACES.sub(" ", _fold(text))


def _without_server_sentences(reply: str) -> str:
    def drop(match: re.Match[str]) -> str:
        before = reply[: match.start()]
        if before and not _SENTENCE_END.search(before):
            return match.group()
        return " "

    return _SERVER_SENTENCE.sub(drop, reply)


def _foreign_number(text: str) -> bool:
    """A digit, number, or letter-number character other than ASCII 0-9.

    Vulgar fractions are named as number words by _fold, so they are not flagged.
    """
    return any(
        unicodedata.category(c) in ("Nd", "No", "Nl")
        and not ("0" <= c <= "9")
        and not re.fullmatch(_FRACTION, c)
        for c in text
    )


def _squash(text: str) -> str:
    """Letters only; the text holds ASCII letters, so no letter is ever removed."""
    return re.sub(r"[^a-z]", "", text.lower())


def _is_id(low: str) -> bool:
    return low == "id" or low.endswith(("_id", "_ids"))


def _is_delta(low: str) -> bool:
    return low == "delta" or low.startswith("delta_")


def _add_text(text: str, facts: FactSet, *, scan_percent: bool = True) -> None:
    text = _OPAQUE.sub(" ", text)
    for match in re.finditer(_NUM, text):
        value = Decimal(match.group().replace(",", ""))
        facts.generic.add(value)
        if scan_percent and _PERCENT_AFTER.match(text, match.end()):
            facts.percent.add(value)


def _changes(
    before: Mapping[object, object], after: Mapping[object, object], facts: FactSet
) -> None:
    """Record after minus before for every numeric key that both sides share."""
    for name in before.keys() & after.keys():
        if _is_id(str(name).lower()):
            continue
        old, new = before[name], after[name]
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            _changes(old, new, facts)
        elif type(old) is int and type(new) is int:
            now, was = _kinds(str(name), new), _kinds(str(name), old)
            facts.deltas.update(
                (k, a - b) for (k, a), (_, b) in zip(now, was, strict=False)
            )
            facts.deltas.update(_kinds(str(name), new - old))


def _walk(
    value: object,
    key: str,
    facts: FactSet,
    delta: bool = False,
    forced: str | None = None,
) -> None:
    low = key.lower()
    if isinstance(value, bool) or value is None:
        return
    if _is_id(low) and low != "fdc_id":
        return
    if _is_delta(low):
        delta, forced = True, "percent" if "percent" in low else forced
    if isinstance(value, int):
        for kind, number in _kinds(key, value, forced):
            if delta:
                facts.deltas.add((kind, number))
            else:
                getattr(facts, kind).add(number)
    elif delta and isinstance(value, float | str):
        pass  # a delta subtree holds signed ints only
    elif isinstance(value, float):
        facts.generic.add(Decimal(str(value)))
    elif isinstance(value, str):
        _add_text(value, facts)
    elif isinstance(value, Mapping):
        if isinstance(value.get("before"), Mapping) and isinstance(
            value.get("after"), Mapping
        ):
            _changes(value["before"], value["after"], facts)
        for name, item in value.items():
            if not (delta or _is_delta(str(name).lower())):
                _add_text(str(name), facts, scan_percent=False)
            _walk(item, str(name), facts, delta, forced)
    elif isinstance(value, Sequence):
        for item in value:
            _walk(item, key, facts, delta, forced)


def facts_from_payloads(
    payloads: Sequence[tuple[str, Mapping[str, object]]],
) -> FactSet:
    facts = FactSet()
    for tool, payload in payloads:
        if tool == TOOL_NAME:
            for note in (_SAFETY, KETO_NOTE, CARNIVORE_NOTE):
                _add_text(note, facts)
        _walk(payload, "", facts)
    return facts


def with_notice(reply: str) -> str:
    if SAMPLE_ESTIMATE_NOTICE in reply:
        return reply
    return f"{reply} {SAMPLE_ESTIMATE_NOTICE}"


def _number(raw: str) -> Decimal:
    word = raw.lower()
    if word in _SMALL:
        return Decimal(_SMALL.index(word) + 1)
    return Decimal(raw.replace(",", ""))


def _grounded(
    kind: str, value: Decimal, sign: str | None, approx: bool, facts: FactSet
) -> bool:
    pool: set[Decimal] = getattr(facts, kind)
    if sign:
        signed = -value if sign in _MINUS else value
        return (kind, signed) in facts.deltas or (signed < 0 and signed in pool)
    if kind == "energy":
        # "about 480 kcal" may stand for an energy fact within 9 of 480.
        near = (
            approx
            and value % 10 == 0
            and any(abs(value - f) < APPROX_WINDOW for f in pool)
        )
        return value in pool or near
    return value in pool or (kind in ("mass", "count") and value in facts.generic)


def _scan(reply: str, facts: FactSet) -> tuple[list[str], bool, bool]:
    unmatched: list[str] = []
    word = money = False
    for m in _TOKEN.finditer(reply):
        before = reply[max(0, m.start() - 20) : m.start()]
        if m["big"]:
            word = True
        elif m["bare"]:
            word = money = True  # a money unit with no adjacent number
        elif m["dw"]:
            word = money = True
        elif m["usd"] or m["usdn"] or m["mn"]:
            money = True
            msign = m["s1"] or m["s2"] or m["s3"] or m["s4"]
            amounts = (
                m["usd"] or m["usdn"] or m["mn"],
                m["usd2"] or m["usdn2"] or m["mn2"],
            )
            for index, raw in enumerate(amounts):
                if raw is None:
                    continue
                amount = _number(raw)
                text = str(amount) if raw[0].isalpha() else raw.replace(",", "")
                sign = msign if index == 0 else None
                cents = amount * (1 if m["cents"] else 100)
                if not _grounded("money", cents, sign, False, facts):
                    label = text if m["cents"] else f"${text}"
                    unmatched.append(f"{sign or ''}{label}")
        elif (
            m["n1"].lower() == "one"
            and not any(m[name] for name in _KINDS)
            and (_DETERMINER.search(before) or _OF.match(reply, m.end()))
            and _ONE_TAIL.match(reply, m.end())
        ):
            continue
        else:
            kind = next((_KINDS[name] for name in _KINDS if m[name]), "count")
            approx = bool(_APPROX.search(before))
            for index, raw in enumerate((m["n1"], m["n2"])):
                if raw is None:
                    continue
                nsign = m["sign"] if index == 0 else None
                value = _number(raw) * (1000 if m["kg"] else 1)
                if not _grounded(kind, value, nsign, approx, facts):
                    shown = str(int(_number(raw))) if raw[0].isalpha() else raw
                    unmatched.append(f"{nsign or ''}{shown}")
    unmatched.extend(
        m[1] for m in _ATTACHED.finditer(reply) if m[2].lower() not in _UNITS
    )
    unmatched.extend(m[0] for m in _SCALED.finditer(reply))
    return list(dict.fromkeys(unmatched)), word, money


def validate(reply: str, facts: FactSet) -> Verdict:
    if _foreign_number(reply) or _UNSUPPORTED.search(_fold(reply)):
        return Verdict(False, ("unsupported_character",), (), False)
    text = normalize(reply)
    unmatched, word, money = _scan(text, facts)
    claims = normalize(_without_server_sentences(reply))
    checks = (
        ("empty", not text.strip()),
        ("too_long", len(reply) > MAX_REPLY_CHARS),
        ("store_price", "kroger" in _squash(text)),
        ("forbidden_claim", _FORBIDDEN.search(_squash(claims)) is not None),
        ("number_word", word),
        ("unmatched_number", bool(unmatched)),
    )
    reasons = tuple(code for code, failed in checks if failed)
    return Verdict(not reasons, reasons, tuple(unmatched), money)
