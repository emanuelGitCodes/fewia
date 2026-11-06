"""Okapi BM25 order for meals that a word query already selected.

The order never adds or removes a meal. A document is the recipe id words,
counted twice, plus the words of the ingredient names. IDF and average length
come from every supported recipe.
"""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import cache

from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS

K1 = 1.2
B = 0.75


def stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _tokens(text: str) -> list[str]:
    return [stem(word) for word in re.findall(r"[a-z]+", text.lower())]


def idf(documents: int, containing: int) -> float:
    """Okapi IDF with the +1 inside the log, so it is never negative."""
    return math.log(1 + (documents - containing + 0.5) / (containing + 0.5))


def bm25_score(
    terms: Sequence[str],
    document: Sequence[str],
    frequencies: Mapping[str, int],
    documents: int,
    average_length: float,
) -> float:
    counts = Counter(document)
    length_norm = 1 - B + B * len(document) / average_length
    score = 0.0
    for term in dict.fromkeys(terms):
        count = counts[term]
        if count:
            score += (
                idf(documents, frequencies.get(term, 0))
                * count
                * (K1 + 1)
                / (count + K1 * length_norm)
            )
    return score


@cache
def _corpus() -> tuple[dict[str, list[str]], Counter[str], float]:
    docs: dict[str, list[str]] = {}
    for recipe_id in SUPPORTED_RECIPE_IDS:
        words = _tokens(recipe_id)
        names = (INGREDIENTS[item].name for item, _ in RECIPES[recipe_id].ingredients)
        docs[recipe_id] = [*words, *words, *(t for n in names for t in _tokens(n))]
    frequencies = Counter(term for doc in docs.values() for term in set(doc))
    average = sum(len(doc) for doc in docs.values()) / len(docs)
    return docs, frequencies, average


def bm25_order(words: Sequence[str], recipe_ids: Sequence[str]) -> list[str]:
    docs, frequencies, average = _corpus()
    terms = [stem(word) for word in words]
    scores = {
        rid: bm25_score(terms, docs.get(rid, []), frequencies, len(docs), average)
        for rid in recipe_ids
    }
    return sorted(recipe_ids, key=lambda rid: -scores[rid])
