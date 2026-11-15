from __future__ import annotations

import pytest

from dhvani.eval.numbers import digit_strings, to_digit_tokens


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("पाँच एक नौ तीन", "5193"),
        ("मेरा नंबर 5 1 9 3 है", "मेरा नंबर 5193 है"),
        ("five one nine three", "5193"),
        ("फाइव वन नाइन थ्री", "5193"),
        ("५१९३", "5193"),
        ("5149 3773 6246", "514937736246"),
        ("दो सौ पचास", "250"),
        ("एक हज़ार दो सौ", "1200"),
        ("सौ", "100"),
        ("पच्चीस हजार", "25000"),
        ("दो", "2"),
        ("छः तीन एक सात दो पाँच चार सात चार दो जीरो", "63172547420"),
    ],
)
def test_reduces_numbers_to_digit_strings(text: str, expected: str) -> None:
    assert to_digit_tokens(text) == expected


def test_other_words_and_vowel_signs_are_untouched() -> None:
    assert to_digit_tokens("नमस्ते आधार कार्ड") == "नमस्ते आधार कार्ड"
    assert to_digit_tokens("Hello, World!") == "hello world"


def test_long_tokens_are_not_merged() -> None:
    assert to_digit_tokens("12345 67890") == "12345 67890"


def test_both_spellings_give_the_same_digit_string() -> None:
    spelled = "मेरा नंबर पाँच एक नौ तीन नौ नौ तीन पाँच छः छः है"
    written = "मेरा नंबर 5193993566 है।"
    assert digit_strings(spelled) == digit_strings(written) == ["5193993566"]


def test_digit_strings_are_maximal_runs_not_substrings() -> None:
    assert digit_strings("id 51939935667", min_digits=4) == ["51939935667"]
    assert digit_strings("call 12 now") == []
