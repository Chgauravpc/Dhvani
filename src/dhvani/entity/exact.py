"""Exact-lookup canonicalisation: replace every word-bounded curated variant of
a lexicon entity with its canonical form (phase-4 plan, 3B-14 / 3B-15).

This is the "dictionary lookup" the Nov 14 review found the corrector's large
canonicalisation win to be (phase-3b section 11.1, B3): no phonetic keys, no
fuzzy scores, no threshold. It uses the same matcher the scorer counts
mentions with (`dhvani.entity.mentions.find_mentions`), so it can only rewrite
text the scorer would also call an entity mention -- which is also why it has
essentially no corruption source: a window of ordinary text is never rewritten
unless it *is* a hand-curated variant, word-bounded.
"""

from __future__ import annotations

from dataclasses import dataclass

from dhvani.entity.lexicon import DomainLexicon
from dhvani.entity.mentions import find_mentions


@dataclass(frozen=True, slots=True)
class ExactRewrite:
    span: tuple[int, int]
    original: str
    canonical: str


@dataclass(frozen=True, slots=True)
class ExactResult:
    text: str
    rewrites: list[ExactRewrite]


def canonicalise_exact(text: str, lexicon: DomainLexicon) -> ExactResult:
    """`text` with each word-bounded variant occurrence replaced by its canonical
    form. Matches are non-overlapping and longest-variant-first (the shared
    matcher's rule), so one stretch of text is never rewritten twice."""
    parts: list[str] = []
    rewrites: list[ExactRewrite] = []
    last = 0
    for mention in find_mentions(text, lexicon):
        parts.append(text[last : mention.start])
        parts.append(mention.canonical)
        rewrites.append(
            ExactRewrite(
                (mention.start, mention.end), text[mention.start : mention.end], mention.canonical
            )
        )
        last = mention.end
    parts.append(text[last:])
    return ExactResult("".join(parts), rewrites)
