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

Direction rule: an unsigned energy, mass, milli, or percent token takes a sign from a
direction word after it (more, less: "2.5 g more fat") or a direction verb before it
(gains, drops: "drops by 2.8 g", carried over "and" or ","). It is then checked like a
signed token, against this turn's deltas only. Money, counts, ranges are never bound.
"changes by N" and "<label> by N" state a change with no direction: such a token
matches a signed delta only, takes the sign of the direction verb that leads its run
("Fat drops by 3 g, protein by 5 g"), and fails when there is none.
"<verb> from X to Y" on energy or a nutrient must read one recorded before and after
pair of that nutrient (FactSet.moves), and the direction verbs and words in the clause
before "from" (back to a sentence end, ";", or a line break, with no length cap; a line
break right after ":" does not end it) must agree with Y - X: "rose sharply from",
"rose, from", and "is down from" all count. An up and a down word in that clause fail.
That holds when such a word, "changes", "changed", "went", or "goes" sits anywhere in
that clause, or when this turn recorded a pair for that subject. Any other
"from X to Y" is a range: both values must be facts of that kind.
Any words may sit inside the shape: X is the first energy or nutrient number after the
"from" in its clause, Y the first number with a unit after a later "to" of that clause
("from just 480 kcal all the way to 500 kcal"). When such a change has X right after
"from" and no Y can be read, X fails. No cue, "by", or "from" lookup has a length cap.
Basis rule: every energy and nutrient fact, absolute or delta, records its basis from
the nearest basis key on its payload path: "serving" under `per_serving`, "total"
under `total`, "100g" under `per_100g`, else None (FactSet.tagged). A basis phrase
right after a claim ("per serving", "per 100 g", "in total", "total", "for the meal",
"for all servings", "for N servings") gives the claim that basis, and it then matches
only a fact of that basis or of none. "for 1 serving" and "per meal" name the serving;
the 1 of "for 1 serving" is no count, but the N of "for N servings" names the total
only when N is a servings count that a payload of this turn states under a `servings`
key (FactSet.servings). Any other N, and any "per <word>" after an energy claim that
is no known basis ("per person"), gives the basis "unmatched", which matches no fact.
A known basis phrase after a comma ("480 kcal, per serving") applies as well.
A signed "(+5 g)" right after an "X to Y" pair, and after
the pair's own basis phrase, has the basis of that pair.
A claim with no basis phrase matches any basis.
A from-to claim also matches the basis of its recorded pair: the phrase after Y, else
the one after X, must name the basis of a pair (FactSet.moves) or the pair has none.
Side rule: every absolute energy and nutrient fact records its side: "before" under a
`before` key, "after" under an `after` key, else None. A value that exists only as a
before-side fact matches only when its clause (split at . ! ? ; a line break, and a
comma) holds one of: from, was, were, before, original, originally, previously, used
to, had ("Previously protein was" and "protein used to be" still bind the label).
Otherwise a claim matches only after-side and side-None facts. A value on
both sides matches. In "X to Y" an unsigned X also counts as before-side when X and Y
are a recorded pair (FactSet.moves): the server templates print "protein 26 to 15 g".
Signed changes have no side. A fact with no tag (a hand-built FactSet) has no basis
and no side.
A reply over MAX_REPLY_CHARS fails with `too_long` before any scan.

Medical rule: a reply that names a health condition or marker fails with
`medical_claim` (0025): diabet, glycemi, insulin, glucose, blood sugar, blood
pressure, hypertens, cholesterol, pregnan, anywhere in the same text as the diet
labels (inside a word, after "_", "antidiabetic"). "blood" and "sugar" or "pressure"
may be joined or split by any run of non-alphanumerics ("blood **sugar**",
"blood_sugar", "bloodsugar"). The server sentences stay exempt.
Spaced letters do not match.

