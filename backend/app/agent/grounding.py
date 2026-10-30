"""Check a model-written reply against the facts that tools returned (0022).

An "about N" energy token, with N a multiple of 10, also passes when some
energy fact is within 9 of N (see APPROX_WINDOW).
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
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
# _normalize maps every dash and minus sign to a hyphen-minus first.
_SIGN = r"[+\-]"
_MINUS = "-"
_DASHES = re.compile("[‐-―−﹣－]")
_SPACES = re.compile(r"\s")
_SMALL = "one two three four five six seven eight nine ten eleven twelve".split()
_WORD = rf"\b(?:{'|'.join(_SMALL)})\b"
_BIG = (
    r"(?:(?:thir|four|fif|six|seven|eigh|nine)teen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?|half"
    r"|halves|couple|zero|twice|double|triple|quadruple|quarters?|once|tens)"
)
# Vulgar fractions U+00BC-U+00BE, U+2150-U+215E, and U+2189.
_FRACTION = r"[¼-¾⅐-⅞↉]"
_TOKEN = re.compile(
    rf"(?:(?<!\w)(?P<s1>{_SIGN}))?(?:\bUSD\s*)?(?P<s2>{_SIGN})?\$\s?(?P<usd>{_NUM})"
    rf"|(?:(?<!\w)(?P<s3>{_SIGN}))?(?:\bUSD\s*(?P<usdn>{_NUM})"
    rf"|(?P<mn>{_NUM}|{_WORD})\s*(?:(?P<mu>dollars?|USD)|(?P<cents>cents?))\b)"
    rf"|(?P<big>\b{_BIG}\b|{_FRACTION})"
    rf"|(?:(?<!\w)(?P<sign>{_SIGN}))?(?P<n1>{_NUM}|\b(?:{'|'.join(_SMALL)})\b)"
    rf"(?:\s*(?:to|-)\s*(?P<n2>{_NUM}))?"
    r"(?:\s*(?:(?P<en>kcal|calories|calorie|cal)\b|(?P<ms>grams|gram|g)\b"
    r"|(?P<pc>%|percent\b)))?",
    re.IGNORECASE,
)
_KINDS = {"en": "energy", "ms": "mass", "pc": "percent"}
_PERCENT_AFTER = re.compile(r"\s*(?:%|percent\b)", re.IGNORECASE)
_APPROX = re.compile(r"\b(?:about|around|roughly|approximately)\s+$", re.IGNORECASE)
_DETERMINER = re.compile(
    r"\b(?:which|this|that|the|any|no|each|every|another|a|an)\s+$", re.IGNORECASE
)
_OF = re.compile(r"\s+of\b", re.IGNORECASE)
# UUIDs, long hex hashes, and ISO dates or datetimes carry no quantity.
_OPAQUE = re.compile(
    r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|[0-9a-f]{16,}"
    r"|\d{4}-\d{2}-\d{2}(?:[T ][\d:.+\-Z]*)?",
    re.IGNORECASE,
)
_FORBIDDEN = re.compile(
    r"\bsafe for\b|\ballerg(?:y|en)[- ]free\b|\bceliac[- ]safe\b|\bmedical"
    r"|\bcures\b|\btreats\b|\bprevents\b|\bdiagnos"
    r"|\bgluten[- ]free\b(?! ingredients)",
    re.IGNORECASE,
)
# The one server sentence that names the claims it refuses; removed before the check.
_SAFETY_SENTENCE = _SAFETY.rsplit(". ", 1)[-1]


@dataclass
class FactSet:
    money: set[Decimal] = field(default_factory=set)
    energy: set[Decimal] = field(default_factory=set)
    mass: set[Decimal] = field(default_factory=set)
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
        return [("mass", _whole_grams(number)), ("mass", tenth)]
    if "kcal" in low:
        return [("energy", value)]
    if "percent" in low:
        return [("percent", value)]
    return [("count", value), *([("mass", value)] if low.endswith("_g") else [])]


def _normalize(text: str) -> str:
    # NFKC would turn a vulgar fraction into digits, so name it as a number word first.
    text = re.sub(_FRACTION, " half ", text)
    folded = _DASHES.sub("-", unicodedata.normalize("NFKC", text))
    return _SPACES.sub(" ", folded)


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
        elif m["usd"] or m["usdn"] or m["mn"]:
            money = True
            raw = m["usd"] or m["usdn"] or m["mn"]
            amount = _number(raw)
            text = str(amount) if raw[0].isalpha() else raw.replace(",", "")
            msign = m["s1"] or m["s2"] or m["s3"]
            cents = amount * (1 if m["cents"] else 100)
            if not _grounded("money", cents, msign, False, facts):
                label = text if m["cents"] else f"${text}"
                unmatched.append(f"{msign or ''}{label}")
        elif (
            m["n1"].lower() == "one"
            and not any(m[name] for name in _KINDS)
            and (_DETERMINER.search(before) or _OF.match(reply, m.end()))
        ):
            continue
        else:
            kind = next((_KINDS[name] for name in _KINDS if m[name]), "count")
            approx = bool(_APPROX.search(before))
            for index, raw in enumerate((m["n1"], m["n2"])):
                if raw is None:
                    continue
                nsign = m["sign"] if index == 0 else None
                if not _grounded(kind, _number(raw), nsign, approx, facts):
                    shown = str(int(_number(raw))) if raw[0].isalpha() else raw
                    unmatched.append(f"{nsign or ''}{shown}")
    return list(dict.fromkeys(unmatched)), word, money


def validate(reply: str, facts: FactSet) -> Verdict:
    text = _normalize(reply)
    unmatched, word, money = _scan(text, facts)
    claims = text.replace(_SAFETY_SENTENCE, " ")
    checks = (
        ("empty", not text.strip()),
        ("too_long", len(text) > MAX_REPLY_CHARS),
        ("store_price", "kroger" in text.lower()),
        ("forbidden_claim", _FORBIDDEN.search(claims) is not None),
        ("number_word", word),
        ("unmatched_number", bool(unmatched)),
    )
    reasons = tuple(code for code, failed in checks if failed)
    return Verdict(not reasons, reasons, tuple(unmatched), money)
