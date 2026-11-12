"""Which lexicon entities a piece of text actually mentions.

The one shared definition of "mention" for the entity-density gate, the EER
scorer, and the dataset filter (phase-3b item 3B-1). Before this module each
of those three had its own copy of a case-insensitive *substring* test, so
"pan" fired inside "company", "gst" inside "youngsters", "pf" inside
"helpful" -- the Sep 23 audit (phase-3b section 2) found over half of
Svarah's reported mentions were of this kind.

Rules:

- **Word-bounded.** A variant matches only where the characters immediately
  before and after it are not word characters. "Word character" is any
  Unicode letter, mark, or number (plus `_` and ZWJ/ZWNJ) -- *not* Python's
  `\\w`, which excludes combining marks, so `\\b`-style matching would let
  "पैन" match inside "पैनी" (the vowel sign ी is a mark, not a letter).
- **Longest variant wins.** Candidate matches are claimed longest-first and a
  shorter match overlapping an already-claimed span is dropped, so one
  stretch of text is never credited to two entities.
- **Deduplicated per (text, entity).** The unit of counting is the
  (example, entity) pair, not raw occurrences: an entity named three times
  in one utterance is one mention.

Matching is on the hand-curated lexicon variants with Unicode case folding --
never on `phonetic_key`, so the scorer stays independent of the corrector's
matcher (phase-2 spec section 6.7).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from dhvani.entity.lexicon import DomainLexicon

_JOINERS = frozenset({"‌", "‍", "_"})


def is_word_char(char: str) -> bool:
    """Letter, mark, or number in any script (plus `_`, ZWNJ, ZWJ)."""
    return char in _JOINERS or unicodedata.category(char)[0] in "LMN"


@dataclass(frozen=True, slots=True)
class Mention:
    canonical: str
    variant: str
    start: int
    end: int


def _bounded(text: str, start: int, end: int) -> bool:
    before_ok = start == 0 or not is_word_char(text[start - 1])
    after_ok = end == len(text) or not is_word_char(text[end])
    return before_ok and after_ok


def find_mentions(text: str, lexicon: DomainLexicon) -> list[Mention]:
    """Every non-overlapping, word-bounded variant occurrence in `text`,
    longest-variant-first, returned in text order."""
    folded = text.casefold()
    if len(folded) != len(text):
        # casefold can change length (e.g. "ß" -> "ss"); offsets would drift.
        # Fall back to lower(), which is length-preserving for every script
        # this lexicon uses.
        folded = text.lower()

    candidates: list[Mention] = []
    for canonical, _script, variant in lexicon.all_variants():
        needle = variant.casefold()
        if not needle:
            continue
        start = folded.find(needle)
        while start != -1:
            end = start + len(needle)
            if _bounded(folded, start, end):
                candidates.append(Mention(canonical, variant, start, end))
            start = folded.find(needle, start + 1)

    candidates.sort(key=lambda m: (-(m.end - m.start), m.start))
    claimed: list[Mention] = []
    for mention in candidates:
        if all(mention.end <= c.start or mention.start >= c.end for c in claimed):
            claimed.append(mention)
    claimed.sort(key=lambda m: m.start)
    return claimed


def mentioned_entities(text: str, lexicon: DomainLexicon) -> set[str]:
    """Canonical names of every entity `text` mentions (deduplicated)."""
    return {m.canonical for m in find_mentions(text, lexicon)}


def substring_mentioned_entities(text: str, lexicon: DomainLexicon) -> set[str]:
    """The pre-3B-1 definition: any variant as a case-insensitive substring.

    Kept only so the gate can report old-vs-new counts side by side
    (phase-3b rule 0.2.6: superseded numbers stay visible). Do not use it
    for scoring.
    """
    lowered = text.lower()
    return {
        canonical
        for canonical, _script, variant in lexicon.all_variants()
        if variant.lower() in lowered
    }