Digit rule: any digit, number, or letter-number character other than ASCII 0-9
(superscripts, circled or fullwidth digits, other scripts, "Ⅻ") fails with
`unsupported_character` before folding. Vulgar fractions are the exception.
An ellipsis, a spaced dot, or an abbreviation ("e.g.", "Dr.", "U.S.") does not end a
sentence, so a server sentence after one is not exempt.
"""

import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.agent.catalog_tool import _SAFETY, TOOL_NAME
from app.agent.chat_answer import _DIET, _diet_conflict_answer
from app.agent.nutrient_grounding import (
    BASIS_KEYS,
    DOWN_VERBS,
    DOWN_WORDS,
    LABEL_BY,
    NUTRIENT_KEYS,
    SIDE_KEYS,
    UNMATCHED,
    UP_VERBS,
    UP_WORDS,
    NutrientFact,
    TaggedFact,
    basis_count,
    before_marker,
    claim_basis,
    energy_basis,
    nutrient_bindings,
    nutrient_grounded,
    pair_delta,
    tag_ok,
)
from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import RECIPES
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.meal_tags import CARNIVORE_NOTE, KETO_NOTE

MAX_REPLY_CHARS = 1200
# Every reason code validate can emit; a test keeps this list and validate in step.
REASON_CODES = frozenset(
    ("unsupported_character", "empty", "too_long", "store_price", "forbidden_claim")
    + ("medical_claim", "number_word", "unmatched_number")
)
APPROX_WINDOW = 10
_NUM = r"(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"
# normalize maps every dash and minus sign to a hyphen-minus first.
_SIGN = r"[+\-]"
_MINUS = "-"
_DASHES = re.compile("[‐-―−﹣－]")
_SPACES = re.compile(r"[^\S\n]")
_SPACE_RUNS = re.compile(r" {2,}")
_QUOTES = str.maketrans("‘’“”", "''\"\"")
_UNSUPPORTED = re.compile(r"[^A-Za-z0-9 \n\t.,;:!?'\"()\[\]$%/+\-&*#_¢]")
_SMALL = "one two three four five six seven eight nine ten eleven twelve".split()
_WORD = rf"\b(?:{'|'.join(_SMALL)})\b"
_BIG = (
    r"(?:(?:thir|four|fif|six|seven|eigh|nine)teen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?|half"
    r"|halves|couple|zero|twice|double|triple|quadruple|quarters?|once|tens"
    r"|thirds?|fifths?|few|several|(?:fourth|sixth|seventh|eighth|ninth|tenth)s?"
    r"|pair)"
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
# A direction word right after a unit gives an unsigned change its sign.
_DIRECTION = re.compile(
    rf"\s*\b(?:(?P<up>{UP_WORDS})|(?P<down>{DOWN_WORDS}))\b", re.IGNORECASE
)
# A direction verb right before a unit number gives it a sign; "and" or "," carry it on.
# The verbs and direction words come from nutrient_grounding, so a word added there
# applies to the nutrient binder as well.
_VERB = re.compile(
    rf"\b(?:(?P<up>{UP_VERBS})|(?P<down>{DOWN_VERBS}))\b",
    re.IGNORECASE,
)
_RUN_END = re.compile(
    rf"from|to|while|but|whereas|than|{UP_VERBS}|{DOWN_VERBS}", re.IGNORECASE
)
_BASE = frozenset("gain add rise increase lose drop fall decrease reduce".split())
_ABOUT = r"(?:(?:about|around|roughly|approximately) +)?"
_LEAD = re.compile(rf" *(?:by +)?{_ABOUT}(?:\*\*)?", re.IGNORECASE)
_CARRY = re.compile(
    rf"(?:\*\*)?((?: +[A-Za-z]+){{0,3}}?) *(?:, *and\b|,|\band\b) *{_ABOUT}(?:\*\*)?",
    re.IGNORECASE,
)
# "protein by 5 g" elides its verb and inherits the sign of the run it follows.
_LABEL_BY = re.compile(LABEL_BY, re.IGNORECASE)
# A number led by "changes by" or "<label> by" states a change with no direction. The
# match ends where the number starts, however long the run of spaces before it is.
_BARE_BY = re.compile(
    rf"(?:{LABEL_BY}|\bchang(?:e|es|ed|ing)[^\S\n]+)by[^\S\n]+{_ABOUT}",
    re.IGNORECASE,
)
# "from X to Y": the direction comes from _CUE. The words may sit anywhere in the shape.
_FROM_WORD = re.compile(r"\bfrom\b", re.IGNORECASE)
_TO_WORD = re.compile(r"\bto\b", re.IGNORECASE)
# What may stand between "from" or "to" and a number that it leads directly.
_GAP = re.compile(rf"[^\S\n]+{_ABOUT}", re.IGNORECASE)
# Every direction verb or word in the clause before "from", whatever sits between.
# "changes", "changed", "went", and "goes" lead a change with no direction of its own.
_CUE = re.compile(
    rf"\b(?:(?P<up>{UP_VERBS}|{UP_WORDS})|(?P<down>{DOWN_VERBS}|{DOWN_WORDS})"
    r"|(?P<flat>changes|changed|went|goes))\b",
    re.IGNORECASE,
)
_CLAUSE_START = re.compile(r"[!?;\n]|\.(?!\d)")
# A line break right after ":" (a bullet list follows) does not start a clause.
_COLON_BREAK = re.compile(r":[^\S\n]*\n")
# A base-form verb at a sentence start is an instruction ("Add 5 g"), not a change.
_IMPERATIVE = re.compile(r"(?:\A|[.!?:\n])[ *\-]*\Z")
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
    r"|purchased|checkedout|order[a-z]{0,8}placed|paid"
    r"|toyourplan|fromyourplan|updatedyourplan|changedyourplan|yourplannowhas"
    r"|yourplanisnow|iaddedit|iremovedit"
)
# Diet labels match from a word start on the folded text: "tofu" does not match
# "keto"; "vegetarians" and "ketogenic" do. Spaced letters do not match.
# Only the catalog's own sentences (see _SERVER_SENTENCE) may use a diet label.
_DIET_LABEL = re.compile(
    r"\b(?:vegan|vegetarian|keto|paleo|halal|kosher"
    r"|(?:plant[- ]?based|(?:dairy|lactose|nut|egg|soy|sugar)[- ]?free"
    r"|low[- ]?(?:sodium|fat)|high[- ]?fiber))",
    re.IGNORECASE,
)
# A health condition or marker fails with `medical_claim` (0025). Same text as
# _DIET_LABEL, but each term matches anywhere, not only at a word start: "_diabetic_"
# and "hyperglycemia" must fail. "kidney", "heart", "gout", and "renal" are left out
# on purpose.
_MEDICAL = re.compile(
    r"(?:diabet|glycemi|insulin|glucose|blood[^A-Za-z0-9]*(?:sugar|pressure)"
    r"|hypertens|cholesterol|pregnan)",
    re.IGNORECASE,
)
# A word split by a hyphen at a line break ("vegetar-\nian") is one word.
_LINE_HYPHEN = re.compile(r"(?<=[A-Za-z])-[^\S\n]*\n\s*(?=[A-Za-z])")
# A number, whitespace, then a scale word or multiplier ("$12 K", "2 x the protein",
# "3 times", "3-fold", "two x").
_SCALED = re.compile(
    rf"(?:{_NUM}|{_WORD})(?:\s+(?:k|m|b|mm|mn|bn|bln|tn|mil|grand|thousand|million"
    r"|billion|trillion|x|times)|\s*-\s*fold)\b",
    re.IGNORECASE,
)


def _diet_sentences() -> set[str]:
    """The exact sentences that the server templates print with a diet label."""
    sentences = {*re.split(r"(?<=\.) ", KETO_NOTE), re.split(r"(?<=\.) ", _DIET)[0]}
    for recipe_id, recipe in RECIPES.items():
        for ingredient_id, _quantity in recipe.ingredients:
            for diet in ("vegetarian", "vegan"):
                error: dict[str, object] = {
                    "error_code": "diet_conflict",
                    "recipe_id": recipe_id,
                    "ingredient_id": ingredient_id,
                    "diet": diet,
                }
                answer = _diet_conflict_answer(error)
                if answer is not None:
                    sentences.add(re.split(r"(?<=\.) ", answer)[0])
    return sentences


# The server notes name the claims they refuse and the diets they state; each exact
# sentence is removed verbatim from the raw reply before the claim check, and nothing
# else is exempt.
_SERVER_SENTENCE = re.compile(
    r"(?:\A\s*|(?<=[.!?])\s+)(?:"
    + "|".join(
        re.escape(s)
        for s in (*re.split(r"(?<=\.) ", _SAFETY), *sorted(_diet_sentences()))
    )
    # The substitute and price tools print this one with the plan's servings: at the
    # start, after any .!? and whitespace, or at the start of a "- " list line.
    + r"|Servings from your plan: \d+\.)"
    + r"|(?<![^\n])- Servings from your plan: \d+\."
)
# A sentence end is a word of 3+ letters or digits, then one of .!? ("Dr.", "No.",
# "e.g.", "U.S.", "a.m.", ". . ." and "..." are not sentence ends).
_SENTENCE_END = re.compile(r"(?<![\w.])\w{3,}[.!?]\Z")

Move = tuple[str, str, Decimal, Decimal, str | None]


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
    nutrition: set[NutrientFact] = field(default_factory=set)
    # Each before and after pair of one key as (nutrient or "energy", kind, before,
    # after, basis); a "from X to Y" claim must read one of them, with its basis.
    moves: set[Move] = field(default_factory=set)
    # Every nutrient and energy fact again, with the basis ("serving", "total",
    # "100g") and side ("before", "after") of its payload path; None when the path
    # names none.
    tagged: set[TaggedFact] = field(default_factory=set)
    # Every count that a payload states under a `servings` key; only these name the
    # total basis in "for N servings".
    servings: set[Decimal] = field(default_factory=set)


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
    """The text every check runs on: folded, with each space run mapped to " "."""
    return _SPACE_RUNS.sub(" ", _SPACES.sub(" ", _fold(text)))


def _without_server_sentences(reply: str, *, mask: bool = False) -> str:
    def drop(match: re.Match[str]) -> str:
        before = reply[: match.start()]
        removed = " " * len(match.group()) if mask else " "
        if "Servings from your plan: " in match.group():
            return removed  # the pattern already fixed its position
        if before and not _SENTENCE_END.search(before):
            return match.group()
        return removed

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


def _tag(
    facts: FactSet,
    subject: str,
    entries: Sequence[tuple[str, Decimal]],
    delta: bool,
    basis: str | None,
    side: str | None,
) -> None:
    """Tag nutrient facts, or the energy ones when the subject is "energy"."""
    facts.tagged.update(
        (subject, kind, delta, number, basis, side)
        for kind, number in entries
        if subject != "energy" or kind == "energy"
    )


def _changes(
    before: Mapping[object, object],
    after: Mapping[object, object],
    facts: FactSet,
    basis: str | None = None,
) -> None:
    """Record after minus before for every numeric key that both sides share."""
    for name in before.keys() & after.keys():
        if _is_id(str(name).lower()):
            continue
        old, new = before[name], after[name]
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            _changes(old, new, facts, BASIS_KEYS.get(str(name).lower(), basis))
        elif type(old) is int and type(new) is int:
            now, was = _kinds(str(name), new), _kinds(str(name), old)
            subject = NUTRIENT_KEYS.get(str(name))
            facts.moves.update(
                (subject or k, k, b, a, basis)
                for (k, a), (_, b) in zip(now, was, strict=False)
                if subject or k == "energy"
            )
            changed = [(k, a - b) for (k, a), (_, b) in zip(now, was, strict=False)]
            changed.extend(_kinds(str(name), new - old))
            if subject:
                facts.nutrition.update((subject, k, True, n) for k, n in changed)
                _tag(facts, subject, changed, True, basis, None)
                continue
            facts.deltas.update(changed)
            _tag(facts, "energy", changed, True, basis, None)


def _walk(
    value: object,
    key: str,
    facts: FactSet,
    delta: bool = False,
    forced: str | None = None,
    basis: str | None = None,
    side: str | None = None,
) -> None:
    low = key.lower()
    basis, side = BASIS_KEYS.get(low, basis), SIDE_KEYS.get(low, side)
    if isinstance(value, bool) or value is None:
        return
    if _is_id(low) and low != "fdc_id":
        return
    if _is_delta(low):
        delta, forced = True, "percent" if "percent" in low else forced
    if key in NUTRIENT_KEYS and type(value) is not int:
        return
    if isinstance(value, int):
        if low == "servings" and not delta:
            facts.servings.add(Decimal(value))
        entries = _kinds(key, value, forced)
        if key in NUTRIENT_KEYS:
            facts.nutrition.update(
                (NUTRIENT_KEYS[key], kind, delta, number) for kind, number in entries
            )
            _tag(facts, NUTRIENT_KEYS[key], entries, delta, basis, side)
            return
        for kind, number in entries:
            if delta:
                facts.deltas.add((kind, number))
            else:
                getattr(facts, kind).add(number)
        _tag(facts, "energy", entries, delta, basis, side)
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
            _changes(value["before"], value["after"], facts, basis)
        for name, item in value.items():
            if not (delta or _is_delta(str(name).lower())):
                _add_text(str(name), facts, scan_percent=False)
            _walk(item, str(name), facts, delta, forced, basis, side)
    elif isinstance(value, Sequence):
        for item in value:
            _walk(item, key, facts, delta, forced, basis, side)


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
    kind: str,
    value: Decimal,
    sign: str | None,
    approx: bool,
    facts: FactSet,
    basis: str | None = None,
    before: bool = False,
) -> bool:
    pool: set[Decimal] = getattr(facts, kind)

    def fits(delta: bool, number: Decimal) -> bool:
        """An energy fact must also have the claim's basis and side."""
        fact = ("energy", kind, delta, number)
        return kind != "energy" or tag_ok(facts.tagged, fact, basis, before)

    if sign:
        signed = -value if sign in _MINUS else value
        return ((kind, signed) in facts.deltas and fits(True, signed)) or (
            signed < 0 and signed in pool and fits(False, signed)
        )
    if kind == "energy":
        # "about 480 kcal" may stand for an energy fact within 9 of 480.
        near = (
            approx
            and value % 10 == 0
            and any(abs(value - f) < APPROX_WINDOW and fits(False, f) for f in pool)
        )
        return (value in pool and fits(False, value)) or near
    return value in pool or (kind in ("mass", "count") and value in facts.generic)


