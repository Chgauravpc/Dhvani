from __future__ import annotations

import pytest

from dhvani.entity.lexicon import DEVANAGARI, LATIN, TAMIL
from dhvani.entity.phonetic import detect_script, phonetic_key

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


def test_detect_script_devanagari() -> None:
    assert detect_script(AADHAAR_DEVANAGARI) == DEVANAGARI


def test_detect_script_tamil() -> None:
    assert detect_script(AADHAAR_TAMIL) == TAMIL


def test_detect_script_latin() -> None:
    assert detect_script("aadhaar card") == LATIN


def test_detect_script_falls_back_to_latin_for_empty_text() -> None:
    assert detect_script("") == LATIN


def test_detect_script_picks_dominant_block_in_mixed_text() -> None:
    """A word or two of English leaking into an otherwise-Devanagari
    transcript (very common in real Indic ASR output) should still read as
    Devanagari overall."""
    assert detect_script("मेरा आधार card चेक करो") == DEVANAGARI
