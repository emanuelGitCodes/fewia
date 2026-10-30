"""Check a model-written reply against the facts that tools returned (0022)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.agent.catalog_tool import _SAFETY, TOOL_NAME
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.meal_tags import CARNIVORE_NOTE, KETO_NOTE

MAX_REPLY_CHARS = 1200
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_SIGN = r"[+\-−]"
_SMALL = "one two three four five six seven eight nine ten eleven twelve".split()
_BIG = (
    r"(?:(?:thir|four|fif|six|seven|eigh|nine)teen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundred|thousand|million|billion|dozen|half|couple"
    r"|zero|twice|double|triple|quadruple|quarter|once)"
)
_TOKEN = re.compile(
    rf"(?:(?<!\w)(?P<s1>{_SIGN}))?(?:\bUSD\s*)?(?P<s2>{_SIGN})?\$\s?(?P<usd>{_NUM})"
    rf"|(?:(?<!\w)(?P<s3>{_SIGN}))?(?:\bUSD\s+(?P<usdn>{_NUM})"
    rf"|(?P<mn>{_NUM})\s+(?:(?P<mu>dollars?|USD)|(?P<cents>cents?))\b)"
    rf"|\b(?P<big>{_BIG})\b"
    rf"|(?:(?<!\w)(?P<sign>{_SIGN}))?(?P<n1>{_NUM}|\b(?:{'|'.join(_SMALL)})\b)"
    rf"(?:\s*(?:to|-|–)\s*(?P<n2>{_NUM}))?"
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
    r"|(?<!cannot claim )\bgluten[- ]free\b(?! ingredients)",
    re.IGNORECASE,
)


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


def _add_text(text: str, facts: FactSet, *, scan_percent: bool = True) -> None:
    if _OPAQUE.fullmatch(text.strip()):
        return
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
    if (low == "id" or low.endswith(("_id", "_ids"))) and low != "fdc_id":
        return
    if low.startswith("delta_"):
        delta, forced = True, "percent" if "percent" in low else forced
    if isinstance(value, int):
        for kind, number in _kinds(key, value, forced):
            if delta:
                facts.deltas.add((kind, number))
            else:
                getattr(facts, kind).add(number)
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
        signed = -value if sign in "-−" else value
        return (kind, signed) in facts.deltas or (signed < 0 and signed in pool)
    if kind == "energy":
        # "about 480 kcal" may stand for a fact within 10 of a multiple of ten.
        near = approx and value % 10 == 0 and any(abs(value - f) < 10 for f in pool)
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
            text = (m["usd"] or m["usdn"] or m["mn"]).replace(",", "")
            msign = m["s1"] or m["s2"] or m["s3"]
            cents = Decimal(text) * (1 if m["cents"] else 100)
            if not _grounded("money", cents, msign, False, facts):
                label = text if m["cents"] else f"${text}"
                unmatched.append(f"{msign or ''}{label}")
        elif m["n1"].lower() == "one" and (
            _DETERMINER.search(before) or _OF.match(reply, m.end())
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
    unmatched, word, money = _scan(reply, facts)
    checks = (
        ("empty", not reply.strip()),
        ("too_long", len(reply) > MAX_REPLY_CHARS),
        ("store_price", "kroger" in reply.lower()),
        ("forbidden_claim", _FORBIDDEN.search(reply) is not None),
        ("number_word", word),
        ("unmatched_number", bool(unmatched)),
    )
    reasons = tuple(code for code, failed in checks if failed)
    return Verdict(not reasons, reasons, tuple(unmatched), money)