def _skip_label(text: str, pos: int) -> int:
    """Step over a label and its "by" ("reduces calories by 20", ", protein by 5")."""
    label = _LABEL_BY.match(text, pos)
    if not label:
        return pos
    lead = _LEAD.match(text, label.end())
    return lead.end() if lead else label.end()


def _verb_signs(text: str) -> dict[int, str]:
    """Map the start of each unit token that a direction verb binds to its sign."""
    signs: dict[int, str] = {}
    for verb in _VERB.finditer(text):
        if verb.group().lower() in _BASE and _IMPERATIVE.search(text[: verb.start()]):
            continue
        sign = _MINUS if verb["down"] else "+"
        start = _LEAD.match(text, verb.end())
        pos = _skip_label(text, start.end() if start else verb.end())
        while token := _TOKEN.match(text, pos):
            if not (token["n1"] and any(token[n] for n in _KINDS)):
                break
            if token["sign"] or token["n2"]:
                break
            signs[token.start()] = sign
            gap = _CARRY.match(text, token.end())
            if not gap or any(_RUN_END.fullmatch(w) for w in gap[1].split()):
                break
            pos = _skip_label(text, gap.end())
    return signs


@dataclass(frozen=True, slots=True)
class _Clauses:
    """Clause starts and the cue words of one reply, found once and bisected.

    The text is `plain`: "*", "_", and "#" are already spaces, so no run of them can
    hide a cue, and no lookup has a length cap.
    """

    size: int
    starts: list[int]
    cues: list[int]
    kinds: list[str]
    by_ends: frozenset[int]  # where each "changes by" or "<label> by" lead ends
    froms: list[int]  # the start of each "from"
    tos: list[int]  # the start of each "to"

    def before(self, stop: int) -> tuple[bool, bool, bool]:
        """Whether an up, a down, and a flat word sit in the clause before `stop`."""
        first, _ = self.bounds(stop)
        found = self.kinds[bisect_left(self.cues, first) : bisect_left(self.cues, stop)]
        return "up" in found, "down" in found, "flat" in found

    def bounds(self, pos: int) -> tuple[int, int]:
        """The start and the end of the clause that holds `pos`."""
        at = bisect_right(self.starts, pos)
        return (
            self.starts[at - 1] if at else 0,
            self.starts[at] if at < len(self.starts) else self.size,
        )

    def origin(self, pos: int, floor: int) -> int | None:
        """The nearest "from" before `pos`, in its clause and after `floor`."""
        at = bisect_left(self.froms, pos) - 1
        if at < 0:
            return None
        src = self.froms[at]
        return src if src > floor and src >= self.bounds(pos)[0] else None


