from __future__ import annotations

import pytest

from dhvani.entity.lexicon import DEVANAGARI, LATIN, TAMIL
from dhvani.entity.phonetic import phonetic_key

# Devanagari/Tamil literals below are the exact strings this test pins
# against -- verified directly against installed indic-transliteration
# 2.3.82 output, not approximated (see entity/phonetic.py's docstring).
AADHAAR_DEVANAGARI = "आधार"  # आधार
AADHAAR_DEVANAGARI_WITH_CARD = "आधार कार्ड"  # आधार कार्ड
AADHAAR_TAMIL = "ஆதார"  # ஆதார


def test_phonetic_key_pinned_devanagari_output() -> None:
    assert phonetic_key(AADHAAR_DEVANAGARI, DEVANAGARI) == "adhara"


def test_phonetic_key_pinned_latin_output() -> None:
    assert phonetic_key("aadhaar", LATIN) == "adhar"


def test_phonetic_key_pinned_tamil_output() -> None:
    assert phonetic_key(AADHAAR_TAMIL, TAMIL) == "adhara"


@pytest.mark.parametrize("spelling", ["aadhaar", "aadhar", "adhaar"])
def test_latin_spelling_variants_of_aadhaar_collapse_to_the_same_key(spelling: str) -> None:
    assert phonetic_key(spelling, LATIN) == "adhar"


def test_cross_script_aadhaar_keys_are_near_identical() -> None:
    """Not required to be byte-identical -- the fuzzy match downstream
    absorbs a one-character difference -- but they must be close."""
    latin_key = phonetic_key("aadhaar", LATIN)
    devanagari_key = phonetic_key(AADHAAR_DEVANAGARI, DEVANAGARI)
    tamil_key = phonetic_key(AADHAAR_TAMIL, TAMIL)
    assert devanagari_key == tamil_key == "adhara"
    assert devanagari_key.startswith(latin_key)


def test_phonetic_key_normalizes_case_and_whitespace() -> None:
    key = phonetic_key(AADHAAR_DEVANAGARI_WITH_CARD, DEVANAGARI)
    assert key == "adhara karda"
    assert "  " not in key


def test_phonetic_key_rejects_unsupported_script() -> None:
    with pytest.raises(ValueError, match="unsupported script"):
        phonetic_key("aadhaar", "klingon")
