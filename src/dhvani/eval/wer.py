"""Word Error Rate -- phase-2b spec section B.1. Nothing in the repo computed
WER before this; the model sweep (`eval/model_sweep.py`) is the reason it
exists.

Normalization choices move WER by several points, so `normalize` is part of
the published result, not an implementation detail: lowercase, strip
punctuation (including the Devanagari danda U+0964 and double danda U+0965),
collapse whitespace, and normalize to Unicode NFC first so visually identical
Devanagari (composed vs. combining-mark sequences) compares equal.

**Verified, not assumed**: an earlier version of `normalize` stripped
punctuation with the regex `[^\\w\\s]`, on the assumption that `\\w` covers
every character that should survive. It does not -- Python's `\\w` matches
Unicode *alphanumeric* characters plus underscore, and Devanagari vowel signs
and the virama (e.g. U+094D, category `Mn`, "Mark, nonspacing") are
combining marks, not alphanumeric, so `\\w` excludes them too. Running that
regex over "नमस्ते" ("namaste") silently
dropped the virama and the following vowel sign, corrupting the word into
something else entirely -- not just leaving the danda behind, the actual bug
this normalizer exists to avoid. Fixed by classifying per-character on
`unicodedata.category` instead: keep Letters (`L*`), Marks (`M*` -- this is
what a regex `\\w` check misses for Devanagari), and Numbers (`N*`); collapse
whitespace to a single space; drop everything else, which is exactly
punctuation and symbols, including the danda (category `Po`).

`corpus_wer` aggregates by summing edits and reference words across an
entire corpus, never by averaging each utterance's own WER -- averaging
per-utterance rates over-weights short utterances (a 1-word utterance with
one substitution contributes a full 100% to the average, same weight as a
50-word utterance with one error) and is the single most common way to
report a wrong WER.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_KEEP_CATEGORY_PREFIXES = ("L", "M", "N")  # Letter, Mark, Number
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Canonical form for WER comparison.

    Lowercases, strips punctuation (including the Devanagari danda), collapses
    whitespace, and normalizes Unicode to NFC so visually identical Devanagari
    compares equal. See the module docstring for why this classifies by
    Unicode category rather than filtering with a `\\w` regex.
    """
    normalized = unicodedata.normalize("NFC", text).lower()
    kept_chars = [
        " " if ch.isspace() else ch
        for ch in normalized
        if ch.isspace() or unicodedata.category(ch).startswith(_KEEP_CATEGORY_PREFIXES)
    ]
    return _WHITESPACE_RE.sub(" ", "".join(kept_chars)).strip()


@dataclass(frozen=True, slots=True)
class WerResult:
    wer: float
    substitutions: int
    deletions: int
    insertions: int
    reference_words: int


def _align(reference_words: Sequence[str], hypothesis_words: Sequence[str]) -> tuple[int, int, int]:
    """Levenshtein alignment over word sequences, returning
    (substitutions, deletions, insertions) via DP + backtrace."""
    n, m = len(reference_words), len(hypothesis_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if reference_words[i - 1] == hypothesis_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    substitutions = deletions = insertions = 0
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and reference_words[i - 1] == hypothesis_words[j - 1]
            and dp[i][j] == dp[i - 1][j - 1]
        ):
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            substitutions += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            deletions += 1
            i -= 1
        else:
            assert j > 0 and dp[i][j] == dp[i][j - 1] + 1
            insertions += 1
            j -= 1

    return substitutions, deletions, insertions


def word_error_rate(reference: str, hypothesis: str) -> WerResult:
    """Levenshtein distance over normalized word sequences.

    If the normalized reference has zero words, `wer` is 0.0 when the
    hypothesis is also empty, else 1.0 -- the conventional way to avoid a
    division by zero without silently reporting a perfect score for a
    hallucinated transcript of a silent reference.
    """
    reference_words = normalize(reference).split()
    hypothesis_words = normalize(hypothesis).split()
    substitutions, deletions, insertions = _align(reference_words, hypothesis_words)
    n_reference = len(reference_words)
    if n_reference:
        wer = (substitutions + deletions + insertions) / n_reference
    else:
        wer = 0.0 if not hypothesis_words else 1.0
    return WerResult(
        wer=wer,
        substitutions=substitutions,
        deletions=deletions,
        insertions=insertions,
        reference_words=n_reference,
    )


def corpus_wer(pairs: Sequence[tuple[str, str]]) -> WerResult:
    """Aggregate over a corpus by summing edits and reference words -- NOT by
    averaging per-utterance WER. See module docstring for why."""
    total_substitutions = total_deletions = total_insertions = total_reference = 0
    for reference, hypothesis in pairs:
        result = word_error_rate(reference, hypothesis)
        total_substitutions += result.substitutions
        total_deletions += result.deletions
        total_insertions += result.insertions
        total_reference += result.reference_words

    total_edits = total_substitutions + total_deletions + total_insertions
    wer = total_edits / total_reference if total_reference else 0.0
    return WerResult(
        wer=wer,
        substitutions=total_substitutions,
        deletions=total_deletions,
        insertions=total_insertions,
        reference_words=total_reference,
    )
