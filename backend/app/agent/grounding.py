"""Check a model-written reply against the facts that tools returned (0022)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE

MAX_REPLY_CHARS = 1200
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_SMALL = "one two three four five six seven eight nine ten eleven twelve".split()
_BIG = (
    r"(?:(?:thir|four|fif|six|seven|eigh|nine)teen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundred|thousand|million|dozen|half|couple)"
)
_TOKEN = re.compile(
    rf"\$\s?(?P<usd>{_NUM})"
    rf"|(?P<dnum>{_NUM})\s+dollars?\b"
    rf"|\b(?P<big>{_BIG})\b"
    rf"|(?:(?<!\w)(?P<sign>[+\-−]))?(?P<n1>{_NUM}|\b(?:{'|'.join(_SMALL)})\b)"
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
_FORBIDDEN = re.compile(
    r"\bsafe for\b|\ballerg(?:y|en)[- ]free\b|\bceliac[- ]safe\b|\bmedical"
    r"|\bcures\b|\btreats\b|\bprevents\b|\bdiagnos"
    r"|\b(?:is|are)\s+(?:\w+\s+)?gluten[- ]free\b"
    r"|\bgluten[- ]free\s+(?:meal|dish|recipe|plan|option|choice)",
    re.IGNORECASE,
)


@dataclass
class FactSet:
    money: set[int] = field(default_factory=set)
    energy: set[Decimal] = field(default_factory=set)
    mass: set[Decimal] = field(default_factory=set)
    whole_grams: set[Decimal] = field(default_factory=set)
    percent: set[Decimal] = field(default_factory=set)
    count: set[Decimal] = field(default_factory=set)
    generic: set[Decimal] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reasons: tuple[str, ...]
    unmatched: tuple[str, ...]
    has_money: bool


def _add_int(key: str, number: int, facts: FactSet) -> None:
    low, value = key.lower(), Decimal(number)
    if low.endswith("_cents"):
        facts.money.add(number)
    elif low.endswith("_mg"):
        whole = Decimal((number + 500) // 1000)
        one_decimal = (value / 1000).quantize(Decimal("0.1"), ROUND_HALF_UP)
        facts.whole_grams.add(whole)
        facts.mass.update((whole, one_decimal))
    elif "kcal" in low:
        facts.energy.add(value)
    elif "percent" in low:
        facts.percent.add(value)
    else:
        facts.count.add(value)
        if low.endswith("_g"):
            facts.mass.add(value)


def _add_text(text: str, facts: FactSet, *, scan_percent: bool = True) -> None:
    for match in re.finditer(_NUM, text):
        value = Decimal(match.group().replace(",", ""))
        facts.generic.add(value)
        if scan_percent and _PERCENT_AFTER.match(text, match.end()):
            facts.percent.add(value)


def _walk(value: object, key: str, facts: FactSet) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        _add_int(key, abs(value), facts)
    elif isinstance(value, str):
        _add_text(value, facts)
    elif isinstance(value, Mapping):
        for name, item in value.items():
            _add_text(str(name), facts, scan_percent=False)
            _walk(item, str(name), facts)
    elif isinstance(value, Sequence):
        for item in value:
            _walk(item, key, facts)


def facts_from_payloads(
    payloads: Sequence[tuple[str, Mapping[str, object]]],
) -> FactSet:
    facts = FactSet()
    for _tool, payload in payloads:
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


def _differs(pool: set[Decimal], value: Decimal) -> bool:
    return any(abs(a - b) == value for a in pool for b in pool)


def _grounded(
    kind: str, value: Decimal, signed: bool, approx: bool, facts: FactSet
) -> bool:
    if kind == "energy":
        # "about 480 kcal" may stand for a fact within 10 of a multiple of ten.
        near = (
            approx
            and value % 10 == 0
            and any(abs(value - fact) < 10 for fact in facts.energy)
        )
        return (
            value in facts.energy or near or (signed and _differs(facts.energy, value))
        )
    if kind == "mass":
        return (
            value in facts.mass
            or value in facts.generic
            or (signed and _differs(facts.whole_grams, value))
        )
    if kind == "percent":
        return value in facts.percent
    return value in facts.count or value in facts.generic


def _scan(reply: str, facts: FactSet) -> tuple[list[str], bool, bool]:
    unmatched: list[str] = []
    word = money = False
    for m in _TOKEN.finditer(reply):
        before = reply[max(0, m.start() - 20) : m.start()]
        if m["big"]:
            word = True
        elif m["usd"] or m["dnum"]:
            money = True
            text = (m["usd"] or m["dnum"]).replace(",", "")
            cents = Decimal(text) * 100
            if cents != cents.to_integral_value() or int(cents) not in facts.money:
                unmatched.append(f"${text}")
        elif m["n1"].lower() == "one" and (
            _DETERMINER.search(before) or _OF.match(reply, m.end())
        ):
            continue
        else:
            kind = next((_KINDS[name] for name in _KINDS if m[name]), "count")
            signed, approx = bool(m["sign"]), bool(_APPROX.search(before))
            for raw in (m["n1"], m["n2"]):
                if raw is None:
                    continue
                value = _number(raw)
                if not _grounded(kind, value, signed, approx, facts):
                    unmatched.append(str(int(value)) if raw[0].isalpha() else raw)
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