def _clauses(plain: str) -> _Clauses:
    held = {m.end() - 1 for m in _COLON_BREAK.finditer(plain)}
    starts = [m.end() for m in _CLAUSE_START.finditer(plain) if m.start() not in held]
    cues = list(_CUE.finditer(plain))
    return _Clauses(
        len(plain),
        starts,
        [m.start() for m in cues],
        [m.lastgroup or "" for m in cues],
        frozenset(m.end() for m in _BARE_BY.finditer(plain)),
        [m.start() for m in _FROM_WORD.finditer(plain)],
        [m.start() for m in _TO_WORD.finditer(plain)],
    )


def _target(
    plain: str,
    tokens: Sequence[re.Match[str]],
    starts: Sequence[int],
    clauses: _Clauses,
    index: int,
) -> re.Match[str] | None:
    """The Y of "from X to Y" for the X at `index`: a number after a later "to".

    Words may sit before the "to" and between it and Y. Y is the first number after
    the "to" in X's clause that has a unit, or none and directly follows the "to".
    """
    token = tokens[index]
    end = clauses.bounds(token.start())[1]
    at = bisect_left(clauses.tos, token.end())
    if at == len(clauses.tos) or clauses.tos[at] >= end:
        return None
    after = clauses.tos[at] + len("to")
    for other in tokens[bisect_left(starts, after) :]:
        if other.start() >= end:
            break
        if not other["n1"]:
            continue
        if other["n2"]:
            return None
        if any(other[name] for name in _KINDS) or _GAP.fullmatch(
            plain, after, other.start()
        ):
            return other
    return None


