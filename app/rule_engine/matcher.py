"""
Symptom matching — pure functions, no DB, so it can be tested directly.

Scoring (per symptom):
  +1 per query word that appears in the title
  +2 per query word that appears in any keyword phrase
  +3 per keyword phrase fully contained in the query (strong signal)
  +1 if the symptom belongs to the bot the intent router guessed

A minimum score is required so a single generic word never "matches".
"""
from __future__ import annotations

import re
from typing import Iterable, Protocol

STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "been", "my", "me", "i", "it",
    "its", "to", "of", "on", "in", "at", "for", "and", "or", "but", "with", "when", "what",
    "how", "do", "does", "did", "can", "will", "should", "this", "that", "there", "if", "so",
    "up", "out", "after", "before", "not", "no", "won", "t", "don", "doesn", "isn", "s",
    "pc", "computer", "please", "help", "need", "want", "have", "has", "get", "getting",
    "keep", "keeps", "very", "really", "lot", "just", "some", "any", "work", "works", "working",
}

MIN_SCORE = 2


class SymptomLike(Protocol):
    title: str
    keywords: str | None
    bot_type: str


def _stem(word: str) -> str:
    """Very light stemming so 'dusty'/'dust', 'heating'/'heat', 'drives'/'drive' match."""
    if len(word) > 4:
        for suffix in ("ing", "ed", "y", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[: -len(suffix)]
    return word


def tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def score(query_tokens: set[str], symptom: SymptomLike, bot: str | None) -> tuple[int, int]:
    """Returns (total score, title overlap). Title overlap is the tie-breaker."""
    title_overlap = len(query_tokens & tokens(symptom.title))
    kw_tokens: set[str] = set()
    phrase_bonus = 0
    if symptom.keywords:
        for phrase in symptom.keywords.split(","):
            phrase_tokens = tokens(phrase)
            if not phrase_tokens:
                continue
            kw_tokens |= phrase_tokens
            if phrase_tokens == query_tokens:
                phrase_bonus += 4  # the user typed (almost) exactly this keyword phrase
            elif len(phrase_tokens) >= 2 and phrase_tokens <= query_tokens:
                phrase_bonus += 3
    total = title_overlap + 2 * len(query_tokens & kw_tokens) + phrase_bonus
    if total and bot and symptom.bot_type == bot:
        total += 1
    return total, title_overlap


def best_match(query: str, symptoms: Iterable[SymptomLike], bot: str | None = None):
    q = tokens(query)
    if not q:
        return None
    best, best_key = None, (0, 0)
    for s in symptoms:
        key = score(q, s, bot)
        if key > best_key:
            best, best_key = s, key
    return best if best_key[0] >= MIN_SCORE else None