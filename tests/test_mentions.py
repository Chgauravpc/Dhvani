"""Phase-3b item 3B-1: the shared, word-bounded mention definition.

Each false-hit case here is a real one the Sep 23 audit found in Svarah or
LAHAJA ground truth (phase-3b section 2), not an invented edge case.
"""

from __future__ import annotations

import pytest

from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.entity.mentions import (
    find_mentions,
    is_word_char,
    mentioned_entities,
    substring_mentioned_entities,
)
from dhvani.eval.entity_error_rate import _mentioned_entities


@pytest.mark.parametrize(
    "text",
    [
        "i work in a software company",  # "pan"
        "i use pantene shampoo",  # "pan"
        "aam panna is a summer drink",  # "pan"
        "youngsters these days",  # "gst"
        "that was very helpful",  # "pf"
        "the painting depicts a river",  # "epic"
        "i was born in udupi",  # "upi"
        "the seat is occupied",  # "upi"
        "the pupils listened",  # "upi"
        "यह आधारशिला है",  # Devanagari "आधार" inside a longer word
        "यह आधारभूत ढांचा है",
    ],
)
def test_no_mention_inside_a_longer_word(text: str) -> None:
    assert mentioned_entities(text, DEFAULT_LEXICON) == set()
    # and the legacy substring rule did fire on every one of these
    assert substring_mentioned_entities(text, DEFAULT_LEXICON) != set()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("my pan card is lost", {"PAN card"}),
        ("pay by UPI please.", {"UPI"}),
        ("update your Aadhaar, then check CoWIN", {"Aadhaar", "CoWIN"}),
        ("मेरा आधार कार्ड खो गया", {"Aadhaar"}),
        ("co-win se certificate", {"CoWIN"}),
        ("(GST)", {"GST"}),
    ],
)
def test_real_mentions_found(text: str, expected: set[str]) -> None:
    assert mentioned_entities(text, DEFAULT_LEXICON) == expected


def test_epfo_is_not_also_provident_fund() -> None:
    # audit: "epfo passbook" was double-counted as EPFO + Provident Fund via "pf"
    assert mentioned_entities("check the epfo passbook", DEFAULT_LEXICON) == {"EPFO"}


def test_devanagari_vowel_sign_is_a_word_character() -> None:
    # "ी" (U+0940) is a combining mark: Python's \w would treat it as a
    # boundary and let "पैन" match inside "पैनी" ("sharp").
    assert is_word_char("ी")
    assert mentioned_entities("चाकू पैनी है", DEFAULT_LEXICON) == set()
    assert mentioned_entities("मेरा पैन खो गया", DEFAULT_LEXICON) == {"PAN card"}


def test_longest_variant_wins_and_dedup_per_entity() -> None:
    mentions = find_mentions("aadhaar card and aadhaar again", DEFAULT_LEXICON)
    assert [m.variant for m in mentions] == ["aadhaar card", "aadhaar"]
    assert mentioned_entities("aadhaar card and aadhaar again", DEFAULT_LEXICON) == {"Aadhaar"}


def test_scorer_uses_shared_definition() -> None:
    assert _mentioned_entities("software company", DEFAULT_LEXICON) == set()
    assert _mentioned_entities("my pan card", DEFAULT_LEXICON) == {"PAN card"}