def _paired(
    moves: Collection[Move],
    pair: tuple[str, str, Decimal, Decimal],
    basis: str | None = None,
) -> bool:
    """Whether a recorded pair has the claim's basis; no basis matches any pair.

    A known basis matches a pair of that basis or of none, and UNMATCHED no pair.
    """
    if basis == UNMATCHED:
        return False
    named = (None, *BASIS_KEYS.values()) if basis is None else (None, basis)
    return any((*pair, have) in moves for have in named)


def _pair_basis(
    claims: str,
    kind: str,
    ends: Sequence[re.Match[str]],
    starts: Sequence[int],
    servings: Collection[Decimal],
) -> str | None:
    """The basis phrase after Y of a from-to claim, else the one after X, else None."""

    def read(end: re.Match[str], limit: int) -> str | None:
        if kind == "energy":
            return energy_basis(claims, end.end(), limit, servings)
        return claim_basis(claims, end.end(), servings)

    at = bisect_right(starts, ends[1].start())
    named = read(ends[1], starts[at] if at < len(starts) else len(claims))
    if named is None and ends[0] is not ends[1]:
        named = read(ends[0], ends[1].start())
    return named


def _from_to(
    plain: str,
    tokens: Sequence[re.Match[str]],
    nutrients: Mapping[int, str | None],
    facts: FactSet,
    clauses: _Clauses,
    claims: str,
) -> dict[int, bool]:
    """Judge each energy or nutrient "from X to Y" claim by token start.

    X is the first energy or nutrient number after a "from" in its clause, and Y the
    number after a later "to" of that clause; any words may sit between them ("from
    just 480 kcal all the way to 500 kcal").
    Only a change is judged: a direction verb or word, or "changes", "changed", "went",
    or "goes", sits in the clause before the "from", or this turn recorded a pair for
    that subject. Any other "from X to Y" is a range, and both values are checked as
    plain facts.
    X and Y must be the before and after sides of one recorded pair, Y - X must be a
    signed delta of that subject, and a direction verb must agree with Y - X.
    The basis phrase after Y, else after X, must name the basis of that pair (see
    _paired); with no phrase, a pair of any basis matches.
    When a change leaves X right after "from" with no Y to read, X fails.
    """
    verdicts: dict[int, bool] = {}
    starts = [token.start() for token in tokens]
    floor = -1  # the start of the last energy or nutrient number
    for index, token in enumerate(tokens):
        if not (token["n1"] and (token["en"] or token.start() in nutrients)):
            continue
        src, floor = clauses.origin(token.start(), floor), token.start()
        if src is None:
            continue
        other = None if token["n2"] else _target(plain, tokens, starts, clauses, index)
        ends = (token, other or token)
        second = token["n2"] or (other["n1"] if other else None)
        kinds = {_KINDS[n] for end in ends for n in _KINDS if end[n]}
        if not kinds - {"percent"}:
            continue
        kind = kinds.pop() if len(kinds) == 1 else ""
        subject = "energy" if kind == "energy" else nutrients.get(token.start())
        if kind != "energy" and nutrients.get(ends[1].start()) != subject:
            subject = None
        up, down, flat = clauses.before(src)
        led = up or down or flat
        if not (led or any(move[0] == subject for move in facts.moves)):
            continue  # "From 474 to 489 kcal" is a range across options, not a change
        if second is None:
            if _GAP.fullmatch(plain, src + len("from"), token.start()):
                verdicts[token.start()] = False  # a change from X, with no Y to read
            continue
        before, after = (
            _number(raw) * (1000 if end["kg"] else 1)
            for raw, end in zip((token["n1"], second), ends, strict=True)
        )
        change = after - before
        basis = _pair_basis(claims, kind, ends, starts, facts.servings)
        ok = bool(
            kind
            and subject
            and not any(end["sign"] for end in ends)
            and _paired(facts.moves, (subject, kind, before, after), basis)
            and (
                (kind, change) in facts.deltas
                if subject == "energy"
                else (subject, kind, True, change) in facts.nutrition
            )
            and not (up and down)
            and not (up and change <= 0)
            and not (down and change >= 0)
        )
        for end in ends:  # a number that one claim fails stays failed
            verdicts[end.start()] = verdicts.get(end.start(), True) and ok
    return verdicts


