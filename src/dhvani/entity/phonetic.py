"""Cross-script phonetic key generation for fuzzy entity matching.

Verified against the installed `indic-transliteration==2.3.82`, not assumed
(phase-2 spec open question 3): a plain lowercase Latin spelling like
"aadhaar" must be interpreted through the **ITRANS** scheme, not HK -- HK
expects capitalized long vowels (`A` for long a) and mangles a casual
spelling (`sanscript.transliterate("aadhaar", HK, DEVANAGARI)` gives
"अअधअर्", not "आधार"), while ITRANS's doubled-vowel convention ("aa" for
long a) matches how these terms are actually spelled in English civic
vocabulary. HK is used only as the *output* scheme for the normalized key:
pure ASCII, one established romanization per phoneme, well-suited to a
rapidfuzz string comparison. Confirmed empirically that this collapses
spelling variants of the same entity to the same or a near-identical key
-- "aadhaar", "aadhar", and "adhaar" (all ITRANS-interpreted) each
transliterate to HK as "AdhAr"/"Adhar"/"adhAr", which lowercase to the
identical string "adhar".

Also verified: interpreting text through ITRANS assumes the schwa (the
implicit final "a") is written explicitly when it's retained in spelling
("aadhaara", not "aadhaar") -- Hindi orthography keeps this "a" for most
words even though it's not pronounced, but ITRANS's own convention (correct
for Sanskrit, which does drop it in writing) adds a trailing virama to a
bare final consonant. This module's callers pass already-spoken/transcribed
text, so it inherits whatever the input's own convention was; the effect on
the produced key is at most a difference of one trailing vowel character,
which the fuzzy match downstream is meant to absorb.
"""

from __future__ import annotations

import re

from indic_transliteration import sanscript

from dhvani.entity.lexicon import DEVANAGARI, LATIN, TAMIL

_SOURCE_SCHEME = {
    LATIN: sanscript.ITRANS,
    DEVANAGARI: sanscript.DEVANAGARI,
    TAMIL: sanscript.TAMIL,
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
_RUN_OF_SPACES_RE = re.compile(r" {2,}")

_DEVANAGARI_BLOCK = range(0x0900, 0x0980)
_TAMIL_BLOCK = range(0x0B80, 0x0C00)


def detect_script(text: str) -> str:
    """Classifies `text` as `DEVANAGARI`, `TAMIL`, or `LATIN` by its
    dominant Unicode block.

    Exists because ASR output script can't be assumed from the spoken
    language -- verified directly and reproducibly (not a one-off): real
    Hindi audio transcribed through `WhisperSTT` with faster-whisper's
    `tiny` model came back as romanized/Latin text ("Varanasi mein Achesh
    Shaka Hari restaurant batao..."), not Devanagari, across every example
    tried. Whether the project's real default (`small`) behaves the same
    way is unverified -- this environment cannot download it (phase-1 spec
    section 11) -- so `EntityCorrector` detects script per candidate window
    instead of trusting a caller-declared one.
    """
    devanagari = sum(1 for ch in text if ord(ch) in _DEVANAGARI_BLOCK)
    tamil = sum(1 for ch in text if ord(ch) in _TAMIL_BLOCK)
    if devanagari and devanagari >= tamil:
        return DEVANAGARI
    if tamil:
        return TAMIL
    return LATIN


def phonetic_key(text: str, script: str) -> str:
    """Transliterate `text` to a common romanized form and normalize it
    (case, punctuation, repeated spaces) for fuzzy cross-script comparison.

    `script` must be one of `dhvani.entity.lexicon.{DEVANAGARI,LATIN,TAMIL}`
    -- use `detect_script` first if the caller doesn't already know it.
    """
    try:
        source_scheme = _SOURCE_SCHEME[script]
    except KeyError:
        raise ValueError(
            f"unsupported script {script!r}, expected one of {sorted(_SOURCE_SCHEME)}"
        ) from None

    romanized = sanscript.transliterate(text, source_scheme, sanscript.HK)
    key = romanized.lower()
    key = _NON_ALNUM_RE.sub("", key)
    key = _RUN_OF_SPACES_RE.sub(" ", key)
    return key.strip()
