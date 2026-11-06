import re
from dataclasses import dataclass

from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_outcome_propositions import public_tags

_ATOMIC: dict[str, str] = {
    SAMPLE_ESTIMATE_NOTICE: "sample_estimate_notice",
    STALE_SPENDING_WARNING: "stale_budget_warning",
}
_FIXED: dict[str, str] = {
    "the plan is accepted": "accepted",
    "the plan is over budget": "over_budget",
    "the estimate exceeds the available budget": "over_budget",
    "a purchase price is missing, so this estimate is incomplete": "missing_price",
}
_MONEY: dict[str, str] = {
    "the estimate total is": "total_cents",
    "available for this plan:": "available_cents",
    "pending:": "pending_cents",
    "the estimate exceeds the available budget of": "available_cents",
}
_SOURCES: dict[str, str] = {
    "source: your entered budget": "manual",
    "source: demo spending": "fixture",
    "source: plaid sandbox": "plaid_sandbox",
}
_SEPARATOR: re.Pattern[str] = re.compile(r"(?<!\d)\.|\.(?!\d)|[!?;\n\r]+")


@dataclass(frozen=True, slots=True)
class PublicProposition:
    kind: str
    value: str | int | bool


@dataclass(frozen=True, slots=True)
class ClaimParse:
    propositions: tuple[PublicProposition, ...]
    unknown_count: int


def _clauses(answer: str) -> list[str]:
    clauses: list[str] = []
    cursor = 0
    while cursor < len(answer):
        if answer[cursor].isspace():
            cursor += 1
            continue
        notice = next(
            (text for text in _ATOMIC if answer.startswith(text, cursor)), None
        )
        if notice is not None:
            clauses.append(notice)
            cursor += len(notice)
            continue
        separator = _SEPARATOR.search(answer, cursor)
        end = separator.start() if separator is not None else len(answer)
        clause = answer[cursor:end].strip()
        if clause:
            clauses.append(clause)
        cursor = separator.end() if separator is not None else end
    return clauses


def _parse_clause(clause: str, *, vegan: bool) -> tuple[PublicProposition, ...]:
    if clause in _ATOMIC:
        return (PublicProposition(_ATOMIC[clause], True),)
    normalized = clause.casefold()
    if normalized in _FIXED:
        return (PublicProposition(_FIXED[normalized], True),)
    if normalized in _SOURCES:
        return (PublicProposition("source", _SOURCES[normalized]),)
    for prefix, kind in _MONEY.items():
        match = re.fullmatch(
            re.escape(prefix) + r" usd (-?)\$([0-9]+)\.([0-9]{2})", normalized
        )
        if match is None:
            continue
        cents = int(match[2]) * 100 + int(match[3])
        if match[1]:
            cents = -cents
        money = (PublicProposition(kind, cents),)
        if prefix == "the estimate exceeds the available budget of":
            return (PublicProposition("over_budget", True), *money)
        return money
    tags = public_tags(clause, vegan=vegan)
    return tuple(PublicProposition(tag, True) for tag in sorted(tags or ()))


def parse_public_claims(answer: object, *, vegan: bool) -> ClaimParse | None:
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 4096:
        return None
    if any(
        (ord(character) < 32 and character not in "\n\r\t")
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in answer
    ):
        return None
    propositions: list[PublicProposition] = []
    unknown_count = 0
    for clause in _clauses(answer):
        recognized = _parse_clause(clause, vegan=vegan)
        if recognized:
            propositions.extend(recognized)
        else:
            unknown_count += 1
    if not propositions and not unknown_count:
        return None
    return ClaimParse(tuple(propositions), unknown_count)