def _scan(reply: str, facts: FactSet) -> tuple[list[str], bool, bool]:
    unmatched: list[str] = []
    word = money = False
    plain = re.sub(r"[*_#]", " ", reply)
    lead = _verb_signs(plain)
    tokens = list(_TOKEN.finditer(plain))
    safe = _without_server_sentences(reply, mask=True)
    nutrients = nutrient_bindings(safe, tokens)
    claims = re.sub(r"[*_#]", " ", safe)  # same offsets as plain, no server sentence
    clauses = _clauses(plain)
    moves = _from_to(plain, tokens, nutrients, facts, clauses, claims)
    # Where the next number starts, so that a basis is read only up to it.
    stops = [token.start() for token in tokens[1:]] + [len(claims)]
    plan_counts = {
        match.start(1)
        for match in re.finditer(r"Servings from your plan: (\d+)\.", reply)
    }
    served: set[int] = set()  # the N of "for N servings" after a claim
    for index, m in enumerate(tokens):
        before = plain[max(0, m.start() - 20) : m.start()]
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
            for part, raw in enumerate(amounts):
                if raw is None:
                    continue
                amount = _number(raw)
                text = str(amount) if raw[0].isalpha() else raw.replace(",", "")
                sign = msign if part == 0 else None
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
        elif m.start() in served and _number(m["n1"]) == 1:
            continue  # "for 1 serving" names the serving; it states no count
        else:
            kind = next((_KINDS[name] for name in _KINDS if m[name]), "count")
            approx = bool(_APPROX.search(before))
            directionless = kind != "count" and m.start() in clauses.by_ends
            bound = None
            if kind != "count" and not (m["sign"] or m["n2"]):
                bound = _DIRECTION.match(plain, m.end())
            subject = nutrients[m.start()] if m.start() in nutrients else None
            subject = "energy" if kind == "energy" and not subject else subject
            basis = None
            if subject and kind == "energy":
                basis = energy_basis(claims, m.end(), stops[index], facts.servings)
            elif subject:
                basis = claim_basis(claims, m.end(), facts.servings)
            if subject and index and basis is None:
                # "(+5 g)" after "20 to 25 g per serving" has the basis of the pair.
                if pair_delta(claims, tokens[index - 1], m):
                    basis = claim_basis(claims, tokens[index - 1].end(), facts.servings)
            if subject and (own := basis_count(claims, m.end())) is not None:
                served.add(own)
            marker = bool(subject) and before_marker(claims, m.start())
            for part, raw in enumerate((m["n1"], m["n2"])):
                if raw is None:
                    continue
                nsign = m["sign"] if part == 0 else None
                if bound:
                    nsign = _MINUS if bound["down"] else "+"
                elif part == 0 and not m["sign"]:
                    nsign = lead.get(m.start())
                value = _number(raw) * (1000 if m["kg"] else 1)
                if m.start() in plan_counts:
                    grounded = (
                        kind == "count" and nsign is None and value in facts.count
                    )
                else:
                    # In "X to Y" the X may be the before side of a recorded pair.
                    upper = _number(m["n2"] or "0") * (1000 if m["kg"] else 1)
                    early = marker or bool(
                        part == 0
                        and m["n2"]
                        and not nsign
                        and subject is not None
                        and _paired(facts.moves, (subject, kind, value, upper))
                    )
                    grounded = (
                        nutrient_grounded(
                            nutrients[m.start()],
                            kind,
                            value,
                            nsign,
                            facts.nutrition,
                            facts.tagged,
                            basis,
                            early,
                        )
                        if m.start() in nutrients
                        else _grounded(kind, value, nsign, approx, facts, basis, early)
                    )
                    if kind == "count" and m.start() in moves:
                        grounded = moves[m.start()]  # "from 500 kcal to 480"
                    # A change with no direction needs a sign; a from-to claim a pair.
                    grounded = grounded and not (directionless and nsign is None)
                    grounded = grounded and moves.get(m.start(), True)
                if not grounded:
                    shown = str(int(_number(raw))) if raw[0].isalpha() else raw
                    unmatched.append(f"{nsign or ''}{shown}")
    unmatched.extend(
        m[1] for m in _ATTACHED.finditer(reply) if m[2].lower() not in _UNITS
    )
    unmatched.extend(m[0] for m in _SCALED.finditer(reply))
    return list(dict.fromkeys(unmatched)), word, money


