"""3B-17 (a): number normalisation for scoring.

Both the reference and the hypothesis are reduced to digit strings before they
are compared, so "पाँच एक नौ तीन", "5 1 9 3", "5193" and "five one nine three"
are the same thing. This is **not** a Whisper-style normaliser: it changes only
number words and numerals, and leaves every other word (and every Devanagari
vowel sign) untouched.

Rules (preregistered in `docs/runs/3b-17-preregistration.md`):

1. `wer.normalize` first (NFC, lowercase, punctuation out), then tokenise on spaces.
2. Devanagari numerals become ASCII digits.
3. A run of two or more **single-digit words** (zero..nine, in Devanagari Hindi or
   English in either script) is read digit by digit: "पाँच एक नौ" -> "519".
4. Any other run of Hindi number words (ten..ninety-nine, hundred, thousand,
   lakh, crore) is read positionally: "दो सौ पचास" -> "250".
5. A lone single-digit word becomes its digit ("दो" -> "2"). This makes the
   article "एक"/"one" a digit on both sides; both sides are normalised by the
   same function, so it is symmetric.
6. Adjacent digit tokens separated only by spaces merge into one string when
   every token has at most four digits ("5149 3773 6246" -> "514937736246";
   "6 3 1 7" -> "6317"). Longer tokens are left alone.

Hand-written tables: the plan said to try Sarvam's `indic-numtowords` first; it
converts numbers to words (the opposite direction) and was not installed, so
this module is the plan's fallback.
"""

from __future__ import annotations

import re
import unicodedata

from dhvani.eval.wer import normalize

_SINGLE = {
    0: ["शून्य", "ज़ीरो", "जीरो", "जिरो", "ज़ीरो", "zero", "ज़ेरो", "जेरो"],
    1: ["एक", "one", "वन"],
    2: ["दो", "two", "टू"],
    3: ["तीन", "three", "थ्री"],
    4: ["चार", "four", "फोर"],
    5: ["पाँच", "पांच", "five", "फाइव"],
    6: ["छह", "छः", "छै", "छे", "six", "सिक्स"],
    7: ["सात", "seven", "सेवन"],
    8: ["आठ", "eight", "एट"],
    9: ["नौ", "नो", "nine", "नाइन"],
}
_TEEN_TO_NINETY_NINE = (
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
_ALT = {"पन्द्रह": 15, "अठाईस": 28}
_MULTIPLIER = {"सौ": 100, "हज़ार": 1000, "हजार": 1000, "लाख": 100_000, "करोड़": 10_000_000}

_DIGIT_WORD: dict[str, str] = {w: str(d) for d, ws in _SINGLE.items() for w in ws}
_TENS_WORD: dict[str, int] = {w: 10 + i for i, w in enumerate(_TEEN_TO_NINETY_NINE)} | _ALT
_NUMERALS = {chr(0x0966 + i): str(i) for i in range(10)}
_ASCII_DIGITS = re.compile(r"^[0-9]+$")


def _is_number_word(token: str) -> bool:
    return token in _DIGIT_WORD or token in _TENS_WORD or token in _MULTIPLIER


def _positional(tokens: list[str]) -> int:
    total = current = 0
    for token in tokens:
        if token in _MULTIPLIER:
            multiplier = _MULTIPLIER[token]
            if multiplier == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * multiplier
                current = 0
        elif token in _DIGIT_WORD:
            current += int(_DIGIT_WORD[token])
        else:
            current += _TENS_WORD[token]
    return total + current


def _read_run(run: list[str]) -> str:
    if len(run) >= 2 and all(t in _DIGIT_WORD for t in run):
        return "".join(_DIGIT_WORD[t] for t in run)
    return str(_positional(run))


def to_digit_tokens(text: str) -> str:
    """The text with number words and numerals reduced to digit strings (rules 1-6)."""
    tokens = [
        "".join(_NUMERALS.get(ch, ch) for ch in token)
        for token in unicodedata.normalize("NFC", normalize(text)).split()
    ]
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if _is_number_word(tokens[i]):
            j = i
            while j < len(tokens) and _is_number_word(tokens[j]):
                j += 1
            out.append(_read_run(tokens[i:j]))
            i = j
        else:
            out.append(tokens[i])
            i += 1
    merged: list[str] = []
    group: list[str] = []

    def flush() -> None:
        if group:
            merged.append("".join(group) if all(len(g) <= 4 for g in group) else " ".join(group))
            group.clear()

    for token in out:
        if _ASCII_DIGITS.match(token):
            group.append(token)
        else:
            flush()
            merged.append(token)
    flush()
    return " ".join(merged)


def digit_strings(text: str, *, min_digits: int = 4) -> list[str]:
    """Maximal digit runs of at least `min_digits` in the normalised text, in order."""
    return [m for m in re.findall(r"[0-9]+", to_digit_tokens(text)) if len(m) >= min_digits]