def validate(reply: str, facts: FactSet) -> Verdict:
    # The scan cost grows with the reply, so a long reply is refused before any scan.
    if len(reply) > MAX_REPLY_CHARS:
        return Verdict(False, ("too_long",), (), False)
    if _foreign_number(reply) or _UNSUPPORTED.search(_fold(reply)):
        return Verdict(False, ("unsupported_character",), (), False)
    text = normalize(reply)
    unmatched, word, money = _scan(text, facts)
    kept = _without_server_sentences(reply)
    claims = normalize(kept)
    diet_text = normalize(_LINE_HYPHEN.sub("", _fold(kept)))
    # Only the server appends the stale warning; a model copy of it is a claim.
    stale_copy = _squash(STALE_SPENDING_WARNING) in _squash(text)
    checks = (
        ("empty", not text.strip()),
        ("store_price", "kroger" in _squash(text)),
        (
            "forbidden_claim",
            stale_copy
            or _FORBIDDEN.search(_squash(claims)) is not None
            or _DIET_LABEL.search(diet_text) is not None,
        ),
        ("medical_claim", _MEDICAL.search(diet_text) is not None),
        ("number_word", word),
        ("unmatched_number", bool(unmatched)),
    )
    reasons = tuple(code for code, failed in checks if failed)
    return Verdict(not reasons, reasons, tuple(unmatched), money)
